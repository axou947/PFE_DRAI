"""The calculators of the Learn Lab (docs/LEARN.md). Textbook formulas, no data access."""

import math

import pandas as pd

from .data import _asof


def mortgage_payment(loan: float, rate_pct: float, years: int = 30) -> float:
    """Monthly payment of a fixed-rate loan."""
    r, n = rate_pct / 1200, years * 12
    return loan / n if r == 0 else loan * r * (1 + r) ** n / ((1 + r) ** n - 1)


def purchasing_power(cpi: pd.Series, amount: float, then, now) -> float | None:
    """What `amount` dollars of `then` are worth in dollars of `now` (CPI ratio)."""
    a, b = _asof(cpi, [pd.Timestamp(then), pd.Timestamp(now)])
    if math.isnan(a) or math.isnan(b) or a <= 0:
        return None
    return float(amount * b / a)


def bond(yield_pct: float, coupon_pct: float, years: float, shift_pct: float = 0.0) -> dict:
    """Price (per 100), modified duration and convexity of an annual-coupon bond, and its price after a
    parallel move of `shift_pct` in its yield (exact repricing, and the duration + convexity estimate)."""

    def price(y):
        n = max(int(round(years)), 1)
        c = coupon_pct
        if abs(y) < 1e-12:
            return c * n + 100
        return sum(c / (1 + y) ** t for t in range(1, n + 1)) + 100 / (1 + y) ** n

    y = yield_pct / 100
    p0 = price(y)
    h = 1e-4
    up, down = price(y + h), price(y - h)
    duration = (down - up) / (2 * h * p0)
    convexity = (up + down - 2 * p0) / (h**2 * p0)
    dy = shift_pct / 100
    p1 = price(y + dy)
    estimate = p0 * (1 - duration * dy + 0.5 * convexity * dy**2)
    return {
        "price": p0,
        "duration": duration,
        "convexity": convexity,
        "new_price": p1,
        "change_pct": (p1 / p0 - 1) * 100,
        "estimate_pct": (estimate / p0 - 1) * 100,
    }


# New York Fed yield-curve model (Estrella and Trubin 2006): P(recession in 12 months) from the
# 10-year minus 3-month spread, in percentage points (bond-equivalent 3-month yield in the original).
CURVE_PROBIT = (-0.5333, -0.6330)


def curve_recession_probability(spread_pt: float) -> float:
    a, b = CURVE_PROBIT
    return 0.5 * (1 + math.erf((a + b * spread_pt) / math.sqrt(2)))


def debt_path(debt_pct: float, primary_deficit_pct: float, rate_pct: float, growth_pct: float, years: int = 20) -> list[float]:
    """Debt / GDP each year: d' = d (1 + r) / (1 + g) + primary deficit (nominal r and g, % of GDP)."""
    path, d = [debt_pct], debt_pct
    for _ in range(years):
        d = d * (1 + rate_pct / 100) / (1 + growth_pct / 100) + primary_deficit_pct
        path.append(d)
    return path


def stabilising_balance(debt_pct: float, rate_pct: float, growth_pct: float) -> float:
    """Primary surplus (% of GDP) that keeps debt / GDP flat: d (r - g) / (1 + g)."""
    return debt_pct * (rate_pct - growth_pct) / (100 + growth_pct)


def real_change(nominal_pct: float, inflation_pct: float) -> float:
    """Exact real change: (1 + nominal) / (1 + inflation) - 1, in %."""
    return ((1 + nominal_pct / 100) / (1 + inflation_pct / 100) - 1) * 100
