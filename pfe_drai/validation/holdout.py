"""Pre-registered holdout for the onset detector (docs/DETECTION_V2.md).

US market history before the real-data out-of-sample period (SPY from 1993, VIX, LQD/IEF from
2002), dated by the same frozen episode rule. None of these episodes was ever scored, so the
candidates can be compared on them without touching the 11 episodes already published.
Only the onset detector runs here: the other models need series that start in 2003 (breakeven).
"""

from dataclasses import dataclass

import pandas as pd

from ..config import _deep_merge
from ..data import get_provider
from ..features.market import MARKET, NEEDED, market_frame
from .episodes import find_episodes, onset_target
from .metrics import evaluate
from .walkforward import walk_forward


@dataclass
class HoldoutResult:
    provider: str
    is_live: bool
    first_prediction: pd.Timestamp
    last_day: pd.Timestamp
    rows: pd.DataFrame  # one row per candidate
    latencies: pd.DataFrame  # one row per episode, one column per candidate
    chosen: int | None  # index of the selected candidate, None if none qualifies


def candidate_settings(settings: dict, candidate: dict) -> dict:
    return _deep_merge(settings, {"models": {"onset": candidate}})


def select(rows: pd.DataFrame, settings: dict) -> int | None:
    """Pre-registered selection rule (docs/DETECTION_V2.md).

    A candidate must meet the product's false-alarm targets on its own (validation.targets:
    false positives a year, share of calm days in false alarm). Among those, the lowest median
    latency over all episodes (misses = window end) wins; ties: fewer false positives, then
    the earlier candidate in the list.
    """
    targets = settings["validation"]["targets"]
    ok = rows[
        (rows["fp_per_year"] <= targets["max_false_positives_per_year"])
        & (rows["false_alarm_share"] <= targets["max_false_alarm_share"])
    ]
    if ok.empty:
        return None
    return int(ok.sort_values(["median_latency_all", "fp_per_year"], kind="stable").index[0])


def run_holdout(settings: dict) -> HoldoutResult:
    cfg = settings["validation"]["holdout"]
    start, end = pd.Timestamp(cfg["start"]), pd.Timestamp(cfg["end"])
    provider = get_provider(settings)
    raw = provider.fetch_subset(NEEDED["market_credit"], start, end)
    for name in NEEDED["market"]:
        if name not in raw or raw[name].empty:
            raise ValueError(f"The holdout needs '{name}' from provider '{provider.name}'")
    raw = {name: series.loc[start:end] for name, series in raw.items()}
    market = market_frame(raw, settings, provider.release_dated)
    equity = raw["equity"].sort_index().reindex(market.index).ffill()
    episodes = find_episodes(equity, settings)
    # Days where every equity/VIX input exists (credit may still be missing before 2002).
    market = market.dropna(subset=MARKET)
    equity = equity.loc[market.index]

    rows, latencies = [], {}
    for candidate in cfg["candidates"]:
        s = candidate_settings(settings, candidate)
        onset = s["models"]["onset"]
        target = onset_target(market.index, episodes, onset["horizon_days"], onset.get("after_start_days"))
        probs = walk_forward("onset", market, market, target, s, market=market, onset=target)
        r = evaluate(probs, equity, episodes, s)
        name = f"{candidate['learner']} / {candidate['inputs']}"
        rows.append(
            {
                "candidate": name,
                "episodes": r["n_episodes"],
                "detected": r["detected"],
                "median_latency": r["median_latency"],
                "median_latency_all": r["median_latency_all"],
                "fp_per_year": r["false_positives_per_year"],
                "false_alarm_share": r["false_alarm_share"],
                "brier": r["brier_stress"],
            }
        )
        lat = r["episodes"].set_index("start")
        latencies[name] = lat["latency_days"]
        latencies.setdefault("max_drawdown", lat["max_drawdown"])
    table = pd.DataFrame(rows)
    lat_table = pd.DataFrame(latencies)
    lat_table = lat_table[["max_drawdown"] + [c for c in lat_table.columns if c != "max_drawdown"]]
    first = probs.index[0]
    return HoldoutResult(provider.name, provider.is_live, first, market.index[-1], table, lat_table, select(table, settings))
