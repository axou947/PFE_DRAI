"""Catalog of the series the pipeline needs, with their id at each source.

To plug a real API, a provider only has to return these canonical columns.
The `licence` field records what the audits found: research use vs commercial display.
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
        Series("equity", "US equity index (price)", "daily", "market", {"fred": "SP500", "yahoo": "SPY"}, "check"),
        Series("vix", "Implied volatility index", "daily", "stress", {"fred": "VIXCLS", "yahoo": "^VIX"}, "check"),
        Series("hy_bond", "High-yield corporate bond ETF (price)", "daily", "stress", {"yahoo": "HYG"}, "research"),
        Series("ig_bond", "Investment-grade corporate bond ETF (price)", "daily", "stress", {"yahoo": "LQD"}, "research"),
        Series("treasury", "7-10y Treasury ETF (price)", "daily", "stress", {"yahoo": "IEF"}, "research"),
        Series("us10y", "10-year Treasury yield (%)", "daily", "growth", {"fred": "DGS10"}, "commercial"),
        Series("us2y", "2-year Treasury yield (%)", "daily", "growth", {"fred": "DGS2"}, "commercial"),
        Series("breakeven10", "10-year breakeven inflation (%)", "daily", "inflation", {"fred": "T10YIE"}, "commercial"),
        Series("claims", "Initial jobless claims", "weekly", "growth", {"fred": "ICSA"}, "commercial"),
        Series("indpro", "Industrial production index", "monthly", "growth", {"fred": "INDPRO"}, "commercial"),
        Series("cpi", "Consumer price index", "monthly", "inflation", {"fred": "CPIAUCSL"}, "commercial"),
    ]
}

REQUIRED = list(CATALOG)
