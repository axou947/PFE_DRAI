"""Challenger track record (docs/CHALLENGERS.md): candidate models published live every day next to v2.2.

Ideas that cannot be judged on past data, because their series start too late or the past crises have already
been seen, get a fair test going forward instead. Each challenger is v2.2 with one change fixed in
`challengers.models` (config/settings.yaml). It is published every market day into its own folder of the track
record with the same hash chain and external timestamp as the published model (publish/snapshot.py), and scored
on the episodes that start after its first day, against the published model's own entries on the same days.

Nothing here changes what is published for v2.2: the `challengers` block is outside the settings fingerprint,
and the challengers read their extra series (catalog TESTED) on top of the published data.
"""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from .config import _deep_merge, resolve
from .publish.record import LiveRecord, live_scorecard, read_live
from .publish.snapshot import publish


def challenger_names(settings: dict) -> list[str]:
    return list(settings.get("challengers", {}).get("models", {}))


def challenger_settings(settings: dict, name: str) -> dict:
    """The published settings with the challenger's one change, and a model version naming it."""
    cfg = settings["challengers"]["models"][name]
    version = f"{settings['models'].get('version', '')}+{name}"
    return _deep_merge(_deep_merge(settings, cfg.get("settings", {})), {"models": {"version": version}})


def challenger_pipeline(pipeline, name: str):
    """The challenger on the published model's data, plus its own extra series (fetched once, cached here)."""
    cfg = pipeline.settings["challengers"]["models"][name]
    other = pipeline.with_settings(challenger_settings(pipeline.settings, name))
    series = list(cfg.get("series", []))
    extra = pipeline.__dict__.setdefault("_challenger_raw", {})
    missing = [s for s in series if s not in pipeline.raw and s not in extra]
    if missing:
        data = pipeline.settings["data"]
        start = pd.Timestamp(data["start"])
        end = pd.Timestamp(data["end"]) if data.get("end") else pd.Timestamp.today().normalize()
        extra.update(pipeline.provider.fetch_subset(missing, start, end))
    absent = [s for s in series if s not in pipeline.raw and (s not in extra or extra[s].empty)]
    if absent:
        raise ValueError(f"Challenger '{name}' needs {', '.join(absent)} from provider '{pipeline.provider.name}'")
    # A new dict: the published model's own data stays exactly as it was fetched.
    other.__dict__["raw"] = {**pipeline.raw, **{s: extra[s] for s in series if s in extra}}
    return other


def folder(settings: dict, name: str | None = None) -> Path:
    base = resolve(settings["challengers"]["dir"])
    return base / name if name else base


def publish_challengers(pipeline, out_dir: str | Path | None = None) -> dict[str, Path | None | Exception]:
    """Publish every challenger's latest day. One challenger's failure never stops the others."""
    out = {}
    for name in challenger_names(pipeline.settings):
        target = Path(out_dir) / name if out_dir else folder(pipeline.settings, name)
        try:
            out[name] = publish(challenger_pipeline(pipeline, name), out_dir=target)
        except Exception as exc:  # noqa: BLE001 - reported per challenger by the caller
            out[name] = exc
    return out


def _since(live: LiveRecord, start: str | None) -> LiveRecord:
    if start is None:
        return live
    return replace(live, entries=[e for e in live.entries if e["date"] >= start])


def scorecard(pipeline, champion_dir: str | Path | None = None, challengers_dir: str | Path | None = None) -> dict:
    """Champion and challengers, as published, on the days since the first challenger day.

    Every number comes from the published entries (never recomputed). Episodes are dated by the frozen rule on
    today's prices, and an episode or a false alarm whose window has not elapsed is pending.
    """
    settings = pipeline.settings
    base = Path(challengers_dir) if challengers_dir else folder(settings)
    records = {name: read_live(base / name) for name in challenger_names(settings)}
    firsts = [r.first for r in records.values() if r.first]
    start = min(firsts) if firsts else None
    champion = read_live(resolve(champion_dir or settings["publish"]["dir"]))
    rows = {"v2.2 (published)": _since(champion, start), **{n: records[n] for n in records}}
    index = pipeline.prices.index
    models = {}
    for name, live in rows.items():
        card = live_scorecard(live, pipeline.episodes, index, settings) if live.entries else None
        models[name] = _summary(name, live, card)
    return {
        "since": start,
        "last_market_day": pd.Timestamp(index[-1]).date().isoformat(),
        "models": models,
        "episodes": _who_called_first(models),
        "months": _by_month(models),
    }


def _summary(name: str, live: LiveRecord, card: dict | None) -> dict:
    episodes = card["episodes"] if card else []
    alarms = card["alarms"] if card else []
    done = [e for e in episodes if e["status"] != "pending"]
    lat = [e["latency_days"] for e in episodes if e["status"] == "detected"]
    false = [a for a in alarms if a["false_alarm"]]
    return {
        "name": name,
        "days": len(live.entries),
        "first_day": live.first,
        "chain_ok": live.chain_ok,
        "alarm_days": sum(1 for e in live.entries if e.get("alarm_on")),
        "episodes_scored": len(done),
        "detected": sum(1 for e in done if e["status"] == "detected"),
        "pending": len(episodes) - len(done),
        "median_latency": float(np.median(lat)) if lat else None,
        "false_alarms": sum(1 for a in false if not a.get("pending")),
        "false_alarms_pending": sum(1 for a in false if a.get("pending")),
        "episode_list": episodes,
        "alarm_list": alarms,
    }


def _who_called_first(models: dict) -> list[dict]:
    starts = sorted({e["start"] for m in models.values() for e in m["episode_list"]})
    out = []
    for start in starts:
        calls = {}
        for name, m in models.items():
            e = next((x for x in m["episode_list"] if x["start"] == start), None)
            calls[name] = None if e is None else {"status": e["status"], "latency_days": e["latency_days"]}
        hits = {n: c["latency_days"] for n, c in calls.items() if c and c["status"] == "detected"}
        best = min(hits.values()) if hits else None
        out.append({"start": start, "calls": calls, "first": sorted(n for n, v in hits.items() if v == best)})
    return out


def _by_month(models: dict) -> list[dict]:
    months: dict[str, dict] = {}
    for name, m in models.items():
        for a in m["alarm_list"]:
            month = a["start"][:7]
            row = months.setdefault(month, {})
            key = "false_alarms" if a["false_alarm"] else "true_alarms"
            row.setdefault(name, {"true_alarms": 0, "false_alarms": 0, "alarm_days": 0})
            row[name][key] += 1
            row[name]["alarm_days"] += int(a["days"])
    return [{"month": k, "models": v} for k, v in sorted(months.items())]


def scorecard_markdown(card: dict) -> str:
    """The scorecard as a page: what each model called, since the first challenger day."""
    lines = [
        "# Challenger scorecard",
        "",
        f"Live since {card['since'] or '(no challenger published yet)'}, last market day {card['last_market_day']}. "
        "Every number is read from the published, hash-chained entries (docs/CHALLENGERS.md). Rebuilt every day.",
        "",
        "| model | days | chain | episodes scored | detected | median latency | false alarms (final) | pending |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for m in card["models"].values():
        lat = "–" if m["median_latency"] is None else f"{m['median_latency']:+.0f}"
        pending = m["pending"] + m["false_alarms_pending"]
        chain = "ok" if m["chain_ok"] else "BROKEN"
        lines.append(
            f"| {m['name']} | {m['days']} | {chain} | {m['episodes_scored']} | {m['detected']} | {lat} | "
            f"{m['false_alarms']} | {pending} |"
        )
    lines += ["", "## Who called each stress episode first", ""]
    if not card["episodes"]:
        lines.append("No stress episode has started since the challengers went live.")
    else:
        names = list(card["models"])
        lines += ["| episode start | " + " | ".join(names) + " | first |", "|---|" + "---:|" * len(names) + "---|"]
        for e in card["episodes"]:
            cells = []
            for n in names:
                c = e["calls"][n]
                cells.append("–" if c is None else (f"{c['latency_days']:+d}" if c["status"] == "detected" else c["status"]))
            lines.append(f"| {e['start']} | " + " | ".join(cells) + f" | {', '.join(e['first']) or '–'} |")
    lines += ["", "## By month (alarm spells that started that month)", ""]
    if not card["months"]:
        lines.append("No alarm yet.")
    else:
        for row in card["months"]:
            parts = [
                f"{n}: {v['true_alarms']} true, {v['false_alarms']} false, {v['alarm_days']} days"
                for n, v in row["models"].items()
            ]
            lines.append(f"- **{row['month']}**: " + "; ".join(parts))
    return "\n".join(lines) + "\n"


def slim(card: dict) -> dict:
    """The scorecard without the per-episode and per-alarm lists (scorecard.json)."""
    drop = ("episode_list", "alarm_list")
    return {**card, "models": {k: {x: y for x, y in v.items() if x not in drop} for k, v in card["models"].items()}}


def backtest_table(pipeline, model: str | None = None) -> pd.DataFrame:
    """Each challenger on the past out-of-sample period. Seen data: informative only, it decides nothing."""
    model = model or pipeline.settings["models"]["default"]
    rows = []
    for name, p in [("v2.2 (published)", pipeline)] + [
        (n, challenger_pipeline(pipeline, n)) for n in challenger_names(pipeline.settings)
    ]:
        r = p.evaluate(model)
        rows.append(
            {
                "model": name,
                "detected": f"{r['detected']}/{r['n_episodes']}",
                "median_latency_all": r["median_latency_all"],
                "fp_per_year": r["false_positives_per_year"],
                "false_alarm_share": r["false_alarm_share"],
                "brier": r["brier"],
                "ece": r["ece"],
            }
        )
    return pd.DataFrame(rows)
