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


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=resolve(".")
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - publishing must not fail because git is missing
        return "unknown"


def publish(pipeline, model: str | None = None, out_dir: str | Path | None = None) -> Path:
    settings = pipeline.settings
    state = pipeline.state(model)
    folder = resolve(out_dir or settings["publish"]["dir"])
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        **state.to_dict(),
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "code_version": _git_sha(),
    }
    index_path = folder / "index.csv"
    previous_hash = ""
    if index_path.exists():
        rows = list(csv.DictReader(index_path.open(encoding="utf-8")))
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
