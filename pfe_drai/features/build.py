"""Point-in-time features and the three dimension scores (stress, growth, inflation).

Every transformation only uses past data: rolling windows, expanding z-scores and
publication lags for monthly releases. `test_features.py` checks this property.
"""

import numpy as np
import pandas as pd

from ..data.catalog import CATALOG

# feature name -> dimension. The sign makes a high value mean "more" of the dimension.
FEATURES: dict[str, str] = {
    "vix_level": "stress",
    "realised_vol": "stress",
    "credit_stress": "stress",
    "drawdown": "stress",
    "equity_momentum": "growth",
    "curve_slope": "growth",
    "industrial_production": "growth",
    "jobless_claims": "growth",
    "cpi_inflation": "inflation",
    "breakeven_level": "inflation",
    "breakeven_change": "inflation",
    "short_rate_change": "inflation",
}
DIMENSIONS = ["stress", "growth", "inflation"]


def align(raw: dict[str, pd.Series], lags: dict[str, int], release_dated: set[str] = frozenset()) -> pd.DataFrame:
    """Put every series on business days, as known on each day.

    Series in `release_dated` are already indexed by their publication day. The others are
    indexed by their reference period: monthly values move to the end of the month (FRED dates
    them on the 1st), then the publication lag is added.
    """
    daily_index = raw["equity"].index
    columns = {}
    for name, series in raw.items():
        series = series.sort_index()
        if name not in release_dated:
            series = series.copy()
            if name in CATALOG and CATALOG[name].frequency == "monthly":
                series.index = series.index + pd.offsets.MonthEnd(0)
            series.index = series.index + pd.Timedelta(days=lags.get(name, 0))
        columns[name] = series.reindex(daily_index.union(series.index)).ffill().reindex(daily_index)
    return pd.DataFrame(columns, index=daily_index)


def raw_features(prices: pd.DataFrame) -> pd.DataFrame:
    eq = prices["equity"]
    log_eq = np.log(eq)
    f = pd.DataFrame(index=prices.index)
    f["vix_level"] = prices["vix"]
    f["realised_vol"] = log_eq.diff().rolling(21).std() * np.sqrt(252)
    f["credit_stress"] = credit_stress(prices["hy_bond"], prices["treasury"])
    f["drawdown"] = -(eq / eq.rolling(252, min_periods=21).max() - 1)
    f["equity_momentum"] = log_eq.diff(126)
    f["curve_slope"] = prices["us10y"] - prices["us2y"]
    f["industrial_production"] = np.log(prices["indpro"]).diff(252)
    f["jobless_claims"] = -np.log(prices["claims"]).diff(63)
    f["cpi_inflation"] = np.log(prices["cpi"]).diff(252)
    f["breakeven_level"] = prices["breakeven10"]
    f["breakeven_change"] = prices["breakeven10"].diff(63)
    f["short_rate_change"] = prices["us2y"].diff(126)
    return f[list(FEATURES)]


def credit_stress(bond: pd.Series, treasury: pd.Series) -> pd.Series:
    """Credit bonds lagging Treasuries over a quarter (a widening spread) reads as stress."""
    return -np.log(bond / treasury).diff(63)


def expanding_zscore(frame: pd.DataFrame, min_periods: int, clip: float) -> pd.DataFrame:
    mean = frame.expanding(min_periods).mean()
    std = frame.expanding(min_periods).std()
    return ((frame - mean) / std).clip(-clip, clip)


def dimension_scores(z: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({dim: z[[f for f, d in FEATURES.items() if d == dim]].mean(axis=1) for dim in DIMENSIONS})


def build(
    raw: dict[str, pd.Series], settings: dict, release_dated: set[str] = frozenset()
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (aligned prices, feature z-scores, dimension scores), without warm-up rows."""
    prices = align(raw, settings["data"].get("publication_lag_days", {}), release_dated)
    feats = raw_features(prices)
    cfg = settings["features"]
    z = expanding_zscore(feats, cfg["zscore_min_periods"], cfg["zscore_clip"])
    # HYG only exists since 2007. Before its z-score is ready, the investment-grade ETF (LQD,
    # 2002) stands in, z-scored on its own past so both read on the same scale.
    proxy = credit_stress(prices["ig_bond"], prices["treasury"]).to_frame("credit_stress")
    z["credit_stress"] = z["credit_stress"].fillna(
        expanding_zscore(proxy, cfg["zscore_min_periods"], cfg["zscore_clip"])["credit_stress"]
    )
    z = z.dropna()
    scores = dimension_scores(z)
    return prices.loc[z.index], z, scores
