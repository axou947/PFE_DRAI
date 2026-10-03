"""Key-free official sources for the UK, Japan and emerging-market regions (docs/REGIONS.md).

    Bank of England    IADB database, CSV: daily gilt yields (nominal and real zero-coupon curves)
    Japan MoF          JGB benchmark yields, CSV files: daily, 1y to 40y
    OECD               Data Explorer, SDMX: Key Short-Term Economic Indicators (industrial production,
                       unemployment rate, long-term interest rates), monthly
    BIS                SDMX: consumer prices (long series) and central bank policy rates

None needs an API key. Every parser is a pure function tested on recorded payloads (tests/test_regions.py);
every fetcher fails loudly with the server's answer, so a wrong code never turns into silent numbers.
"""

import io

import httpx
import pandas as pd

# The Bank of England and the MoF answer browser-like clients only (a bare client gets an error page).
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; pfe-drai research; +https://github.com/axou947/PFE_DRAI)"}

BOE_URL = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
MOF_URLS = (
    # Up to the end of the previous month, then the current month: both are needed for the latest days.
    "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv",
    "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv",
)
OECD_URL = "https://sdmx.oecd.org/public/rest/data/{flow}/{key}"
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/{flow}/1.0/{key}"


class NoDataError(ValueError):
    """The source has no data for this code (an unknown code, or a series it stopped publishing)."""


def _get(url: str, params: dict | None = None, timeout: int = 60) -> httpx.Response:
    response = httpx.get(url, params=params, headers=HEADERS, timeout=timeout, follow_redirects=True)
    if response.status_code == 404:
        # SDMX servers answer 404 "NoRecordsFound" for a valid query that matches nothing.
        raise NoDataError(f"{response.url}: no data (404) {response.text[:200]}")
    response.raise_for_status()
    return response


# ---- Bank of England ------------------------------------------------------------------------------


def parse_boe(text: str) -> pd.DataFrame:
    """IADB CSV (CSVF=TN): a DATE column ('02 Jan 2024') and one column per series code."""
    if text.lstrip().startswith("<"):
        # An unknown code returns an HTML page ("Invalid series code value supplied"), not a CSV.
        raise NoDataError("Bank of England: the answer is a web page, not data (unknown series code?)")
    frame = pd.read_csv(io.StringIO(text))
    frame.columns = [c.strip() for c in frame.columns]
    dates = pd.to_datetime(frame.pop("DATE"), format="%d %b %Y")
    frame = frame.apply(pd.to_numeric, errors="coerce")
    frame.index = pd.DatetimeIndex(dates)
    return frame.sort_index()


def fetch_boe(codes: list[str], start, end) -> pd.DataFrame:
    params = {
        "csv.x": "yes",
        "SeriesCodes": ",".join(codes),
        "UsingCodes": "Y",
        "CSVF": "TN",
        "Datefrom": pd.Timestamp(start).strftime("%d/%b/%Y"),
        "Dateto": pd.Timestamp(end).strftime("%d/%b/%Y"),
    }
    frame = parse_boe(_get(BOE_URL, params).text)
    missing = [code for code in codes if code not in frame.columns]
    if missing:
        raise NoDataError(f"Bank of England: no column for {', '.join(missing)}")
    return frame


# ---- Japan Ministry of Finance ----------------------------------------------------------------------


def parse_mof(text: str) -> pd.DataFrame:
    """MoF JGB yields CSV: a title line, then 'Date,1Y,2Y,...,40Y'; dates '1974/9/24'; '-' = no yield."""
    lines = text.splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith("Date,"))
    frame = pd.read_csv(io.StringIO("\n".join(lines[header:])), na_values=["-", ""])
    dates = pd.to_datetime(frame.pop("Date"), format="%Y/%m/%d", errors="coerce")
    frame = frame.apply(pd.to_numeric, errors="coerce")
    frame.index = pd.DatetimeIndex(dates)
    return frame[frame.index.notna()].sort_index()


def fetch_mof(start, end) -> pd.DataFrame:
    parts = []
    for url in MOF_URLS:
        response = _get(url)
        # The files are plain ASCII in English; older copies were Shift-JIS: decode defensively.
        parts.append(parse_mof(response.content.decode("utf-8", errors="replace")))
    frame = pd.concat(parts)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame.loc[pd.Timestamp(start) : pd.Timestamp(end)]


# ---- SDMX (OECD, BIS) -----------------------------------------------------------------------------


def period_start(period: str) -> pd.Timestamp:
    """'2024-03' -> 2024-03-01; '2024-03-15' -> that day; '2024-Q1' -> 2024-01-01."""
    period = str(period)
    if "Q" in period:
        return pd.Period(period.replace("-", ""), freq="Q").to_timestamp()
    return pd.Period(period, freq="M").to_timestamp() if len(period) == 7 else pd.Timestamp(period)


def parse_sdmx_csv(text: str) -> pd.DataFrame:
    """SDMX-CSV (OECD csvfile, BIS csv): one column per area, indexed by the start of the period.

    The query must leave only REF_AREA open: two series for the same area means the key is not specific.
    """
    # keep_default_na=False: "NA" is Namibia's area code, not a missing value.
    frame = pd.read_csv(io.StringIO(text), dtype={"TIME_PERIOD": str, "REF_AREA": str}, keep_default_na=False, na_values=[""])
    if frame.empty:
        raise NoDataError("SDMX: no observation")
    frame["OBS_VALUE"] = pd.to_numeric(frame["OBS_VALUE"], errors="coerce")  # BIS writes "NaN"
    frame = frame.dropna(subset=["OBS_VALUE"])
    repeated = frame.duplicated(["REF_AREA", "TIME_PERIOD"], keep=False)
    if repeated.any():
        area = frame.loc[repeated, "REF_AREA"].iloc[0]
        raise ValueError(f"SDMX: several series for {area}: the key must fix every dimension but REF_AREA")
    wide = frame.pivot(index="TIME_PERIOD", columns="REF_AREA", values="OBS_VALUE")
    wide.index = pd.DatetimeIndex([period_start(p) for p in wide.index])
    wide.columns.name = None
    return wide.sort_index()


def fetch_oecd(flow: str, key: str, start) -> pd.DataFrame:
    """OECD Data Explorer (60 queries an hour per client: one query per series, every area at once)."""
    params = {"startPeriod": pd.Timestamp(start).strftime("%Y-%m"), "format": "csvfile"}
    return parse_sdmx_csv(_get(OECD_URL.format(flow=flow, key=key), params, timeout=120).text)


def fetch_bis(flow: str, key: str, start) -> pd.DataFrame:
    params = {"startPeriod": pd.Timestamp(start).strftime("%Y-%m-%d"), "format": "csv"}
    return parse_sdmx_csv(_get(BIS_URL.format(flow=flow, key=key), params, timeout=120).text)
