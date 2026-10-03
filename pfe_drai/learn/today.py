"""Where the US is on a given day: readings for the cards' "today" boxes and a recession checklist.

Facts only (level, change, rank in its own history): no forecast and no advice.
"""

import numpy as np
import pandas as pd

from .data import Indicator, _asof


def reading(series: pd.Series | None, indicator: Indicator, date) -> dict | None:
    """Latest value on or before `date`, its changes, its rank in its history and its trend."""
    if series is None or series.empty:
        return None
    date = pd.Timestamp(date)
    past = series.loc[:date].dropna()
    if past.empty:
        return None
    value, when = float(past.iloc[-1]), past.index[-1]

    def back(months):
        v = _asof(past, [when - pd.DateOffset(months=months)])[0]
        return float(value - v) if not np.isnan(v) else None

    change_3m, change_12m = back(3), back(12)
    # A move counts as a trend when it is larger than a quarter of the usual 3-month move.
    monthly = past.resample("ME").last().dropna()
    usual = (monthly - monthly.shift(3)).abs().median() if len(monthly) > 6 else np.nan
    if change_3m is None or np.isnan(usual):
        trend = None
    elif abs(change_3m) <= 0.25 * usual:
        trend = "stable"
    else:
        trend = "rising" if change_3m > 0 else "falling"
    return {
        "id": indicator.id,
        "value": value,
        "date": when.date().isoformat(),
        "unit": indicator.unit,
        "ref": indicator.ref,
        "change_3m": change_3m,
        "change_12m": change_12m,
        "percentile": float((past < value).mean()),
        "since": past.index[0].year,
        "trend": trend,
        "stale_days": int((date - when).days),
    }


def readings(indicators: dict[str, Indicator], values: dict[str, pd.Series], names, date) -> list[dict]:
    out = []
    for name in names:
        r = reading(values.get(name), indicators[name], date)
        if r:
            out.append(r)
    return out


def checklist(values: dict[str, pd.Series], date, settings: dict, alarm_on: bool | None = None) -> list[dict]:
    """Classic recession warning lights, each green / amber / red / None (no data), with its value."""
    cfg = settings["learn"]["checklist"]
    date = pd.Timestamp(date)

    def last(name, at=date):
        s = values.get(name)
        return float(_asof(s, [at])[0]) if s is not None and not s.empty else float("nan")

    items = []
    sahm = last("sahm")
    items.append(_light("sahm", sahm, "red" if sahm >= cfg["sahm_red"] else "amber" if sahm >= cfg["sahm_amber"] else "green"))
    curve = last("curve_10y_3m")
    s = values.get("curve_10y_3m")
    inverted_last_year = s is not None and not s.empty and (s.loc[date - pd.DateOffset(years=1) : date] < 0).any()
    items.append(_light("curve", curve, "red" if curve < 0 else "amber" if inverted_last_year else "green"))
    claims = values.get("claims")
    if claims is not None and not claims.empty:
        recent = claims.loc[:date]
        avg4 = recent.rolling(4).mean()
        low = avg4.loc[date - pd.DateOffset(weeks=52) : date].min()
        rise = float(avg4.iloc[-1] / low - 1) if len(avg4.dropna()) and low > 0 else float("nan")
    else:
        rise = float("nan")
    items.append(
        _light(
            "claims", rise, "red" if rise >= cfg["claims_rise_red"] else "amber" if rise >= cfg["claims_rise_amber"] else "green"
        )
    )
    payrolls = last("payrolls_3m")
    items.append(
        _light("payrolls", payrolls, "red" if payrolls < 0 else "amber" if payrolls < cfg["payrolls_amber_k"] else "green")
    )
    gdp = last("real_gdp_yoy")
    items.append(_light("gdp", gdp, "red" if gdp < 0 else "amber" if gdp < 1 else "green"))
    if alarm_on is not None:
        items.append({"id": "alarm", "value": None, "status": "red" if alarm_on else "green"})
    return items


def _light(name: str, value: float, status: str) -> dict:
    return {"id": name, "value": None if np.isnan(value) else value, "status": None if np.isnan(value) else status}


def in_focus(cards, indicators: dict[str, Indicator], values: dict[str, pd.Series], date) -> set[str]:
    """Cards with an indicator at an extreme of its own history (top or bottom 10%) on the day."""
    hot = set()
    for card in cards:
        for name in card.indicators:
            if name not in indicators:
                continue
            r = reading(values.get(name), indicators[name], date)
            if r and r["stale_days"] < 200 and (r["percentile"] >= 0.9 or r["percentile"] <= 0.1):
                hot.add(card.id)
                break
    return hot
