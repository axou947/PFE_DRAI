"""Daily publication of the regime: one JSON file per day, hashed and externally timestamped.

A git commit date is easy to change, so each file also gets:
- a SHA-256 hash appended to track_record/index.csv (tamper-evident chain), and
- an OpenTimestamps proof (.ots) when the `ots` command is installed
  (pip install opentimestamps-client), which anchors the hash in Bitcoin.
"""

import csv
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from ..config import resolve
from ..validation import rule_fingerprint

#: Settings that decide the model's numbers. A new backtest record is written when one changes.
_CONFIG_KEYS = ("features", "regimes", "models", "validation")
_DATA_KEYS = ("start", "point_in_time", "publication_lag_days", "fred_fallback")


def config_fingerprint(settings: dict) -> str:
    """SHA-256 of every setting that changes the backtest (data source and end date excluded)."""
    config = {key: settings[key] for key in _CONFIG_KEYS}
    config["data"] = {key: settings["data"].get(key) for key in _DATA_KEYS}
    return hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()


def model_version(settings: dict) -> str | None:
    """Human name of the model configuration (models.version), shown next to its fingerprint."""
    return settings["models"].get("version")


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=resolve(".")
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - publishing must not fail because git is missing
        return "unknown"


class NotLiveDataError(RuntimeError):
    """Raised when publishing would put simulated data in the track record."""


def publish(pipeline, model: str | None = None, out_dir: str | Path | None = None) -> Path | None:
    """Write the latest regime. Returns None when that date is already published (holidays)."""
    settings = pipeline.settings
    state = pipeline.state(model)
    if settings["publish"].get("require_live_data", True) and not state.is_live_data:
        raise NotLiveDataError(
            f"Data provider '{state.data_provider}' is not fully live: refusing to publish simulated data. "
            "Run with --provider fred and set FRED_API_KEY and TIINGO_API_KEY."
        )
    folder = resolve(out_dir or settings["publish"]["dir"])
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        **state.to_dict(),
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "code_version": _git_sha(),
        "episode_rule_sha256": rule_fingerprint(settings),
        # Which model made this day: the page shows when it changed (docs/TRACK_RECORD.md).
        "model_version": model_version(settings),
        "config_sha256": config_fingerprint(settings),
    }
    index_path = folder / "index.csv"
    previous_hash = ""
    if index_path.exists():
        rows = list(csv.DictReader(index_path.open(encoding="utf-8")))
        if any(row["date"] == payload["date"] for row in rows):
            return None  # no new market day since the last run
        previous_hash = rows[-1]["sha256"] if rows else ""
    payload["previous_sha256"] = previous_hash
    body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    path = folder / f"{payload['date']}.json"
    path.write_text(body + "\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    new_file = not index_path.exists()
    with index_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(["date", "regime", "p_regime", "model", "data_provider", "sha256"])
        writer.writerow(
            [payload["date"], state.regime, f"{state.probabilities[state.regime]:.4f}", state.model, state.data_provider, digest]
        )

    if settings["publish"].get("opentimestamps") and shutil.which("ots"):
        subprocess.run(["ots", "stamp", str(path)], check=False)
    return path
