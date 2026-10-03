"""Your own portfolio: weights pasted or uploaded as CSV, mapped to the scenario asset classes.

Read in memory only: nothing here writes a file, caches or publishes. One row per holding:

    holding,asset_class,weight
    MSCI World ETF,equity_world,40
    Euro govies,gov_bonds,35
    ...

- `asset_class` takes an id from config/scenarios.yaml (equity_world, gov_bonds...), its French or
  English name ("Actions monde", "Government bonds") or a common alias (govies, high yield, or...).
- `weight` in percent (summing to 100) or as fractions (summing to 1); "40 %" and "40,5" are read.
- `holding` is optional: rows of the same class add up, and the per-holding contribution is shown.
- Comma, semicolon (French Excel) or tab separated; header optional (2 columns = class, weight;
  3 columns = holding, class, weight).

Errors come back as codes with their line, so the app and the API can word them in FR or EN.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from ..i18n import t
from .library import Fund, Scenario

MAX_ROWS = 500
MAX_BYTES = 200_000
TOLERANCE_PCT = 0.5  # weights must sum to 100 within ±0.5 point (rounding in a broker export)

HOLDING_COLUMNS = {"holding", "name", "nom", "ligne", "titre", "security", "fund", "fonds", "ticker", "isin", "position"}
ASSET_COLUMNS = {
    "asset",
    "asset_class",
    "assetclass",
    "class",
    "classe",
    "classe_d_actif",
    "classe_actif",
    "actif",
    "category",
    "categorie",
}
WEIGHT_COLUMNS = {
    "weight",
    "weight_pct",
    "weight_percent",
    "weights",
    "poids",
    "poids_pct",
    "pct",
    "percent",
    "allocation",
    "share",
    "part",
}

# Common names people use for the scenario classes, beyond the ids and the FR/EN labels.
ALIASES = {
    "equity_world": [
        "world_equity",
        "world_equities",
        "global_equity",
        "global_equities",
        "actions_monde",
        "actions_internationales",
        "msci_world",
        "acwi",
    ],
    "equity_europe": [
        "europe_equity",
        "european_equity",
        "european_equities",
        "actions_europe",
        "actions_europeennes",
        "actions_zone_euro",
        "stoxx_600",
    ],
    "gov_bonds": [
        "government_bonds",
        "govies",
        "sovereign_bonds",
        "sovereigns",
        "treasuries",
        "obligations_d_etat",
        "obligations_souveraines",
        "emprunts_d_etat",
    ],
    "ig_credit": [
        "investment_grade",
        "ig",
        "corporate_bonds",
        "credit_ig",
        "obligations_d_entreprises",
        "credit_investment_grade",
    ],
    "hy_credit": ["high_yield", "hy", "credit_hy", "haut_rendement", "obligations_haut_rendement", "junk_bonds"],
    "gold": ["or", "xau"],
    "commodities": ["commodity", "matieres_premieres", "matiere_premiere"],
    "cash": ["liquidites", "monetaire", "money_market", "tresorerie", "fonds_euros"],
}


@dataclass
class Holding:
    line: int
    name: str
    asset: str
    weight: float  # fraction of the portfolio


@dataclass
class Portfolio:
    holdings: list[Holding]
    weights: dict[str, float]  # per asset class, fractions summing to 1
    unit: str  # "percent" or "fraction", as read
    warnings: list[dict] = field(default_factory=list)

    def fund(self) -> Fund:
        return Fund(id="own", name={"fr": t("portfolio.name", "fr"), "en": t("portfolio.name", "en")}, weights=self.weights)


class PortfolioError(ValueError):
    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__("; ".join(f"{e['code']} {e}" for e in errors))


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def asset_lookup(assets: list[str]) -> dict[str, str]:
    """Normalised name -> asset id: ids, FR and EN labels, aliases."""
    table = {}
    for a in assets:
        for name in [a, t(f"asset.{a}", "fr"), t(f"asset.{a}", "en"), *ALIASES.get(a, [])]:
            table[_norm(name)] = a
    return table


def _number(text: str) -> float | None:
    s = str(text).strip().replace(" ", "").replace(" ", "").rstrip("%")
    if "," in s and "." not in s:
        s = s.replace(",", ".")  # French decimal comma
    try:
        return float(s)
    except ValueError:
        return None


def _rows(text: str) -> list[list[str]]:
    sample = "\n".join(text.splitlines()[:20])
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def decode(data: bytes | str) -> str:
    if isinstance(data, str):
        return data
    for encoding in ("utf-8-sig", "cp1252"):  # Excel on Windows saves CSV as cp1252
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def parse_portfolio(data: bytes | str, assets: list[str]) -> Portfolio:
    """Read a portfolio CSV; raise PortfolioError with every problem found (not just the first)."""
    raw = data if isinstance(data, bytes) else data.encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise PortfolioError([{"code": "too_big", "limit": f"{MAX_BYTES // 1000} KB"}])
    text = decode(data)
    numbered = [(i + 1, row) for i, row in enumerate(_rows(text)) if any(c for c in row) and not row[0].startswith("#")]
    if not numbered:
        raise PortfolioError([{"code": "empty"}])

    first_line, first = numbered[0]
    names = [_norm(c) for c in first]
    has_header = all(_number(c) is None for c in first)
    if has_header:
        numbered = numbered[1:]
        col = {"holding": None, "asset": None, "weight": None}
        for j, n in enumerate(names):
            for key, accepted in (("holding", HOLDING_COLUMNS), ("asset", ASSET_COLUMNS), ("weight", WEIGHT_COLUMNS)):
                if n in accepted and col[key] is None:
                    col[key] = j
        if col["weight"] is None and len(first) - 1 not in (col["asset"], col["holding"]):
            col["weight"] = len(first) - 1  # e.g. a "%" or "Montant (%)" header: the last column
        if col["asset"] is None:
            raise PortfolioError([{"code": "no_asset_column", "line": first_line, "columns": ", ".join(first)}])
        if col["weight"] is None:
            raise PortfolioError([{"code": "no_weight_column", "line": first_line, "columns": ", ".join(first)}])
    else:
        width = max(len(r) for _, r in numbered)
        col = {"holding": 0, "asset": 1, "weight": 2} if width >= 3 else {"holding": None, "asset": 0, "weight": 1}
    if not numbered:
        raise PortfolioError([{"code": "empty"}])
    if len(numbered) > MAX_ROWS:
        raise PortfolioError([{"code": "too_many_rows", "limit": MAX_ROWS}])

    lookup = asset_lookup(assets)
    errors, rows = [], []

    def cell(row: list[str], key: str) -> str:
        j = col[key]
        return row[j] if j is not None and j < len(row) else ""

    for line, row in numbered:
        label, weight_text = cell(row, "asset"), cell(row, "weight")
        asset = lookup.get(_norm(label))
        weight = _number(weight_text)
        if not label:
            errors.append({"code": "missing_asset", "line": line})
        elif asset is None:
            errors.append({"code": "unknown_asset", "line": line, "value": label})
        if weight is None:
            errors.append({"code": "bad_weight", "line": line, "value": weight_text})
        elif weight < 0:
            errors.append({"code": "negative_weight", "line": line, "value": weight_text})
        if asset is not None and weight is not None and weight >= 0:
            rows.append((line, cell(row, "holding") or label, asset, weight))
    if errors:
        if any(e["code"] == "unknown_asset" for e in errors):
            errors.append({"code": "accepted", "values": ", ".join(assets)})
        if any(e["code"] == "unknown_asset" and _number(e["value"]) is not None for e in errors):
            errors.append({"code": "decimal_comma"})  # "Gold,2,5" read as three columns
        raise PortfolioError(errors)

    total = sum(w for *_, w in rows)
    if abs(total - 1) <= TOLERANCE_PCT / 100 and all(w <= 1 for *_, w in rows):
        unit, scale = "fraction", 1.0
    elif abs(total - 100) <= TOLERANCE_PCT:
        unit, scale = "percent", 100.0
    else:
        raise PortfolioError([{"code": "bad_sum", "total": round(total, 2)}])

    holdings = [Holding(line, name, asset, w / scale) for line, name, asset, w in rows]
    s = sum(h.weight for h in holdings)
    holdings = [Holding(h.line, h.name, h.asset, h.weight / s) for h in holdings]  # rounding gap spread pro rata
    weights = {a: 0.0 for a in assets}
    for h in holdings:
        weights[h.asset] += h.weight
    warnings = []
    if abs(total - scale) > 1e-9:
        warnings.append({"code": "rescaled", "total": round(total, 2)})
    return Portfolio(holdings=holdings, weights=weights, unit=unit, warnings=warnings)


def messages(problems: list[dict], lang: str) -> list[str]:
    """Each error or warning in words, with its line when it has one."""
    out = []
    for p in problems:
        params = {k: v for k, v in p.items() if k not in ("code", "line")}
        text = t(f"portfolio.err.{p['code']}", lang, **params) if params else t(f"portfolio.err.{p['code']}", lang)
        out.append(t("portfolio.line", lang, line=p["line"], text=text) if "line" in p else text)
    return out


def holdings_impact(portfolio: Portfolio, scenarios: list[Scenario], ids: list[str]) -> pd.DataFrame:
    """Contribution of each holding (weight x its class shock) under each scenario: rows = holdings."""
    by_id = {s.id: s for s in scenarios}
    return pd.DataFrame(
        {sid: [h.weight * by_id[sid].shocks.get(h.asset, 0.0) for h in portfolio.holdings] for sid in ids},
        index=[h.name for h in portfolio.holdings],
    )


def template(assets: list[str], lang: str = "en") -> str:
    """A CSV to start from: one example holding per class, summing to 100."""
    example = {
        "equity_world": 40,
        "equity_europe": 10,
        "gov_bonds": 25,
        "ig_credit": 15,
        "hy_credit": 0,
        "gold": 5,
        "commodities": 0,
        "cash": 5,
    }
    head = "holding,asset_class,weight" if lang == "en" else "ligne;classe_d_actif;poids"
    sep = "," if lang == "en" else ";"
    lines = [head] + [f"{t(f'asset.{a}', lang)}{sep}{a}{sep}{example.get(a, 0)}" for a in assets]
    return "\n".join(lines) + "\n"
