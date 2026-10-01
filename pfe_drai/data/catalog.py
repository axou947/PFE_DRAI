"""Catalog of the series the pipeline needs, with their id at each source.

To plug a real API, a provider only has to return these canonical columns.
The `licence` field records what the audits found: research use vs commercial display.
"commercial" means the best listed source allows commercial use (FRED with its disclaimer,
Tiingo on a paid plan); Yahoo ids stay research-only.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Series:
    name: str
    description: str
    frequency: str  # daily | weekly | monthly
    dimension: str  # stress | growth | inflation | market
    source_ids: dict[str, str] = field(default_factory=dict)
    licence: str = "research"  # research | commercial | check


CATALOG: dict[str, Series] = {
    s.name: s
    for s in [
        # FRED SP500 starts in 2016 and S&P forbids reproduction: use the SPY ETF instead.
        Series("equity", "US equity index ETF (price)", "daily", "market", {"tiingo": "SPY", "yahoo": "SPY"}, "commercial"),
        Series("vix", "Implied volatility index", "daily", "stress", {"fred": "VIXCLS", "yahoo": "^VIX"}, "check"),
        Series("hy_bond", "High-yield bond ETF (price)", "daily", "stress", {"tiingo": "HYG", "yahoo": "HYG"}, "commercial"),
        Series("ig_bond", "Inv.-grade bond ETF (price)", "daily", "stress", {"tiingo": "LQD", "yahoo": "LQD"}, "commercial"),
        Series("treasury", "7-10y Treasury ETF (price)", "daily", "stress", {"tiingo": "IEF", "yahoo": "IEF"}, "commercial"),
        Series("us10y", "10-year Treasury yield (%)", "daily", "growth", {"fred": "DGS10"}, "commercial"),
        Series("us2y", "2-year Treasury yield (%)", "daily", "growth", {"fred": "DGS2"}, "commercial"),
        Series("breakeven10", "10-year breakeven inflation (%)", "daily", "inflation", {"fred": "T10YIE"}, "commercial"),
        Series("claims", "Initial jobless claims", "weekly", "growth", {"fred": "ICSA"}, "commercial"),
        Series("indpro", "Industrial production index", "monthly", "growth", {"fred": "INDPRO"}, "commercial"),
        Series("cpi", "Consumer price index", "monthly", "inflation", {"fred": "CPIAUCSL"}, "commercial"),
    ]
}

REQUIRED = list(CATALOG)
