"""Global board: every published region side by side, and the challenger scorecard, read from the track record.

Nothing is recomputed: each number is the one published that evening in track_record/ (US) or
track_record/<region>/ (docs/REGIONS.md), with its hash chain re-checked by `read_live`. A region appears
once its pre-registered rule is passed (`publish.enabled`); the euro area stays out while it is experimental.

"In this regime since" counts the published days only: when the current regime goes back to the region's
first published day, the board says so ("since the record began") instead of guessing an earlier start.
"""

import json
from pathlib import Path

import pandas as pd

from ..config import DEFAULT_REGION, available_regions, load_settings, resolve
from .record import LiveRecord, read_live

# Display order of the regions; one not listed here comes after them, alphabetically.
ORDER = ["us", "uk", "japan", "euro", "em"]

# A region whose latest entry is this many business days older than the newest one is flagged as late.
LATE_BUSINESS_DAYS = 3


def published_regions(settings: dict | None = None) -> list[tuple[str, dict]]:
    """(region, settings) of the US and of every region whose publication is switched on, US first."""
    us = settings if settings is not None and not settings.get("region") else load_settings()
    out = [(DEFAULT_REGION, us)]
    for region in sorted(available_regions(), key=lambda r: (ORDER.index(r) if r in ORDER else len(ORDER), r)):
        if region == DEFAULT_REGION:
            continue
        s = load_settings(region=region)
        if s["publish"].get("enabled", False):
            out.append((region, s))
    return out


def _payload(folder: Path, live: LiveRecord) -> dict:
    if not live.last:
        return {}
    path = folder / live.last["file"]
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _run(live: LiveRecord) -> tuple[str | None, int, bool]:
    """Start of the current regime in the published days, its length in published days, and whether it
    reaches back to the first published day (so it may have started earlier)."""
    entries = [e for e in live.entries if e.get("regime")]
    if not entries:
        return None, 0, False
    regime, n = entries[-1]["regime"], 0
    for e in reversed(entries):
        if e["regime"] != regime:
            break
        n += 1
    return entries[-n]["date"], n, n == len(entries)


def region_row(region: str, folder: Path, base: Path | None = None) -> dict:
    """One region's latest published day, as published."""
    live = read_live(folder)
    row = {
        "region": region,
        "folder": folder.relative_to(base).as_posix() if base and folder.is_relative_to(base) else None,
        "days": len(live.entries),
        "first_day": live.first,
        "chain_ok": live.chain_ok,
        "problems": len(live.problems),
        "anchored": sum(e["ots"] == "bitcoin" for e in live.entries),
    }
    if not live.entries:
        return {**row, "date": None}
    last, payload = live.last, _payload(folder, live)
    probs = payload.get("probabilities") or {}
    previous = payload.get("previous") or {}
    prev_probs = previous.get("probabilities") or {}
    since, run_days, from_start = _run(live)
    p_stress = last.get("p_stress")
    return {
        **row,
        "date": last["date"],
        "file": last["file"],
        "regime": last.get("regime"),
        "p_regime": probs.get(last.get("regime")),
        "p_stress": p_stress,
        "alarm_on": last.get("alarm_on"),
        "alarm_since": last.get("alarm_since"),
        "regime_since": since,
        "regime_days": run_days,
        "regime_since_record_start": from_start,
        "week_ago_date": previous.get("date"),
        "week_ago_regime": previous.get("regime"),
        "p_stress_change": None if p_stress is None or "stress" not in prev_probs else p_stress - prev_probs["stress"],
        "model_version": last.get("model_version"),
        "is_live_data": payload.get("is_live_data"),
    }


def _rebase(path: str, us_dir: str, records_dir: Path) -> Path:
    """A folder of the track record (track_record/uk) read under `records_dir` instead of the repository's."""
    rel = Path(path).relative_to(Path(us_dir)) if Path(path).is_relative_to(Path(us_dir)) else None
    return records_dir / rel if rel is not None else resolve(path)


def board(settings: dict | None = None, records_dir: Path | None = None) -> dict:
    """Every published region's latest day, with a `late` flag for one well behind the newest.

    `records_dir`: the US track record folder (default: publish.dir); the regional folders are read under it,
    where the daily job writes them (track_record/<region>/).
    """
    regions = published_regions(settings)
    us_dir = regions[0][1]["publish"]["dir"]
    base = Path(records_dir) if records_dir else resolve(us_dir)
    rows = [region_row(r, _rebase(s["publish"]["dir"], us_dir, base), base) for r, s in regions]
    dates = [r["date"] for r in rows if r["date"]]
    newest = max(dates) if dates else None
    for r in rows:
        behind = len(pd.bdate_range(r["date"], newest)) - 1 if r["date"] and newest else None
        r["late"] = behind is not None and behind >= LATE_BUSINESS_DAYS
    return {"newest": newest, "regions": rows}


def read_scorecard(settings: dict, records_dir: Path | None = None) -> dict | None:
    """The challenger scorecard as the daily job wrote it (scorecard.json), or None before the first one.

    Adds `folder`: where it lies relative to the US track record folder, for the page's links.
    """
    us_dir = settings["publish"]["dir"]
    base = Path(records_dir) if records_dir else resolve(us_dir)
    folder = _rebase(settings.get("challengers", {}).get("dir", "track_record/challengers"), us_dir, base)
    path = folder / "scorecard.json"
    if not path.exists():
        return None
    card = json.loads(path.read_text(encoding="utf-8"))
    card["folder"] = folder.relative_to(base).as_posix() if folder.is_relative_to(base) else None
    return card
