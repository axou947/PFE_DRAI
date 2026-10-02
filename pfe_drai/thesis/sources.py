"""What the thesis reads: the settings, the backtest records, the live record and the docs. Read-only."""

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..config import ROOT, load_settings
from ..publish.record import LiveRecord, read_live
from ..publish.snapshot import config_fingerprint


class ThesisError(RuntimeError):
    """The report cannot be built, or is inconsistent. `problems` lists every cause."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("\n".join(f"- {p}" for p in self.problems))


def version_key(version: str | None) -> str:
    """'v2.2' -> 'v2_2': a name usable in a placeholder."""
    return re.sub(r"\W+", "_", version or "unversioned")


def _git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=True, cwd=root)
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 - a missing git must not stop the report
        return ""


@dataclass
class Sources:
    root: Path
    settings: dict
    records_dir: Path
    backtests: dict[str, dict] = field(default_factory=dict)  # version key -> backtest record, oldest config first
    live: LiveRecord = field(default_factory=LiveRecord)
    current: str | None = None  # version key of the record that matches models.version (else the latest)
    meta: dict = field(default_factory=dict)

    @property
    def docs_dir(self) -> Path:
        return self.root / "docs"

    @property
    def thesis_dir(self) -> Path:
        return self.root / "docs" / "thesis"

    def backtest(self, key: str | None) -> dict:
        key = self.current if key in (None, "current") else key
        if key not in self.backtests:
            have = ", ".join(self.backtests) or "none"
            raise KeyError(f"no backtest record for version '{key}' (records: {have})")
        return self.backtests[key]

    def doc_commit(self, name: str) -> tuple[str, str]:
        """(short commit, date) of the last commit that touched docs/<name>; ('', '') without git."""
        out = _git(self.root, "log", "-1", "--format=%h %cs", "--", f"docs/{name}")
        short, _, day = out.partition(" ")
        return short, day

    def lookup(self, ref: str):
        """Resolve 'backtest.v2_2.metrics.brier', 'config.validation.targets...', 'meta.x' or 'live.x'."""
        head, _, rest = ref.partition(".")
        if head == "backtest":
            key, _, rest = rest.partition(".")
            node = self.backtest(key)
        elif head == "config":
            node = self.settings
        elif head == "meta":
            node = self.meta
        elif head == "live":
            node = live_facts(self.live)
        else:
            raise KeyError(f"unknown source '{head}' (backtest, config, meta, live)")
        for token in [p for p in rest.split(".") if p]:
            if isinstance(node, list):
                node = node[int(token)]
            elif isinstance(node, dict) and token in node:
                node = node[token]
            else:
                raise KeyError(f"'{ref}': no '{token}'")
        return node


def live_facts(live: LiveRecord) -> dict:
    last = live.last or {}
    return {
        "days": len(live.entries),
        "first_day": live.first,
        "last_day": last.get("date"),
        "chain_ok": live.chain_ok,
        "anchored": sum(1 for e in live.entries if e["ots"] == "bitcoin"),
        "pending": sum(1 for e in live.entries if e["ots"] == "pending"),
        "last_regime": last.get("regime"),
        "last_p_stress": last.get("p_stress"),
        "last_alarm_on": last.get("alarm_on"),
        "last_model_version": last.get("model_version"),
    }


def load_sources(root: Path | None = None, settings: dict | None = None, records_dir: Path | None = None) -> Sources:
    root = Path(root or ROOT)
    settings = settings if settings is not None else load_settings()
    records_dir = Path(records_dir) if records_dir else root / settings["publish"]["dir"]
    src = Sources(root=root, settings=settings, records_dir=records_dir)
    ordered = sorted(
        (json.loads(p.read_text(encoding="utf-8")) for p in (records_dir / "backtest").glob("*.json")),
        key=lambda r: r.get("generated_at") or "",
    )
    for record in ordered:
        src.backtests[version_key(record.get("model_version"))] = record
    wanted = version_key(settings["models"].get("version"))
    src.current = wanted if wanted in src.backtests else (list(src.backtests)[-1] if src.backtests else None)
    src.live = read_live(records_dir)
    cur = src.backtests.get(src.current or "", {})
    rule = settings["validation"]["episodes"].get("frozen", {})
    src.meta = {
        "commit": _git(root, "rev-parse", "--short", "HEAD") or "unknown",
        "model_version": settings["models"].get("version"),
        "settings_sha256": config_fingerprint(settings),
        "config_sha256": cur.get("config_sha256", ""),
        "episode_rule_sha256": cur.get("episode_rule_sha256") or rule.get("sha256", ""),
        "episode_rule_frozen": rule.get("date", ""),
        "data_provider": cur.get("data_provider", ""),
        "record_generated_at": cur.get("generated_at", ""),
        "record_code_version": cur.get("code_version", ""),
        "n_backtests": len(src.backtests),
        "repository_url": settings["publish"].get("repository_url", ""),
        "pages_url": settings["publish"].get("pages_url", ""),
    }
    return src
