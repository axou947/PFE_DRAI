"""What the Fed may do next, three ways (docs/LEARN.md). Descriptive, never advice.

1. bill_implied   what Treasury bill yields imply about the policy rate over the next 3 and 6 months
2. taylor         where three standard policy rules put the rate, versus where it is
3. base_rates     what the Fed did next, historically, when the economy looked like it does on the day

CME fed funds futures (the source of FedWatch) are licensed and are not used. Bills are a noisier
public proxy: they carry a small premium and move with Treasury supply, so lens 1 is an approximation.
"""

import numpy as np
import pandas as pd

from .data import _asof, load_meetings, policy_target

HORIZONS = {"DGS3MO": 91, "DGS6MO": 182}
OUTCOMES = ["cut", "hold", "hike"]


def _value(series: pd.Series, date) -> float:
    return float(_asof(series, [date])[0]) if series is not None and not series.empty else float("nan")


def meetings_ahead(settings: dict, date, days: int) -> list[pd.Timestamp]:
    """FOMC decision days in (date, date + days], extended past the calendar at the usual spacing."""
    date = pd.Timestamp(date)
    listed = list(load_meetings(settings)["date"])
    spacing = int(settings["learn"]["fed"]["meeting_spacing_days"])
    # Before the calendar (a past date in the time machine): the usual spacing, counted backwards.
    while listed[0] > date:
        listed.insert(0, listed[0] - pd.Timedelta(days=spacing))
    last = listed[-1]
    while last < date + pd.Timedelta(days=days):
        last = last + pd.Timedelta(days=spacing)
        listed.append(last)
    return [m for m in listed if date < m <= date + pd.Timedelta(days=days)]


def next_meeting(settings: dict, date) -> dict | None:
    """The next decision day; `listed` = False when it is estimated (outside fomc.yaml)."""
    ahead = meetings_ahead(settings, date, 120)
    if not ahead:
        return None
    frame = load_meetings(settings).set_index("date")
    day = ahead[0]
    listed = day in frame.index
    return {
        "date": day,
        "sep": bool(frame.loc[day, "sep"]) if listed else False,
        "listed": listed,
        "days": int((day - pd.Timestamp(date)).days),
    }


def bill_basis(data: dict[str, pd.Series], bill: str, date, settings: dict) -> tuple[float, int]:
    """(median bill - fed funds spread on 'quiet' days, number of such days); quiet = no target move
    within one bill life before or after the day, and that whole window already in the past."""
    cfg = settings["learn"]["fed"]
    date = pd.Timestamp(date)
    horizon = pd.Timedelta(days=HORIZONS[bill])
    target = policy_target(data)
    if bill not in data or "DFF" not in data or target.empty:
        return float(cfg["default_basis_pct"][bill]), 0
    window_start = date - pd.DateOffset(years=int(cfg["basis_years"]))
    days = data[bill].loc[window_start : date - horizon].index
    if len(days) == 0:
        return float(cfg["default_basis_pct"][bill]), 0
    before = _asof(target, days - horizon)
    now = _asof(target, days)
    after = _asof(target, days + horizon)
    quiet = (np.abs(now - before) < 1e-9) & (np.abs(after - now) < 1e-9)
    spread = data[bill].loc[days].to_numpy() - _asof(data["DFF"], days)
    spread = spread[quiet & ~np.isnan(spread)]
    if len(spread) < int(cfg["basis_min_days"]):
        return float(cfg["default_basis_pct"][bill]), int(len(spread))
    return float(np.median(spread)), int(len(spread))


def _probabilities(moves: float) -> dict[str, float]:
    """FedWatch-style reading of an expected number of 25 bp moves: 0.4 hikes = 40% hike, 60% hold."""
    p = min(abs(moves), 1.0)
    if moves >= 0:
        return {"cut": 0.0, "hold": 1 - p, "hike": p}
    return {"cut": p, "hold": 1 - p, "hike": 0.0}


def bill_implied(data: dict[str, pd.Series], date, settings: dict) -> dict:
    """Per bill (3 and 6 months): expected change of the policy rate by the end of the bill's life.

    A bill's yield ~ basis + average expected overnight rate over its life. With a move of the same size d
    at each meeting m inside the window (m at a fraction f_m of it), the average is r0 + d * sum(1 - f_m),
    so d = (yield - basis - r0) / sum(1 - f_m), and the change by the end is d x number of meetings.
    """
    date = pd.Timestamp(date)
    step = float(settings["learn"]["fed"]["step_pct"])
    r0 = _value(data.get("DFF"), date)
    out = {"effr": r0, "horizons": []}
    for bill, days in HORIZONS.items():
        y = _value(data.get(bill), date)
        if np.isnan(y) or np.isnan(r0):
            continue
        basis, quiet_days = bill_basis(data, bill, date, settings)
        meetings = meetings_ahead(settings, date, days)
        weights = [1 - (m - date).days / days for m in meetings]
        implied_avg = y - basis
        per_meeting = (implied_avg - r0) / sum(weights) if weights else 0.0
        change = per_meeting * len(meetings)
        moves = change / step
        out["horizons"].append(
            {
                "bill": bill,
                "days": days,
                "yield": y,
                "basis": basis,
                "basis_days": quiet_days,
                "meetings": [m.date().isoformat() for m in meetings],
                "change_pct": change,
                "moves": moves,
                "path": [r0 + per_meeting * (i + 1) for i in range(len(meetings))],
                "probabilities": _probabilities(moves),
            }
        )
    return out


# ---------------------------------------------------------------- Taylor rules
def taylor_inputs(data: dict[str, pd.Series], indicators: dict[str, pd.Series], date) -> dict:
    return {
        "inflation": _value(indicators.get("core_pce_yoy"), date),
        "unemployment": _value(indicators.get("unrate"), date),
        "natural_unemployment": _value(indicators.get("nrou"), date),
        "policy_rate": _value(policy_target(data), date),
    }


def taylor_rules(inputs: dict, settings: dict, r_star: float | None = None) -> dict[str, float]:
    """{rule: prescribed rate}. gap = okun x (u* - u): unemployment below its natural rate = positive gap."""
    cfg = settings["learn"]["fed"]["taylor"]
    r_star = cfg["r_star"] if r_star is None else r_star
    pi = inputs["inflation"]
    gap = cfg["okun"] * (inputs["natural_unemployment"] - inputs["unemployment"])
    out = {name: r_star + pi + w["a"] * (pi - 2) + w["b"] * gap for name, w in cfg["rules"].items()}
    if "balanced" in out:
        out["inertial"] = cfg["inertia"] * inputs["policy_rate"] + (1 - cfg["inertia"]) * out["balanced"]
    return out


def taylor(data: dict[str, pd.Series], indicators: dict[str, pd.Series], date, settings: dict) -> dict:
    inputs = taylor_inputs(data, indicators, date)
    if any(np.isnan(v) for v in inputs.values()):
        return {"inputs": inputs, "rules": {}, "median": float("nan"), "gap": float("nan"), "direction": None}
    rules = taylor_rules(inputs, settings)
    median = float(np.median(list(rules.values())))
    gap = median - inputs["policy_rate"]
    step = settings["learn"]["fed"]["step_pct"]
    direction = "hike" if gap > 2 * step else "cut" if gap < -2 * step else "hold"
    return {"inputs": inputs, "rules": rules, "median": median, "gap": gap, "direction": direction}


def taylor_history(data: dict[str, pd.Series], indicators: dict[str, pd.Series], settings: dict) -> pd.DataFrame:
    """Monthly prescriptions of each rule and the actual target (for the chart)."""
    infl = indicators.get("core_pce_yoy")
    if infl is None or infl.empty:
        return pd.DataFrame()
    rows = {}
    for d in infl.index:
        inputs = taylor_inputs(data, indicators, d)
        if not any(np.isnan(v) for v in inputs.values()):
            rows[d] = {**taylor_rules(inputs, settings), "actual": inputs["policy_rate"]}
    return pd.DataFrame.from_dict(rows, orient="index")


# ---------------------------------------------------------------- base rates
FEATURES = ["inflation", "unemployment_gap", "unemployment_trend", "fed_last_year"]


def monthly_conditions(data: dict[str, pd.Series], indicators: dict[str, pd.Series], settings: dict, end) -> pd.DataFrame:
    """Month ends with the conditions the Fed looks at and what it did over the next months."""
    cfg = settings["learn"]["fed"]["base_rates"]
    target = policy_target(data)
    if target.empty or indicators.get("core_pce_yoy") is None:
        return pd.DataFrame()
    months = pd.date_range(cfg["start"], pd.Timestamp(end), freq="ME")
    unrate = indicators["unrate"]
    frame = pd.DataFrame(index=months)
    frame["inflation"] = _asof(indicators["core_pce_yoy"], months)
    frame["unemployment_gap"] = _asof(indicators["unemp_gap"], months)
    frame["unemployment_trend"] = _asof(unrate, months) - _asof(unrate, months - pd.DateOffset(months=6))
    frame["target"] = _asof(target, months)
    frame["fed_last_year"] = frame["target"] - _asof(target, months - pd.DateOffset(months=12))
    ahead = months + pd.DateOffset(months=int(cfg["horizon_months"]))
    change = _asof(target, ahead) - frame["target"].to_numpy()
    change[ahead > pd.Timestamp(end)] = np.nan  # outcome not known yet on `end`
    frame["change"] = change
    move = float(cfg["move_pct"])
    frame["outcome"] = np.where(np.isnan(change), None, np.where(change > move, "hike", np.where(change < -move, "cut", "hold")))
    return frame.dropna(subset=FEATURES)


def base_rates(
    data: dict[str, pd.Series],
    indicators: dict[str, pd.Series],
    date,
    settings: dict,
    regimes: pd.Series | None = None,
) -> dict:
    """Share of hikes, holds and cuts after the past months most like `date` (nearest neighbours on
    standardised conditions), plus the same split by our regime when its history is given."""
    cfg = settings["learn"]["fed"]["base_rates"]
    date = pd.Timestamp(date)
    frame = monthly_conditions(data, indicators, settings, date)
    if frame.empty:
        return {"probabilities": None}
    today = pd.Series(
        {
            "inflation": _value(indicators["core_pce_yoy"], date),
            "unemployment_gap": _value(indicators["unemp_gap"], date),
            "unemployment_trend": _value(indicators["unrate"], date)
            - _value(indicators["unrate"], date - pd.DateOffset(months=6)),
            "fed_last_year": _value(policy_target(data), date) - _value(policy_target(data), date - pd.DateOffset(months=12)),
        }
    )
    known = frame[frame["outcome"].notna()]
    if today.isna().any() or len(known) < cfg["neighbours"]:
        return {"probabilities": None, "today": today.to_dict()}
    scale = known[FEATURES].std().replace(0, 1)
    distance = np.sqrt((((known[FEATURES] - today) / scale) ** 2).sum(axis=1))
    nearest = known.loc[distance.nsmallest(int(cfg["neighbours"])).index]
    counts = nearest["outcome"].value_counts()
    probs = {o: float(counts.get(o, 0)) / len(nearest) for o in OUTCOMES}
    shown = nearest.assign(distance=distance.loc[nearest.index]).sort_values("distance").head(8)
    out = {
        "probabilities": probs,
        "today": today.to_dict(),
        "sample": len(nearest),
        "months": len(known),
        "horizon_months": int(cfg["horizon_months"]),
        "similar": [
            {
                "date": d.date().isoformat(),
                **{k: float(r[k]) for k in FEATURES},
                "change": float(r["change"]),
                "outcome": r["outcome"],
            }
            for d, r in shown.iterrows()
        ],
    }
    if regimes is not None and not regimes.empty:
        by_regime = known.join(pd.Series(_asof_labels(regimes, known.index), index=known.index, name="regime"))
        by_regime = by_regime.dropna(subset=["regime"])
        table = pd.crosstab(by_regime["regime"], by_regime["outcome"]).reindex(columns=OUTCOMES, fill_value=0)
        out["by_regime"] = {r: {o: int(row[o]) for o in OUTCOMES} for r, row in table.iterrows()}
    return out


def _asof_labels(labels: pd.Series, dates) -> list:
    pos = labels.index.searchsorted(pd.DatetimeIndex(dates), side="right") - 1
    values = labels.to_numpy()
    return [
        values[p] if p >= 0 and labels.index[p] >= pd.Timestamp(d) - pd.Timedelta(days=7) else None
        for p, d in zip(pos, dates, strict=True)
    ]


# ---------------------------------------------------------------- summary
def outlook(data: dict[str, pd.Series], indicators: dict[str, pd.Series], date, settings: dict, regimes=None) -> dict:
    """The three lenses and a one-line headline (from the bills, the only market-based one)."""
    bills = bill_implied(data, date, settings)
    rule = taylor(data, indicators, date, settings)
    history = base_rates(data, indicators, date, settings, regimes)
    headline = None
    if bills["horizons"]:
        probs = bills["horizons"][0]["probabilities"]
        likely = max(probs, key=probs.get)
        headline = {
            "outcome": likely,
            "probability": probs[likely],
            "probabilities": probs,
            "source": bills["horizons"][0]["bill"],
        }
    agree = []
    if headline:
        if history.get("probabilities"):
            hp = history["probabilities"]
            agree.append(("history", max(hp, key=hp.get) == headline["outcome"]))
        if rule.get("direction"):
            agree.append(("taylor", rule["direction"] == headline["outcome"]))
    return {
        "date": pd.Timestamp(date).date().isoformat(),
        "next_meeting": next_meeting(settings, date),
        "policy_rate": _value(policy_target(data), date),
        "bills": bills,
        "taylor": rule,
        "history": history,
        "headline": headline,
        "agreement": dict(agree),
    }
