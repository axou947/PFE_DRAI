"""Daily job health: is the track record complete, intact and fed by fresh data?

The track record's promise is "one entry per market day, nothing missing, nothing rewritten". A day
the job did not publish counts as no alarm on the public page, so a silent failure (outage, expired
key, disabled workflow, a source that stops updating) would quietly damage the proof. This module
looks for those failures and says so. It never changes a published record.

Two kinds of checks, in one `Report` (exit code 0 ok, 1 warning, 2 failure):
- record checks need only `track_record/`: hash chain, the expected market day against the latest
  entry (NYSE calendar, so a holiday is not a miss), gaps, OpenTimestamps upgrades, timeliness;
- source checks need the data: freshness of each series against its own release calendar, and which
  path each series took (point-in-time, fallback). They run inside the publication job, which writes
  the result next to the entry (`track_record/health/<day>.json`, outside the hash chain) so the
  key-less health workflow and the public page can read it.

Missed-day policy: a day not published stays missing. The entry would otherwise be dated after the
fact. See docs/OPERATIONS.md.

Constraints: dates and series names only (no market prices), and exception text is scrubbed of keys.
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import nyse
from .data.catalog import CATALOG

OK, WARNING, FAILURE = "ok", "warning", "failure"
_RANK = {OK: 0, WARNING: 1, FAILURE: 2}
HEALTH_DIR = "health"
ISSUE_TITLE = "Daily job health"
_MAX_LISTED = 12  # dates or names printed in one message


# ---------------------------------------------------------------- report
@dataclass
class Check:
    name: str
    status: str
    message: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "message": self.message, "details": self.details}


@dataclass
class Report:
    generated_at: str
    expected_day: str | None
    latest_day: str | None
    checks: list[Check] = field(default_factory=list)

    @property
    def status(self) -> str:
        return max((c.status for c in self.checks), key=_RANK.__getitem__, default=OK)

    @property
    def exit_code(self) -> int:
        return _RANK[self.status]

    def problems(self) -> list[Check]:
        return [c for c in self.checks if c.status != OK]

    def to_dict(self) -> dict:
        return {
            "kind": "health",
            "status": self.status,
            "generated_at": self.generated_at,
            "expected_day": self.expected_day,
            "latest_day": self.latest_day,
            "checks": [c.to_dict() for c in self.checks],
        }

    def to_text(self) -> str:
        lines = [f"Daily job health: {self.status.upper()}  (expected day {self.expected_day}, latest entry {self.latest_day})"]
        for c in self.checks:
            lines.append(f"  [{c.status:<7}] {c.name}: {c.message}")
            lines.extend(f"      {row}" for row in _series_lines(c))
        return "\n".join(lines)

    def to_markdown(self) -> str:
        icon = {OK: "🟢", WARNING: "🟡", FAILURE: "🔴"}
        out = [
            f"## {icon[self.status]} Daily job health: {self.status}",
            "",
            f"Checked {self.generated_at}. Expected market day: **{self.expected_day}**. "
            f"Latest published entry: **{self.latest_day}**.",
            "",
            "| | Check | What |",
            "|---|---|---|",
        ]
        out += [f"| {icon[c.status]} | `{c.name}` | {c.message.replace('|', '/')} |" for c in self.checks]
        for c in self.checks:
            rows = c.details.get("series")
            if rows:
                out += [
                    "",
                    f"<details><summary>{c.name}: every series</summary>",
                    "",
                    "| Series | Source | Last data | Age | |",
                    "|---|---|---|---|---|",
                ]
                out += [
                    f"| {r['name']} | {r['source']} | {r['last']} | {r['age']} {r['unit']} | {icon[r['status']]} |" for r in rows
                ]
                out += ["", "</details>"]
        return "\n".join(out) + "\n"


def _series_lines(check: Check) -> list[str]:
    return [
        f"{r['name']:<10} {r['source']:<8} last {r['last']}  {r['age']} {r['unit']}  {r['status']}"
        for r in check.details.get("series", [])
        if r["status"] != OK
    ]


def _listed(items, limit: int = _MAX_LISTED) -> str:
    items = [str(i) for i in items]
    return ", ".join(items[:limit]) + (f" and {len(items) - limit} more" if len(items) > limit else "")


def _cfg(settings: dict) -> dict:
    return settings["health"]


def _day(value) -> str:
    return pd.Timestamp(value).date().isoformat()


def _aware(now=None) -> pd.Timestamp:
    """A UTC-aware moment; None is now, a naive one is read as UTC."""
    moment = pd.Timestamp(datetime.now(UTC) if now is None else now)
    return moment.tz_localize("UTC") if moment.tzinfo is None else moment.tz_convert("UTC")


# ---------------------------------------------------------------- secrets
_SECRET_QUERY = re.compile(r"(?i)\b(api[_-]?key|apikey|access[_-]?token|token|key)=[^&\s'\"<>)]+")
_SECRET_HEADER = re.compile(r"(?i)\b(Token|Bearer)\s+[A-Za-z0-9._~+/=-]{8,}")
_SECRET_ENV = re.compile(r"(?i)(key|token|secret|password)$")


def scrub(text: str) -> str:
    """Remove API keys from text that will be printed or written to an issue (README constraint 7).

    Covers `api_key=...` in URLs (httpx puts them in its error messages), `Token ...` headers, and
    the value of any environment variable whose name ends in KEY, TOKEN, SECRET or PASSWORD.
    """
    text = _SECRET_QUERY.sub(lambda m: f"{m.group(1)}=***", str(text))
    text = _SECRET_HEADER.sub(lambda m: f"{m.group(1)} ***", text)
    for name, value in os.environ.items():
        if _SECRET_ENV.search(name) and len(value) >= 6:
            text = text.replace(value, "***")
    return text


def describe_failure(exc: BaseException) -> dict:
    """What failed, for the job summary: error class, failing series, HTTP status, scrubbed message."""
    series: list[str] = []
    status = None
    seen = exc
    while seen is not None:
        series += [s for s in _failing_series(seen) if s not in series]
        response = getattr(seen, "response", None)
        status = status or getattr(response, "status_code", None)
        seen = seen.__cause__ or seen.__context__
    return {
        "error_class": type(exc).__name__,
        "series": series,
        "http_status": status,
        "message": scrub(str(exc))[:500],
    }


def _failing_series(exc: BaseException) -> list[str]:
    names = []
    request = getattr(exc, "request", None) if hasattr(exc, "response") else None
    url = getattr(request, "url", None)
    if url is not None:
        ident = url.params.get("series_id") or (url.path.split("/")[-2] if "/tiingo/daily/" in url.path else None)
        for name, series in CATALOG.items():
            if ident and ident.lower() in (v.lower() for v in series.source_ids.values()):
                names.append(name)
    match = re.search(r"is missing series: ([\w, ]+)", str(exc))
    if match:
        names += [n.strip() for n in match.group(1).split(",") if n.strip() in CATALOG]
    return names


def failure_markdown(info: dict) -> str:
    series = ", ".join(f"`{s}`" for s in info["series"]) or "not identified"
    http = f" (HTTP {info['http_status']})" if info["http_status"] else ""
    return (
        "## 🔴 The daily publication failed\n\n"
        f"- Error: `{info['error_class']}`{http}\n- Failing series: {series}\n- Message: {info['message']}\n\n"
        "No entry was written for this run. A missed day stays missing (docs/OPERATIONS.md).\n"
    )


def step_summary(markdown: str) -> None:
    """Append to the GitHub Actions job summary, when running there."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")


def report_failure(exc: BaseException) -> dict:
    """Loud failure in Actions: an error annotation and the job summary. Never raises."""
    info = describe_failure(exc)
    try:
        step_summary(failure_markdown(info))
        series = ",".join(info["series"]) or "unknown series"
        print(f"::error title=Daily publication failed::{info['error_class']} on {series}: {info['message']}".replace("\n", " "))
    except Exception:  # noqa: BLE001 - reporting must not hide the original error
        pass
    return info


# ---------------------------------------------------------------- record checks
def read_records(folder: Path) -> dict[str, dict]:
    """Health records written by the publication job, by the day they describe."""
    records = {}
    for path in sorted((folder / HEALTH_DIR).glob("*.json")):
        try:
            records[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            records[path.stem] = {"status": WARNING, "checks": [], "unreadable": True}
    return records


def due_at(session, settings: dict) -> datetime:
    """When the entry of a session must be out: its close plus `due_after_close_hours` (the job starts late at times)."""
    return nyse.session_close(session) + timedelta(hours=_cfg(settings)["due_after_close_hours"])


def _closures(after, until) -> list[str]:
    """Weekdays the exchange was closed in (after, until], with the reason."""
    out = []
    for day in pd.bdate_range(pd.Timestamp(after) + pd.Timedelta(days=1), pd.Timestamp(until)):
        name = nyse.holiday_name(day)
        if name:
            out.append(f"{_day(day)} ({name})")
    return out


def _crlf_files(folder: Path, live) -> list[str]:
    """Entries that only fail their hash because the file has Windows line endings (git core.autocrlf)."""
    found = []
    index = {e["date"]: e["sha256"] for e in live.entries}
    for day, digest in index.items():
        path = folder / f"{day}.json"
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            if hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest:
                found.append(day)
    return found


def check_integrity(live, folder: Path | None = None) -> Check:
    crlf = _crlf_files(folder, live) if folder is not None and not live.chain_ok else []
    if crlf:
        return Check(
            "record.integrity",
            FAILURE,
            f"{_listed(crlf)}: the file differs from index.csv only by Windows line endings (git core.autocrlf), "
            "not by content. Re-checkout the file with the .gitattributes of this repository (docs/OPERATIONS.md)",
            {"crlf": crlf, "problems": live.problems},
        )
    if live.chain_ok:
        return Check("record.integrity", OK, f"hash chain intact over {len(live.entries)} day(s)")
    return Check(
        "record.integrity",
        FAILURE,
        f"{len(live.problems)} integrity problem(s), nothing was repaired: {_listed(live.problems, 5)}",
        {"problems": live.problems},
    )


def check_latest(live, records: dict, now: pd.Timestamp, settings: dict) -> Check:
    """The latest entry against the market day that should have been published by now."""
    expected = nyse.last_closed_session(now)
    if not live.entries:
        return Check("record.latest", WARNING, "no entry published yet", {"expected": _day(expected)})
    latest = pd.Timestamp(live.last["date"])
    details = {"expected": _day(expected), "latest": _day(latest)}
    if latest > expected:
        return Check(
            "record.latest", WARNING, f"latest entry {_day(latest)} is after the last closed market day {_day(expected)}", details
        )
    if latest == expected:
        closed = _closures(latest, now.tz_localize(None).normalize())
        note = f"; no entry due since: market closed {_listed(closed)}" if closed else ""
        return Check("record.latest", OK, f"latest entry {_day(latest)} is the last market day{note}", details)
    missing = list(nyse.sessions(latest + pd.Timedelta(days=1), expected))
    pending = bool(missing) and _aware(now) < _aware(due_at(missing[-1], settings))
    lost = missing[:-1] if pending else missing
    details["missing"] = [_day(d) for d in missing]
    reasons = _reasons(records, missing)
    if pending and not lost:
        due = due_at(missing[-1], settings).strftime("%H:%M UTC")
        return Check(
            "record.latest", OK, f"entry for {_day(missing[-1])} not out yet, due by {due} (the job often starts late)", details
        )
    return Check(
        "record.latest",
        FAILURE,
        f"market day(s) without an entry: {_listed(_day(d) for d in lost)}; latest entry is {_day(latest)}{reasons}",
        details,
    )


def _reasons(records: dict, days) -> str:
    """The data problems the publication job recorded for missing days, when it ran at all."""
    found = []
    for day in days:
        for check in (records.get(_day(day)) or {}).get("checks", []):
            if check["status"] == FAILURE:
                found.append(f"{_day(day)} {check['name']}: {check['message']}")
    return f". The job reported: {_listed(found, 3)}" if found else ""


def check_gaps(live, settings: dict) -> Check:
    """Market days between the first and the latest entry with no entry, and entries on closed days."""
    if len(live.entries) < 2:
        return Check("record.gaps", OK, "no gap")
    published = {e["date"] for e in live.entries}
    acknowledged = {str(k) for k in (_cfg(settings).get("acknowledged_gaps") or {})}
    first, last = pd.Timestamp(live.first), pd.Timestamp(live.last["date"])
    gaps = [_day(d) for d in nyse.sessions(first, last) if _day(d) not in published]
    open_gaps = [d for d in gaps if d not in acknowledged]
    off_calendar = [d for d in sorted(published) if not nyse.is_session(d)]
    details = {"gaps": gaps, "acknowledged": [d for d in gaps if d in acknowledged], "off_calendar": off_calendar}
    if open_gaps or off_calendar:
        parts = []
        if open_gaps:
            parts.append(
                f"missed market day(s) {_listed(open_gaps)} (stay missing; acknowledge them in health.acknowledged_gaps)"
            )
        if off_calendar:
            parts.append(f"entry dated on a closed day: {_listed(off_calendar)} (calendar or data problem)")
        return Check("record.gaps", WARNING, "; ".join(parts), details)
    note = f" ({len(gaps)} acknowledged)" if gaps else ""
    return Check("record.gaps", OK, f"no unexplained gap{note}", details)


def check_timestamps(live, now: pd.Timestamp, settings: dict) -> Check:
    """Entries older than `ots_upgrade_days` whose proof is not anchored in Bitcoin yet."""
    if not settings["publish"].get("opentimestamps"):
        return Check("record.ots", OK, "OpenTimestamps is off")
    limit = _cfg(settings)["ots_upgrade_days"]
    today = now.tz_localize(None).normalize()
    stuck = [e for e in live.entries if (today - pd.Timestamp(e["date"])).days > limit and e["ots"] != "bitcoin"]
    if not stuck:
        return Check("record.ots", OK, f"every entry older than {limit} day(s) is anchored in Bitcoin")
    missing = [e["date"] for e in stuck if e["ots"] == "missing"]
    pending = [e["date"] for e in stuck if e["ots"] == "pending"]
    parts = []
    if missing:
        parts.append(f"no timestamp proof: {_listed(missing)}")
    if pending:
        parts.append(f"not anchored in Bitcoin yet: {_listed(pending)}")
    return Check(
        "record.ots", WARNING, f"older than {limit} day(s), " + "; ".join(parts), {"missing": missing, "pending": pending}
    )


def check_timeliness(live, settings: dict) -> Check:
    """The latest entry published before the next session opened (its data was still the news)."""
    if not live.entries:
        return Check("record.timeliness", OK, "no entry yet")
    last = live.last
    stamp = last.get("published_at")
    if not stamp:
        return Check("record.timeliness", OK, "publication time not recorded")
    published = _aware(stamp)
    deadline = _aware(nyse.next_open(last["date"]))
    late_by = (published - deadline).total_seconds() / 3600
    details = {"published_at": str(stamp), "deadline": deadline.isoformat()}
    if late_by > 0:
        return Check(
            "record.timeliness",
            WARNING,
            f"entry {last['date']} was published {late_by:.1f} h after the next market open: late, not back-dated",
            details,
        )
    return Check("record.timeliness", OK, f"entry {last['date']} published before the next market open", details)


def check_day_health(live, records: dict) -> Check:
    """What the publication job found about the data behind the latest entry."""
    if not live.entries:
        return Check("record.data", OK, "no entry yet")
    day = live.last["date"]
    record = records.get(day)
    if record is None:
        if records:
            return Check(
                "record.data", WARNING, f"no data-health record for entry {day}: the job did not write one", {"day": day}
            )
        return Check("record.data", OK, "no data-health record yet (written by the daily job from now on)", {"day": day})
    problems = [c for c in record.get("checks", []) if c["status"] != OK]
    if not problems:
        return Check("record.data", OK, f"data behind entry {day} was healthy", {"day": day})
    listed = _listed(f"{c['name']}: {c['message']}" for c in problems)
    return Check(
        "record.data", record.get("status", WARNING), f"entry {day} was published on degraded data. {listed}", {"day": day}
    )


def check_record(folder: Path, now, settings: dict) -> list[Check]:
    """Everything that needs only the track_record/ folder."""
    from .publish.record import read_live

    now = _aware(now)
    live = read_live(folder)
    records = read_records(folder)
    return [
        check_integrity(live, folder),
        check_latest(live, records, now, settings),
        check_gaps(live, settings),
        check_timestamps(live, now, settings),
        check_timeliness(live, settings),
        check_day_health(live, records),
    ]


# ---------------------------------------------------------------- source checks
def _frequency(name: str, series: pd.Series) -> str:
    if name in CATALOG:
        return CATALOG[name].frequency
    gap = series.index.to_series().diff().dt.days.median() if len(series) > 2 else 1
    return "daily" if gap <= 4 else "weekly" if gap <= 10 else "monthly"


def known_date(name: str, series: pd.Series, release_dated: set[str], lags: dict[str, int]) -> pd.Timestamp:
    """The day the latest value of a series was known, as the pipeline dates it (features.build.align).

    Release-dated series (ALFRED first releases) are indexed by that day. The others are indexed by
    their reference period: a monthly value counts from the end of the month, plus its publication lag.
    """
    last = series.index.max()
    if name in release_dated:
        return last
    if _frequency(name, series) == "monthly":
        last = last + pd.offsets.MonthEnd(0)
    return last + pd.Timedelta(days=lags.get(name, 0))


def _thresholds(settings: dict, name: str, frequency: str) -> tuple[int, int]:
    cfg = _cfg(settings)["freshness"]
    chosen = {**cfg[frequency], **(cfg.get("overrides") or {}).get(name, {})}
    return int(chosen["warn"]), int(chosen["fail"])


def _source_of(name: str, provider, release_dated: set[str], settings: dict) -> str:
    if provider.name == "fred":
        if name in release_dated:
            return "alfred"
        return "fred" if name in CATALOG and "fred" in CATALOG[name].source_ids else settings["data"].get("fred_fallback", "?")
    return provider.name


def check_freshness(raw: dict, provider, settings: dict, now: pd.Timestamp) -> Check:
    """Each series against its own release calendar: sessions behind for daily series, days since release otherwise."""
    expected = nyse.last_closed_session(now)
    today = now.tz_localize(None).normalize()
    lags = settings["data"].get("publication_lag_days", {})
    release_dated = set(getattr(provider, "release_dated", ()))
    rows = []
    for name, series in raw.items():
        series = series.dropna()
        frequency = _frequency(name, series)
        source = _source_of(name, provider, release_dated, settings)
        if series.empty:
            rows.append(
                {"name": name, "source": source, "frequency": frequency, "last": "none", "age": 0, "unit": "", "status": FAILURE}
            )
            continue
        known = known_date(name, series, release_dated, lags)
        if frequency == "daily":
            age, unit = nyse.sessions_between(known, expected), "session(s) behind"
        else:
            age, unit = max((today - known).days, 0), "day(s) since release"
        warn, fail = _thresholds(settings, name, frequency)
        status = FAILURE if age >= fail else WARNING if age >= warn else OK
        rows.append(
            {
                "name": name,
                "source": source,
                "frequency": frequency,
                "last": _day(series.index.max()),
                "age": age,
                "unit": unit,
                "status": status,
            }
        )
    bad = [r for r in rows if r["status"] != OK]
    worst = max((r["status"] for r in rows), key=_RANK.__getitem__, default=OK)
    if not bad:
        message = f"all {len(rows)} series are fresh"
    else:
        message = "stale: " + _listed(
            f"{r['name']} (last {r['last']}, {r['age']} {r['unit']})" if r["last"] != "none" else f"{r['name']} (no data)"
            for r in bad
        )
    return Check("sources.freshness", worst, message, {"series": rows, "expected_day": _day(expected)})


def check_path(raw: dict, provider, settings: dict) -> Check:
    """Which way each series came in: live source, ALFRED first releases, fallback."""
    release_dated = set(getattr(provider, "release_dated", ()))
    sources = {name: _source_of(name, provider, release_dated, settings) for name in raw}
    details = {"providers": sorted(set(sources.values())), "series_source": sources}
    problems = []
    status = OK
    if not provider.is_live:
        status = FAILURE
        problems.append(f"provider '{provider.name}' is not fully live (simulated or partly simulated data)")
    if provider.name == "fred" and settings["data"].get("point_in_time", True):
        revised = [n for n in raw if n in CATALOG and CATALOG[n].revised]
        late = [n for n in revised if n not in release_dated]
        if late:
            status = max(status, WARNING, key=_RANK.__getitem__)
            problems.append(f"{_listed(late)} not read as ALFRED first releases (revised values, not point-in-time)")
    if problems:
        return Check("sources.path", status, "; ".join(problems), details)
    return Check("sources.path", OK, f"live data from {', '.join(details['providers'])}", details)


def check_sources(raw: dict, provider, settings: dict, now) -> list[Check]:
    now = _aware(now)
    return [check_freshness(raw, provider, settings, now), check_path(raw, provider, settings)]


# ---------------------------------------------------------------- reports
def build_report(folder: Path, settings: dict, now=None, sources: list[Check] | None = None) -> Report:
    """Record checks (always) and source checks (when the data was read)."""
    from .publish.record import read_live

    moment = _aware(now)
    live = read_live(folder)
    return Report(
        generated_at=moment.strftime("%Y-%m-%d %H:%M UTC"),
        expected_day=_day(nyse.last_closed_session(moment)),
        latest_day=live.last["date"] if live.entries else None,
        checks=[*check_record(folder, moment, settings), *(sources or [])],
    )


def record_run(pipeline, entry: Path | None, now=None, folder: Path | None = None) -> Report:
    """Right after `publish`: check the data it used and write track_record/health/<day>.json.

    The file sits next to the entry, outside the hash chain: it describes the entry (it carries its
    SHA-256) but is not part of it, so a published day is never altered. A run that published nothing
    on a market day is a failure (a stale source looks exactly like a holiday to `publish`).
    """
    from .config import resolve
    from .publish.record import read_live

    settings = pipeline.settings
    moment = _aware(now)
    folder = folder or resolve(settings["publish"]["dir"])
    expected = nyse.last_closed_session(moment)
    checks = check_sources(pipeline.raw, pipeline.provider, settings, moment)
    live = read_live(folder)
    if entry is not None:
        day = json.loads(Path(entry).read_text(encoding="utf-8"))["date"]
        if pd.Timestamp(day) == expected:
            checks.append(Check("run.entry", OK, f"published {day}, the last market day"))
        else:
            checks.append(
                Check(
                    "run.entry",
                    WARNING,
                    f"published {day} but the last closed market day is {_day(expected)}: stale data or a late run",
                )
            )
        key = day
    else:
        latest = live.last["date"] if live.entries else None
        key = _day(expected)
        if latest == key or not nyse.is_session(expected):
            checks.append(Check("run.entry", OK, f"nothing to publish: latest entry {latest} is the last market day"))
        else:
            checks.append(
                Check(
                    "run.entry",
                    FAILURE,
                    f"no new entry for market day {key}: the source data did not reach it (latest entry {latest})",
                )
            )
    report = Report(
        generated_at=moment.strftime("%Y-%m-%d %H:%M UTC"),
        expected_day=_day(expected),
        latest_day=live.last["date"] if live.entries else None,
        checks=checks,
    )
    path = folder / HEALTH_DIR / f"{key}.json"
    if entry is not None or not path.exists():  # a no-op rerun must not overwrite the day's real record
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = report.to_dict()
        if entry is not None:
            payload["entry"] = {"date": key, "sha256": next((e["sha256"] for e in live.entries if e["date"] == key), None)}
        path.write_text(json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def run_summary(folder: Path, now=None, within_hours: float = 6) -> Report | None:
    """The record the job just wrote, for the end of the publish workflow (None when this run wrote none)."""
    moment = _aware(now)
    fresh = {}
    for key, record in read_records(folder).items():
        try:
            written = _aware(record.get("generated_at"))
        except (ValueError, TypeError):
            continue
        if timedelta(0) <= moment - written <= timedelta(hours=within_hours):
            fresh[key] = record
    if not fresh:
        return None
    record = fresh[max(fresh)]
    return Report(
        generated_at=record["generated_at"],
        expected_day=record.get("expected_day"),
        latest_day=record.get("latest_day"),
        checks=[Check(c["name"], c["status"], c["message"], c.get("details", {})) for c in record.get("checks", [])],
    )


def annotate(report: Report) -> None:
    """GitHub Actions annotations and job summary for a run's report."""
    step_summary(report.to_markdown())
    for check in report.problems():
        level = "error" if check.status == FAILURE else "warning"
        print(f"::{level} title={check.name}::{check.message}".replace("\n", " "))
