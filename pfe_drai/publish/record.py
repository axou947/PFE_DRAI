"""The track record behind the public page: the live daily record and the frozen backtest record.

Two records, never mixed:
- **live**: the daily JSON files `publish` writes after each US close (track_record/<date>.json),
  hash-chained in index.csv and stamped with OpenTimestamps. Read here, never rewritten.
- **backtest**: one JSON per configuration (track_record/backtest/<date>.json), written once by
  `record_backtest` the first time the publication runs with that configuration: every stress
  episode 2009-today with its detection latency, every alarm, the summary metrics and the daily
  P(stress). It is out-of-sample (walk-forward), but computed after the fact, and the model was
  chosen with these episodes known (docs/DETECTION_V2.md): it is evidence, not a live result.

Market prices are not published (data licences): only model outputs, episode dates and drawdowns.
"""

import csv
import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..validation import rule_fingerprint, stress_signal
from ..validation.calibration import json_number, to_json
from ..validation.metrics import alarm_spells, latencies
from .snapshot import NotLiveDataError, _git_sha, config_fingerprint, model_version

# OpenTimestamps attestation tags (opentimestamps.core.notary): a proof holds the Bitcoin one once
# `ots upgrade` has completed it, a few hours after `ots stamp`; until then only calendar promises.
_BITCOIN_TAG = bytes.fromhex("0588960d73d71901")
_PENDING_TAG = bytes.fromhex("83dfe30d2ef90c8e")


def ots_status(path: Path) -> str:
    """'bitcoin' (anchored in a Bitcoin block), 'pending' (calendar promise only) or 'missing'."""
    proof = path.with_name(path.name + ".ots")
    if not proof.exists():
        return "missing"
    data = proof.read_bytes()
    if _BITCOIN_TAG in data:
        return "bitcoin"
    return "pending" if _PENDING_TAG in data else "missing"


def stamp(path: Path, settings: dict) -> None:
    if settings["publish"].get("opentimestamps") and shutil.which("ots"):
        subprocess.run(["ots", "stamp", str(path)], check=False)


def _day(value) -> str | None:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).date().isoformat()


def _int(value) -> int | None:
    return None if value is None or pd.isna(value) else int(value)


# ---------------------------------------------------------------- backtest record
def backtest_record(pipeline, model: str | None = None) -> dict:
    """Every episode, every alarm and the summary metrics of the walk-forward backtest."""
    settings = pipeline.settings
    model = model or settings["models"]["default"]
    cfg = settings["validation"]
    probs = pipeline.probabilities(model)
    score = pipeline.alarm_score(model)
    result = pipeline.evaluate(model)
    signal = stress_signal(score, cfg["stress_probability_threshold"], cfg["confirm_days"])
    # Every episode, also one already under way on the first day: an alarm inside it is not false.
    spells = alarm_spells(signal, pipeline.episodes, settings, score)
    calibration = to_json(result["calibration"])
    combination = settings["models"].get("combined", {}).get("stress_combination", "max") if model == "combined" else "raw"
    return {
        "kind": "backtest",
        "model": model,
        "model_version": model_version(settings),
        "stress_sources": settings["models"].get("combined", {}).get("stress_sources") if model == "combined" else None,
        "combination": combination,
        "data_provider": pipeline.provider.name,
        "is_live_data": pipeline.provider.is_live,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "code_version": _git_sha(),
        "config_sha256": config_fingerprint(settings),
        "episode_rule_sha256": rule_fingerprint(settings),
        "period": {"start": _day(probs.index[0]), "end": _day(probs.index[-1]), "days": int(len(probs))},
        "rules": {
            "alarm_threshold": cfg["stress_probability_threshold"],
            "confirm_days": cfg["confirm_days"],
            "detection_window_days": cfg["episodes"]["detection_window_days"],
            "lookback_days": cfg["episodes"]["lookback_days"],
            "calibration_horizon_days": cfg["calibration"]["target_horizon_days"],
            "drawdown_threshold": cfg["episodes"]["drawdown_threshold"],
            "vol_quantile": cfg["episodes"]["vol_quantile"],
        },
        "targets": dict(cfg["targets"]),
        "metrics": {
            "n_episodes": result["n_episodes"],
            "detected": result["detected"],
            "median_latency": json_number(result["median_latency"]),
            "median_latency_all": json_number(result["median_latency_all"]),
            "false_positives_per_year": json_number(result["false_positives_per_year"]),
            "false_alarm_share": json_number(result["false_alarm_share"]),
            "switches_per_year": json_number(result["switches_per_year"]),
            "n_alarms": int(len(spells)),
            "n_false_alarms": int(spells["false_alarm"].sum()) if len(spells) else 0,
            **{k: calibration[k] for k in ("brier", "ece", "log_loss", "brier_skill", "base_rate", "mean_p", "n_days")},
        },
        "reliability": calibration["reliability"],
        "episodes": [
            {
                "start": _day(row["start"]),
                "end": _day(row["end"]),
                "trigger": row["trigger"],
                "max_drawdown": json_number(float(row["max_drawdown"])),
                "latency_days": _int(row["latency_days"]),
                "signal_date": _day(row["signal_date"]),
            }
            for _, row in result["episodes"].iterrows()
        ],
        "alarms": _spells_json(spells),
        # Daily model outputs for the chart: no market prices (data licences).
        "daily": {
            "date": [_day(d) for d in probs.index],
            "p_stress": [round(float(v), 4) for v in probs["stress"]],
            "score": [round(float(v), 4) for v in score.reindex(probs.index)],
            "alarm": [int(v) for v in signal.reindex(probs.index, fill_value=False)],
        },
    }


def _spells_json(spells: pd.DataFrame) -> list[dict]:
    return [
        {
            "start": _day(row["start"]),
            "end": _day(row["end"]),
            "days": int(row["days"]),
            "peak_score": json_number(row["peak_score"]),
            "episode_start": _day(row["episode_start"]),
            "false_alarm": bool(row["false_alarm"]),
            "open": bool(row["open"]),
        }
        for _, row in spells.iterrows()
    ]


def find_backtest(folder: Path, settings: dict) -> tuple[Path, dict] | None:
    """The backtest record written for the current configuration, if any (the earliest one)."""
    fingerprint = config_fingerprint(settings)
    for path in sorted((folder / "backtest").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("config_sha256") == fingerprint:
            return path, record
    return None


def list_backtests(folder: Path) -> list[dict]:
    """Every backtest record in `folder`/backtest, oldest first: one per model configuration ever published."""
    out = []
    for path in sorted((folder / "backtest").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        out.append(
            {
                "file": f"backtest/{path.name}",
                "generated_at": record.get("generated_at"),
                "model_version": record.get("model_version"),
                "config_sha256": record.get("config_sha256"),
                "period": record.get("period"),
                "metrics": record.get("metrics"),
            }
        )
    return sorted(out, key=lambda r: r["generated_at"] or "")


def record_backtest(pipeline, records_dir: Path, out_dir: Path | None = None) -> tuple[Path, dict, bool]:
    """Return the backtest record of the current configuration, writing it once if there is none.

    Never rewrites an existing record: a new configuration gets a new file, the old ones stay.
    Returns (path, record, written now).
    """
    settings = pipeline.settings
    out_dir = out_dir or records_dir
    for folder in dict.fromkeys([records_dir, out_dir]):
        found = find_backtest(folder, settings)
        if found:
            return (*found, False)
    official = out_dir.resolve() == records_dir.resolve()
    if official and settings["publish"].get("require_live_data", True) and not pipeline.provider.is_live:
        raise NotLiveDataError(
            f"Data provider '{pipeline.provider.name}' is not live: refusing to write a simulated backtest "
            "into the track record. Use --provider fred, or --out <folder> for a preview."
        )
    record = backtest_record(pipeline)
    folder = out_dir / "backtest"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{record['period']['end']}.json"
    path.write_text(json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    if official:
        stamp(path, settings)
    return path, record, True


# ---------------------------------------------------------------- live record
@dataclass
class LiveRecord:
    """The published days, checked: the hash chain and each day's external timestamp."""

    entries: list[dict] = field(default_factory=list)  # one per published day, oldest first
    chain_ok: bool = True
    problems: list[str] = field(default_factory=list)

    @property
    def first(self) -> str | None:
        return self.entries[0]["date"] if self.entries else None

    @property
    def last(self) -> dict | None:
        return self.entries[-1] if self.entries else None

    def alarm_series(self) -> pd.Series:
        return pd.Series(
            {pd.Timestamp(e["date"]): bool(e["alarm_on"]) for e in self.entries if e["alarm_on"] is not None}, dtype=bool
        )


def read_live(folder: Path) -> LiveRecord:
    """Read track_record/: every day of index.csv, its file re-hashed and its link to the previous day checked."""
    record = LiveRecord()
    index = folder / "index.csv"
    if not index.exists():
        return record
    previous = ""
    for row in csv.DictReader(index.open(encoding="utf-8")):
        path = folder / f"{row['date']}.json"
        entry = {"date": row["date"], "sha256": row["sha256"], "file": path.name, "ots": ots_status(path)}
        if not path.exists():
            record.chain_ok = False
            record.problems.append(f"{row['date']}: file missing")
            record.entries.append({**entry, "regime": row["regime"], "p_stress": None, "alarm_on": None, "hash_ok": False})
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        hash_ok = hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
        link_ok = payload.get("previous_sha256", "") == previous
        if not hash_ok:
            record.problems.append(f"{row['date']}: file does not match its sha256 in index.csv")
        if not link_ok:
            record.problems.append(f"{row['date']}: previous_sha256 does not match the day before")
        record.chain_ok &= hash_ok and link_ok
        alarm = payload.get("alarm") or {}
        record.entries.append(
            {
                **entry,
                "regime": payload.get("regime"),
                "p_stress": (payload.get("probabilities") or {}).get("stress"),
                "alarm_on": alarm.get("on"),
                "alarm_since": alarm.get("since"),
                "alarm_score": alarm.get("score"),
                "published_at": payload.get("published_at"),
                "code_version": payload.get("code_version"),
                "combination": (payload.get("calibration") or {}).get("combination"),
                "model_version": payload.get("model_version"),
                "config_sha256": payload.get("config_sha256"),
                "hash_ok": hash_ok and link_ok,
            }
        )
        previous = row["sha256"]
    return record


def live_scorecard(live: LiveRecord, episodes, index: pd.DatetimeIndex, settings: dict) -> dict:
    """Score the alarms as published (never recomputed) against the episodes dated since the first day.

    `index`: business days of the market data, to count latencies in business days as the backtest does.
    A day without a publication counts as no alarm. Episodes and false alarms whose window has not
    elapsed yet are marked pending, not missed.
    """
    if not live.entries:
        return {"episodes": [], "alarms": [], "missing_days": 0, "last_market_day": None}
    first = pd.Timestamp(live.first)
    days = index[index >= first]
    published = live.alarm_series()
    signal = published.reindex(days).fillna(False).astype(bool) if len(days) else published
    eps = [e for e in episodes if e.start >= first]
    lat = latencies(signal, eps, settings) if len(signal) else pd.DataFrame()
    lookback = settings["validation"]["episodes"]["lookback_days"]
    out_eps = []
    for _, row in lat.iterrows():
        status = "detected" if row["detected"] else ("missed" if row["window_complete"] else "pending")
        out_eps.append(
            {
                "start": _day(row["start"]),
                "end": _day(row["end"]),
                "trigger": row["trigger"],
                "max_drawdown": json_number(float(row["max_drawdown"])),
                "latency_days": _int(row["latency_days"]),
                "signal_date": _day(row["signal_date"]),
                "status": status,
            }
        )
    scores = pd.Series({pd.Timestamp(e["date"]): e.get("alarm_score") for e in live.entries}, dtype=float)
    spells = alarm_spells(signal, episodes, settings, scores.reindex(signal.index)) if len(signal) else pd.DataFrame()
    alarms = _spells_json(spells)
    for spell in alarms:
        # A false alarm is final once `lookback_days` have passed without an episode starting.
        start = pd.Timestamp(spell["start"])
        after = int((days > start).sum())
        spell["pending"] = spell["false_alarm"] and after < lookback
    return {
        "episodes": out_eps,
        "alarms": alarms,
        "missing_days": int((~days.isin(published.index)).sum()),
        "last_market_day": _day(days[-1]) if len(days) else None,
    }
