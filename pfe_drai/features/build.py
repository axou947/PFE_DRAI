"""Point-in-time features and the three dimension scores (stress, growth, inflation).

Every transformation only uses past data: rolling windows, expanding z-scores and
publication lags for monthly releases. `test_features.py` checks this property.
"""

import numpy as np
import pandas as pd

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


def align(raw: dict[str, pd.Series], lags: dict[str, int]) -> pd.DataFrame:
    """Put every series on business days, as known on each day (publication lags applied)."""
    daily_index = raw["equity"].index
    columns = {}
    for name, series in raw.items():
        series = series.sort_index()
        if name in lags:
            series = series.copy()
            series.index = series.index + pd.Timedelta(days=lags[name])
        columns[name] = series.reindex(daily_index.union(series.index)).ffill().reindex(daily_index)
    return pd.DataFrame(columns, index=daily_index)


def raw_features(prices: pd.DataFrame) -> pd.DataFrame:
    eq = prices["equity"]
    log_eq = np.log(eq)
    f = pd.DataFrame(index=prices.index)
    f["vix_level"] = prices["vix"]
    f["realised_vol"] = log_eq.diff().rolling(21).std() * np.sqrt(252)
    credit_ratio = np.log(prices["hy_bond"] / prices["treasury"])
    f["credit_stress"] = -credit_ratio.diff(63)
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


def expanding_zscore(frame: pd.DataFrame, min_periods: int, clip: float) -> pd.DataFrame:
    mean = frame.expanding(min_periods).mean()
    std = frame.expanding(min_periods).std()
    return ((frame - mean) / std).clip(-clip, clip)


def dimension_scores(z: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({dim: z[[f for f, d in FEATURES.items() if d == dim]].mean(axis=1) for dim in DIMENSIONS})


def build(raw: dict[str, pd.Series], settings: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (aligned prices, feature z-scores, dimension scores), without warm-up rows."""
    prices = align(raw, settings["data"].get("publication_lag_days", {}))
    feats = raw_features(prices)
    cfg = settings["features"]
    z = expanding_zscore(feats, cfg["zscore_min_periods"], cfg["zscore_clip"])
    z = z.dropna()
    scores = dimension_scores(z)
    return prices.loc[z.index], z, scores
