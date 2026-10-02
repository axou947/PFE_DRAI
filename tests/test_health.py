"""Daily job health: NYSE calendar, record checks, source freshness, run records, failure reports, page labels."""

import copy
import csv
import hashlib
import json

import httpx
import pandas as pd
import pytest

from pfe_drai import health, nyse
from pfe_drai.cli import main
from pfe_drai.config import load_settings
from pfe_drai.publish.page import render
from pfe_drai.publish.record import _BITCOIN_TAG, _PENDING_TAG, read_live
from pfe_drai.publish.snapshot import config_fingerprint

OK, WARNING, FAILURE = health.OK, health.WARNING, health.FAILURE


@pytest.fixture(scope="module")
def cfg():
    return load_settings()


def _publish_time(day, hours_after_close=1.5):
    return (nyse.session_close(day) + pd.Timedelta(hours=hours_after_close)).isoformat()


def _entries(folder, days, published=None, ots=None):
    """A track_record/ folder with one chained entry per day, written as `publish` writes them."""
    folder.mkdir(parents=True, exist_ok=True)
    previous = ""
    rows = []
    for day in days:
        payload = {
            "date": day,
            "regime": "expansion",
            "probabilities": {"stress": 0.1},
            "alarm": {"on": False, "score": 0.1},
            "published_at": (published or {}).get(day, _publish_time(day)),
            "previous_sha256": previous,
        }
        path = folder / f"{day}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append([day, "expansion", "0.1", "combined", "fred", digest])
        previous = digest
        proof = (ots or {}).get(day, "bitcoin")
        if proof != "missing":
            tag = _BITCOIN_TAG if proof == "bitcoin" else _PENDING_TAG
            (folder / f"{day}.json.ots").write_bytes(b"OpenTimestamps" + tag)
    with (folder / "index.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "regime", "p_regime", "model", "data_provider", "sha256"])
        writer.writerows(rows)
    return folder


def _status(checks, name):
    return next(c for c in checks if c.name == name)


# ---------------------------------------------------------------- calendar
@pytest.mark.parametrize(
    "day,name",
    [
        ("2024-03-29", "Good Friday"),
        ("2024-06-19", "Juneteenth"),
        ("2024-11-28", "Thanksgiving Day"),
        ("2024-12-25", "Christmas Day"),
        ("2023-01-02", "New Year's Day"),  # 1 January 2023 is a Sunday
        ("2022-12-26", "Christmas Day"),  # Christmas 2022 is a Sunday
        ("2022-06-20", "Juneteenth"),  # first year, a Sunday: observed Monday
        ("2026-07-03", "Independence Day"),  # 4 July 2026 is a Saturday: observed Friday
        ("2026-01-19", "Birthday of Martin Luther King, Jr."),
        ("2026-05-25", "Memorial Day"),
        ("2026-09-07", "Labor Day"),
        ("2025-01-09", "Exceptional closure"),  # national day of mourning
        ("2012-10-29", "Exceptional closure"),  # Hurricane Sandy
    ],
)
def test_known_closures(day, name):
    assert not nyse.is_session(day)
    assert nyse.holiday_name(day) == name


@pytest.mark.parametrize(
    "day",
    [
        "2021-12-31",  # New Year's Day 2022 was a Saturday and is not observed on the Friday
        "2021-06-18",  # Juneteenth only became a market holiday in 2022
        "2024-11-29",  # the day after Thanksgiving is open (early close)
        "2024-12-24",
        "2026-10-01",
    ],
)
def test_open_days(day):
    assert nyse.is_session(day)


def test_weekends_are_not_sessions_and_have_no_holiday_name():
    assert not nyse.is_session("2026-10-03")
    assert nyse.holiday_name("2026-10-03") is None


def test_session_navigation():
    assert nyse.previous_session("2024-11-29") == pd.Timestamp("2024-11-27")  # Thanksgiving in between
    assert nyse.next_session("2024-11-27") == pd.Timestamp("2024-11-29")
    assert nyse.previous_session("2026-10-05") == pd.Timestamp("2026-10-02")
    assert nyse.sessions_between("2026-09-30", "2026-10-05") == 3
    assert nyse.sessions_between("2026-10-05", "2026-10-05") == 0
    assert list(nyse.sessions("2026-10-02", "2026-10-06")) == [
        pd.Timestamp("2026-10-02"),
        pd.Timestamp("2026-10-05"),
        pd.Timestamp("2026-10-06"),
    ]


def test_last_closed_session():
    assert nyse.last_closed_session("2026-10-01T20:59:00Z") == pd.Timestamp("2026-09-30")
    assert nyse.last_closed_session("2026-10-01T21:00:00Z") == pd.Timestamp("2026-10-01")
    assert nyse.last_closed_session("2026-10-03T12:00:00Z") == pd.Timestamp("2026-10-02")  # Saturday
    assert nyse.last_closed_session("2026-10-05T12:00:00Z") == pd.Timestamp("2026-10-02")  # Monday morning
    assert nyse.last_closed_session("2024-11-28T23:00:00Z") == pd.Timestamp("2024-11-27")  # Thanksgiving evening
    assert nyse.last_closed_session(pd.Timestamp("2026-10-01 22:00")) == pd.Timestamp("2026-10-01")  # naive = UTC


# ---------------------------------------------------------------- record checks
def test_healthy_record(tmp_path, cfg):
    folder = _entries(tmp_path, ["2026-09-30", "2026-10-01"])
    report = health.build_report(folder, cfg, "2026-10-02T06:30:00Z")
    assert report.status == OK and report.exit_code == 0
    assert report.expected_day == report.latest_day == "2026-10-01"


def test_a_missing_market_day_is_a_failure_that_names_the_date(tmp_path, cfg):
    folder = _entries(tmp_path, ["2026-09-29", "2026-10-01"])  # 2026-09-30 never published
    checks = health.check_record(folder, "2026-10-02T06:30:00Z", cfg)
    gaps = _status(checks, "record.gaps")
    assert gaps.status == WARNING and "2026-09-30" in gaps.message
    # the day after, the latest entry is also late
    late = health.check_record(_entries(tmp_path / "b", ["2026-09-29", "2026-09-30"]), "2026-10-02T07:00:00Z", cfg)
    latest = _status(late, "record.latest")
    assert latest.status == FAILURE and "2026-10-01" in latest.message and latest.details["missing"] == ["2026-10-01"]
    assert health.build_report(tmp_path / "b", cfg, "2026-10-02T07:00:00Z").exit_code == 2


def test_the_job_gets_its_grace_before_a_day_counts_as_missed(tmp_path, cfg):
    folder = _entries(tmp_path, ["2026-09-30"])
    # 01:46 UTC is when the first scheduled run really started: not late yet
    early = _status(health.check_record(folder, "2026-10-02T01:00:00Z", cfg), "record.latest")
    assert early.status == OK and "not out yet" in early.message and "06:00 UTC" in early.message
    assert _status(health.check_record(folder, "2026-10-02T06:01:00Z", cfg), "record.latest").status == FAILURE


@pytest.mark.parametrize(
    "last,now,reason",
    [
        ("2024-11-27", "2024-11-29T08:00:00Z", "Thanksgiving Day"),
        ("2026-04-02", "2026-04-06T08:00:00Z", "Good Friday"),
        ("2026-05-22", "2026-05-26T07:00:00Z", "Memorial Day"),  # the day after a long weekend
        ("2024-06-18", "2024-06-20T08:00:00Z", "Juneteenth"),
    ],
)
def test_a_holiday_stays_green_and_says_why(tmp_path, cfg, last, now, reason):
    folder = _entries(tmp_path, [last])
    latest = _status(health.check_record(folder, now, cfg), "record.latest")
    assert latest.status == OK
    assert reason in latest.message


def test_the_weekend_is_not_a_miss(tmp_path, cfg):
    folder = _entries(tmp_path, ["2026-10-02"])
    assert health.build_report(folder, cfg, "2026-10-05T05:00:00Z").status == OK  # Monday morning, Friday is the last day


def test_gaps_in_the_middle_are_named_and_can_be_acknowledged(tmp_path, cfg):
    folder = _entries(tmp_path, ["2026-09-28", "2026-09-30", "2026-10-01"])
    gap = _status(health.check_record(folder, "2026-10-02T06:30:00Z", cfg), "record.gaps")
    assert gap.status == WARNING and "2026-09-29" in gap.message
    acknowledged = copy.deepcopy(cfg)
    acknowledged["health"]["acknowledged_gaps"] = {"2026-09-29": "GitHub incident"}
    done = _status(health.check_record(folder, "2026-10-02T06:30:00Z", acknowledged), "record.gaps")
    assert done.status == OK and "1 acknowledged" in done.message


def test_an_entry_on_a_closed_day_is_flagged(tmp_path, cfg):
    folder = _entries(tmp_path, ["2024-11-27", "2024-11-28", "2024-11-29"])  # Thanksgiving "published"
    gap = _status(health.check_record(folder, "2024-11-30T08:00:00Z", cfg), "record.gaps")
    assert gap.status == WARNING and "2024-11-28" in gap.message


def test_a_tampered_file_is_an_integrity_failure_and_is_never_repaired(tmp_path, cfg):
    folder = _entries(tmp_path, ["2026-09-30", "2026-10-01"])
    target = folder / "2026-09-30.json"
    target.write_text(target.read_text().replace("expansion", "stress"), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    report = health.build_report(folder, cfg, "2026-10-02T06:30:00Z")
    assert report.exit_code == 2
    integrity = _status(report.checks, "record.integrity")
    assert integrity.status == FAILURE and "2026-09-30" in integrity.message
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before  # read-only


def test_a_broken_chain_link_is_an_integrity_failure(tmp_path, cfg):
    folder = _entries(tmp_path, ["2026-09-30", "2026-10-01"])
    rows = list(csv.reader((folder / "index.csv").open(encoding="utf-8")))
    del rows[1]  # the first day vanishes from the index: the second one no longer links
    with (folder / "index.csv").open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(rows)
    assert _status(health.check_record(folder, "2026-10-02T06:30:00Z", cfg), "record.integrity").status == FAILURE


def test_timestamp_proofs_must_be_upgraded_within_days(tmp_path, cfg):
    days = ["2026-09-21", "2026-09-22", "2026-09-23", "2026-10-01"]
    folder = _entries(tmp_path, days, ots={"2026-09-21": "pending", "2026-09-22": "missing", "2026-10-01": "pending"})
    ots = _status(health.check_record(folder, "2026-10-02T06:30:00Z", cfg), "record.ots")
    assert ots.status == WARNING
    assert ots.details["pending"] == ["2026-09-21"] and ots.details["missing"] == ["2026-09-22"]  # 10-01 is too recent to count
    assert (
        _status(
            health.check_record(folder, "2026-10-02T06:30:00Z", {**cfg, "publish": {**cfg["publish"], "opentimestamps": False}}),
            "record.ots",
        ).status
        == OK
    )


def test_a_late_entry_is_labelled_not_hidden(tmp_path, cfg):
    on_time = _entries(tmp_path / "a", ["2026-10-01"], published={"2026-10-01": "2026-10-02T01:46:00+00:00"})
    assert _status(health.check_record(on_time, "2026-10-02T06:30:00Z", cfg), "record.timeliness").status == OK
    late = _entries(tmp_path / "b", ["2026-10-01"], published={"2026-10-01": "2026-10-02T15:00:00+00:00"})
    check = _status(health.check_record(late, "2026-10-02T16:00:00Z", cfg), "record.timeliness")
    assert check.status == WARNING and "late" in check.message


def test_no_entry_yet_is_a_warning(tmp_path, cfg):
    report = health.build_report(tmp_path, cfg, "2026-10-02T06:30:00Z")
    assert report.status == WARNING and report.latest_day is None


# ---------------------------------------------------------------- data-health records
def _write_record(folder, day, status, checks):
    (folder / "health").mkdir(exist_ok=True)
    record = {"kind": "health", "status": status, "generated_at": f"{day} 22:40 UTC", "checks": checks}
    (folder / "health" / f"{day}.json").write_text(json.dumps(record), encoding="utf-8")


def test_degraded_data_behind_the_latest_entry_is_surfaced(tmp_path, cfg):
    folder = _entries(tmp_path, ["2026-10-01"])
    bad = {
        "name": "sources.freshness",
        "status": WARNING,
        "message": "stale: vix (last 2026-09-28, 2 session(s) behind)",
        "details": {},
    }
    _write_record(folder, "2026-10-01", WARNING, [bad])
    data = _status(health.check_record(folder, "2026-10-02T06:30:00Z", cfg), "record.data")
    assert data.status == WARNING and "vix" in data.message


def test_a_missing_data_record_is_only_a_warning_once_records_exist(tmp_path, cfg):
    folder = _entries(tmp_path, ["2026-09-30", "2026-10-01"])
    assert _status(health.check_record(folder, "2026-10-02T06:30:00Z", cfg), "record.data").status == OK  # none yet
    _write_record(folder, "2026-09-30", OK, [])
    assert _status(health.check_record(folder, "2026-10-02T06:30:00Z", cfg), "record.data").status == WARNING


def test_a_missing_day_reports_what_the_job_found(tmp_path, cfg):
    folder = _entries(tmp_path, ["2026-09-30"])
    failure = {"name": "run.entry", "status": FAILURE, "message": "no new entry for market day 2026-10-01", "details": {}}
    _write_record(folder, "2026-10-01", FAILURE, [failure])
    latest = _status(health.check_record(folder, "2026-10-02T07:00:00Z", cfg), "record.latest")
    assert latest.status == FAILURE and "The job reported" in latest.message and "no new entry" in latest.message


# ---------------------------------------------------------------- source freshness
class _Provider:
    def __init__(self, name="fred", live=True, release_dated=()):
        self.name, self.is_live, self.release_dated = name, live, set(release_dated)


def _series(last, periods=30, freq="B"):
    return pd.Series(1.0, index=pd.date_range(end=last, periods=periods, freq=freq))


def _raw(**last):
    base = {
        "equity": "2026-10-01",
        "vix": "2026-09-30",
        "hy_bond": "2026-10-01",
        "ig_bond": "2026-10-01",
        "treasury": "2026-10-01",
        "us10y": "2026-09-30",
        "us2y": "2026-09-30",
        "breakeven10": "2026-09-30",
    }
    raw = {name: _series(day) for name, day in {**base, **{k: v for k, v in last.items() if k in base}}.items()}
    raw["claims"] = _series(last.get("claims", "2026-09-24"), 20, "7D")  # release-dated: indexed by release day
    raw["indpro"] = _series(last.get("indpro", "2026-09-16"), 12, pd.DateOffset(months=1))
    raw["cpi"] = _series(last.get("cpi", "2026-09-11"), 12, pd.DateOffset(months=1))
    return raw


NOW = pd.Timestamp("2026-10-01T22:40:00Z")  # the first publication run


def _freshness(raw, release_dated=("claims", "indpro", "cpi"), settings=None, now=NOW):
    check = health.check_freshness(raw, _Provider(release_dated=release_dated), settings or load_settings(), now)
    return check, {r["name"]: r for r in check.details["series"]}


def test_normal_release_calendar_is_fresh():
    check, rows = _freshness(_raw())
    assert check.status == OK, check.message
    assert rows["vix"]["age"] == 1 and rows["equity"]["age"] == 0  # FRED posts a day late: normal


def test_a_stale_series_is_named_with_its_age():
    check, rows = _freshness(_raw(vix="2026-09-25"))  # 4 sessions behind
    assert check.status == WARNING
    assert "vix (last 2026-09-25, 4 session(s) behind)" in check.message
    assert rows["vix"]["status"] == WARNING and rows["us10y"]["status"] == OK
    assert _freshness(_raw(vix="2026-09-23"))[0].status == FAILURE  # 6 sessions behind


def test_an_etf_one_session_behind_is_a_warning():
    assert _freshness(_raw(equity="2026-09-30"))[1]["equity"]["status"] == WARNING


def test_weekly_claims_follow_their_thursday_release():
    assert _freshness(_raw(claims="2026-09-24"))[1]["claims"]["status"] == OK  # one week old
    stale = _freshness(_raw(claims="2026-09-10"), now=NOW)[1]["claims"]
    assert stale["status"] == WARNING and stale["age"] == 21
    assert _freshness(_raw(claims="2026-09-03"), now=NOW)[1]["claims"]["status"] == FAILURE  # 28 days


def test_a_monthly_series_is_not_late_between_two_releases():
    # CPI of August was released on 2026-09-11; on 2026-10-10 (29 days) the next one is still not due
    _, rows = _freshness(_raw(cpi="2026-09-11"), now=pd.Timestamp("2026-10-10T22:40:00Z"))
    assert rows["cpi"]["status"] == OK and rows["cpi"]["age"] == 29
    _, rows = _freshness(_raw(cpi="2026-08-12"), now=pd.Timestamp("2026-10-10T22:40:00Z"))
    assert rows["cpi"]["status"] == WARNING and rows["cpi"]["age"] == 59


def test_a_period_dated_monthly_series_counts_from_its_month_end_and_lag():
    raw = _raw()
    raw["indpro"] = _series("2026-08-01", 12, "MS")  # August, dated on the 1st; known 2026-08-31 + 17 days
    _, rows = _freshness(raw, release_dated=("claims", "cpi"))
    assert rows["indpro"]["age"] == (NOW.tz_localize(None).normalize() - pd.Timestamp("2026-09-17")).days


def test_an_empty_series_is_a_failure():
    raw = _raw()
    raw["vix"] = raw["vix"].iloc[0:0]
    check, rows = _freshness(raw)
    assert check.status == FAILURE and "vix (no data)" in check.message and rows["vix"]["last"] == "none"


def test_freshness_thresholds_live_in_settings():
    loose = load_settings()
    loose["health"]["freshness"]["overrides"]["equity"] = {"warn": 3, "fail": 6}
    assert _freshness(_raw(equity="2026-09-30"), settings=loose)[1]["equity"]["status"] == OK


def test_degradation_is_reported():
    settings = load_settings()
    raw = _raw()
    assert health.check_path(raw, _Provider(release_dated=("claims", "indpro", "cpi")), settings).status == OK
    revised = health.check_path(raw, _Provider(release_dated=("claims",)), settings)
    assert revised.status == WARNING and "indpro" in revised.message and "cpi" in revised.message
    assert revised.details["series_source"]["claims"] == "alfred" and revised.details["series_source"]["vix"] == "fred"
    assert revised.details["series_source"]["equity"] == "tiingo"
    assert health.check_path(raw, _Provider(live=False), settings).status == FAILURE
    off = copy.deepcopy(settings)
    off["data"]["point_in_time"] = False
    assert health.check_path(raw, _Provider(release_dated=()), off).status == OK


def test_the_report_holds_dates_and_names_only():
    check, _ = _freshness(_raw(vix="2026-09-25"))
    assert set(check.details["series"][0]) == {"name", "source", "frequency", "last", "age", "unit", "status"}


# ---------------------------------------------------------------- the run record
class _Pipe:
    def __init__(self, settings, raw, provider):
        self.settings, self.raw, self.provider = settings, raw, provider


def _pipe(tmp_path, **last):
    settings = load_settings(overrides={"publish": {"dir": str(tmp_path)}})
    return _Pipe(settings, _raw(**last), _Provider(release_dated=("claims", "indpro", "cpi")))


def test_record_run_writes_next_to_the_entry_without_touching_it(tmp_path):
    folder = _entries(tmp_path, ["2026-09-30", "2026-10-01"])
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    report = health.record_run(_pipe(folder), folder / "2026-10-01.json", NOW, folder)
    assert report.status == OK
    after = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
    assert after == before  # the entry, index.csv and proofs are byte-identical
    record = json.loads((folder / "health" / "2026-10-01.json").read_text())
    assert record["kind"] == "health" and record["status"] == OK
    assert record["entry"] == {"date": "2026-10-01", "sha256": read_live(folder).last["sha256"]}
    assert read_live(folder).chain_ok


def test_a_degraded_day_is_labelled_in_its_record(tmp_path):
    folder = _entries(tmp_path, ["2026-10-01"])
    report = health.record_run(_pipe(folder, vix="2026-09-22"), folder / "2026-10-01.json", NOW, folder)
    assert report.status == FAILURE
    record = json.loads((folder / "health" / "2026-10-01.json").read_text())
    assert record["status"] == FAILURE
    assert any(c["name"] == "sources.freshness" and "vix" in c["message"] for c in record["checks"])


def test_publishing_nothing_on_a_market_day_is_a_failure(tmp_path):
    folder = _entries(tmp_path, ["2026-09-30"])  # the source never reached 10-01, so publish returned None
    report = health.record_run(_pipe(folder), None, NOW, folder)
    run = _status(report.checks, "run.entry")
    assert run.status == FAILURE and "2026-10-01" in run.message
    assert (folder / "health" / "2026-10-01.json").exists()


def test_publishing_nothing_on_a_holiday_is_fine(tmp_path):
    folder = _entries(tmp_path, ["2024-11-27"])
    run = _status(health.record_run(_pipe(folder), None, pd.Timestamp("2024-11-28T22:40:00Z"), folder).checks, "run.entry")
    assert run.status == OK


def test_a_noop_rerun_does_not_overwrite_the_days_record(tmp_path):
    folder = _entries(tmp_path, ["2026-10-01"])
    health.record_run(_pipe(folder), folder / "2026-10-01.json", NOW, folder)
    first = (folder / "health" / "2026-10-01.json").read_bytes()
    health.record_run(_pipe(folder, vix="2026-09-01"), None, NOW + pd.Timedelta(hours=1), folder)
    assert (folder / "health" / "2026-10-01.json").read_bytes() == first


def test_run_summary_reads_only_this_runs_record(tmp_path):
    folder = _entries(tmp_path, ["2026-10-01"])
    assert health.run_summary(folder, NOW) is None
    health.record_run(_pipe(folder), folder / "2026-10-01.json", NOW, folder)
    assert health.run_summary(folder, NOW + pd.Timedelta(minutes=20)).status == OK
    assert health.run_summary(folder, NOW + pd.Timedelta(days=1)) is None  # an old record is not this run's


# ---------------------------------------------------------------- failures and secrets
def test_scrub_removes_keys(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "abcdef0123456789")
    text = (
        "Client error for url 'https://api.stlouisfed.org/fred/series/observations?series_id=VIXCLS&api_key=abcdef0123456789&x=1'"
    )
    out = health.scrub(text + " Authorization: Token tok_1234567890abcdef and abcdef0123456789")
    assert "abcdef0123456789" not in out and "tok_1234567890abcdef" not in out
    assert "series_id=VIXCLS" in out and "api_key=***" in out


def _http_error(url, status=429):
    request = httpx.Request("GET", url)
    return httpx.HTTPStatusError(
        f"Client error '{status}' for url '{url}'", request=request, response=httpx.Response(status, request=request)
    )


def test_a_failure_names_the_series_and_hides_the_key(monkeypatch):
    monkeypatch.setenv("TIINGO_API_KEY", "t1ing0secretvalue")
    fred = health.describe_failure(
        _http_error("https://api.stlouisfed.org/fred/series/observations?series_id=VIXCLS&api_key=zzzzzzzz1234")
    )
    assert fred["error_class"] == "HTTPStatusError" and fred["series"] == ["vix"] and fred["http_status"] == 429
    assert "zzzzzzzz1234" not in fred["message"]
    tiingo = health.describe_failure(_http_error("https://api.tiingo.com/tiingo/daily/hyg/prices?startDate=2000-01-03", 403))
    assert tiingo["series"] == ["hy_bond"] and tiingo["http_status"] == 403
    missing = health.describe_failure(ValueError("Provider 'fred' is missing series: claims, cpi"))
    assert missing["series"] == ["claims", "cpi"]
    wrapped = RuntimeError("boom")
    wrapped.__cause__ = _http_error("https://api.stlouisfed.org/fred/series/observations?series_id=ICSA&api_key=k")
    assert health.describe_failure(wrapped)["series"] == ["claims"]


def test_report_failure_writes_the_job_summary(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("FRED_API_KEY", "abcdef0123456789")
    health.report_failure(
        _http_error("https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key=abcdef0123456789")
    )
    text = summary.read_text() + capsys.readouterr().out
    assert "HTTPStatusError" in text and "us10y" in text and "::error" in text
    assert "abcdef0123456789" not in text


def test_publish_reports_a_failure_and_still_fails(monkeypatch, tmp_path, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    def boom(pipeline, model=None, out_dir=None):
        raise _http_error("https://api.stlouisfed.org/fred/series/observations?series_id=T10YIE&api_key=k")

    monkeypatch.setattr("pfe_drai.publish.publish", boom)
    with pytest.raises(httpx.HTTPStatusError):
        main(["--provider", "fred", "publish"])
    assert "breakeven10" in summary.read_text()


# ---------------------------------------------------------------- CLI
def test_cli_exit_codes_and_json(tmp_path, capsys):
    folder = _entries(tmp_path, ["2026-09-30", "2026-10-01"])
    with pytest.raises(SystemExit) as ok:
        main(["health", "--offline", "--folder", str(folder), "--now", "2026-10-02T06:30:00Z", "--json"])
    assert ok.value.code == 0
    assert json.loads(capsys.readouterr().out)["status"] == OK
    with pytest.raises(SystemExit) as failed:
        main(
            [
                "health",
                "--offline",
                "--folder",
                str(folder),
                "--now",
                "2026-10-03T07:00:00Z",
                "--markdown",
                str(tmp_path / "out.md"),
            ]
        )
    assert failed.value.code == 2
    assert "2026-10-02" in capsys.readouterr().out
    assert "Daily job health: failure" in (tmp_path / "out.md").read_text()
    with pytest.raises(SystemExit) as warned:
        main(["health", "--offline", "--folder", str(tmp_path / "empty"), "--now", "2026-10-02T06:30:00Z"])
    assert warned.value.code == 1


def test_cli_without_live_provider_says_the_sources_were_not_checked(tmp_path, capsys):
    folder = _entries(tmp_path, ["2026-10-01"])
    with pytest.raises(SystemExit) as ok:
        main(["health", "--folder", str(folder), "--now", "2026-10-02T06:30:00Z"])
    assert ok.value.code == 0
    assert "not checked" in capsys.readouterr().out


def test_run_summary_exits_nonzero_only_on_a_failure(tmp_path, capsys):
    folder = _entries(tmp_path, ["2026-10-01"])
    health.record_run(_pipe(folder, vix="2026-09-22"), folder / "2026-10-01.json", pd.Timestamp.now(tz="UTC"), folder)
    with pytest.raises(SystemExit) as failed:
        main(["health", "--run-summary", "--folder", str(folder)])
    assert failed.value.code == 1


# ---------------------------------------------------------------- settings and the model
def test_health_settings_do_not_change_the_model_fingerprint(cfg):
    other = copy.deepcopy(cfg)
    other["health"]["due_after_close_hours"] = 1
    other["health"]["freshness"]["daily"]["warn"] = 9
    assert config_fingerprint(other) == config_fingerprint(cfg)
    assert "health" not in ("features", "regimes", "models", "validation")


# ---------------------------------------------------------------- the public page
def _page(tmp_path, cfg, lang="en", records=None, days=("2026-09-30", "2026-10-01")):
    folder = _entries(tmp_path, list(days))
    return render(read_live(folder), {}, None, {}, cfg, lang, health=records)


def test_the_page_checks_freshness_in_the_readers_browser(tmp_path, cfg):
    page = _page(tmp_path, cfg)
    assert 'id="freshness"' in page and "isOpen" in page
    data = json.loads(page.split('id="freshness" data-cfg="')[1].split('">')[0].replace("&quot;", '"'))
    assert data["last"] == "2026-10-01" and data["graceHours"] == 9 and data["closeHour"] == 21
    assert "2026-11-26" in data["holidays"] and "2026-04-03" in data["holidays"]  # Thanksgiving, Good Friday
    assert "{expected}" in data["labels"]["late"] and "back-filled" in data["labels"]["late"]


def test_the_page_stays_deterministic_and_bilingual(tmp_path, cfg):
    en, fr = _page(tmp_path / "a", cfg), _page(tmp_path / "b", cfg, "fr")
    assert en == _page(tmp_path / "a", cfg)  # no build time in the page
    assert "Latest entry" in en and "Dernière entrée" in fr and "jamais rattrapé" in fr


def test_a_degraded_day_is_labelled_on_the_page(tmp_path, cfg):
    stale = {
        "name": "sources.freshness",
        "status": WARNING,
        "message": "x",
        "details": {"series": [{"name": "vix", "last": "2026-09-28", "status": WARNING}]},
    }
    records = {"2026-10-01": {"status": WARNING, "checks": [stale]}}
    en = _page(tmp_path / "a", cfg, records=records)
    assert "Data warning on 2026-10-01" in en and "vix (2026-09-28)" in en and "warnmark" in en
    fr = _page(tmp_path / "b", cfg, "fr", records=records)
    assert "Alerte données le 01/10/2026" in fr and "séries en retard" in fr
    clean = _page(tmp_path / "c", cfg, records={"2026-10-01": {"status": OK, "checks": []}})
    assert "Data warning on" not in clean and '<span class="warnmark"' not in clean
