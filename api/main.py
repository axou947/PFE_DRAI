"""REST API: uvicorn api.main:app --reload   (docs at http://localhost:8000/docs)."""

from functools import lru_cache
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from pfe_drai.i18n import t
from pfe_drai.models import available_models
from pfe_drai.pipeline import Pipeline
from pfe_drai.reporting import build_note, to_html, to_markdown, to_pdf
from pfe_drai.scenarios import impact_table, load_funds, load_library, rank_scenarios

app = FastAPI(title="PFE DRAI", description="Market regime detection API", version="0.1.0")
Lang = Literal["fr", "en"]


@lru_cache
def pipeline() -> Pipeline:
    return Pipeline()


def _model(model: str | None) -> str:
    model = model or pipeline().settings["models"]["default"]
    if model not in available_models():
        raise HTTPException(400, f"Unknown model '{model}'")
    return model


@app.get("/health")
def health():
    p = pipeline()
    return {"status": "ok", "data_provider": p.provider.name, "is_live_data": p.provider.is_live}


@app.get("/regime")
def regime(model: str | None = None, date: str | None = None, lang: Lang = "fr"):
    """Regime and probabilities on a date (default: latest)."""
    p = pipeline()
    probs = p.probabilities(_model(model))
    if date and pd.Timestamp(date) < probs.index[0]:
        raise HTTPException(404, t("api.not_found", lang))
    state = p.state(_model(model), date).to_dict()
    state["regime_label"] = t(f"regime.{state['regime']}", lang)
    return state


@app.get("/regime/history")
def history(model: str | None = None, start: str | None = None, end: str | None = None):
    probs = pipeline().probabilities(_model(model)).loc[start:end]
    return [
        {"date": d.date().isoformat(), "regime": row.idxmax(), **{k: round(float(v), 4) for k, v in row.items()}}
        for d, row in probs.iterrows()
    ]


@lru_cache
def world_data():
    from pfe_drai.world import fetch_prices, indicators

    settings = pipeline().settings
    prices, errors = fetch_prices(settings)
    return prices, indicators(prices, settings), errors


@app.get("/world")
def world(date: str | None = None, horizon: Literal["1D", "1W", "1M", "3M", "YTD", "1Y"] = "1M", lang: Lang = "fr"):
    """Country equity markets (country ETFs as proxies): return over `horizon` and market stress state.

    The state is market-only (own volatility and drawdown, docs/WORLD.md), not the US macro regime.
    """
    from pfe_drai.world import breadth, load_markets, snapshot

    prices, ind, errors = world_data()
    settings = pipeline().settings
    day = prices.index[prices.index.searchsorted(pd.Timestamp(date or prices.index[-1]), side="right") - 1]
    markets = load_markets(settings)
    names = {m.id: m.name[lang] for m in markets}
    snap = snapshot(prices, ind, markets, day, horizon, settings["world"]["stale_days"])
    rows = []
    for i, r in snap.iterrows():
        rows.append(
            {
                "id": i,
                "name": names[i],
                "ticker": r["ticker"],
                "state": r["state"],
                "since": r["since"].date().isoformat() if r["since"] is not None else None,
                **{k: None if r[k] != r[k] else round(float(r[k]), 4) for k in ["close", "return", "vol", "vol_pct", "drawdown"]},
            }
        )
    b = breadth(ind["state"]).loc[:day].iloc[-1]
    return {
        "date": day.date().isoformat(),
        "horizon": horizon,
        "share_stress": round(float(b["stress"]), 4),
        "share_elevated": round(float(b["elevated"]), 4),
        "markets": rows,
        "not_loaded": errors,
    }


@app.get("/regime/states")
def regime_states(model: str | None = None, date: str | None = None, lang: Lang = "fr"):
    """How the model's unsupervised states map to the regimes (docs/REGIMES.md).

    One entry per walk-forward refit up to `date` (default: all), each with its state table:
    name, training days, share of those days in each rule regime, centroid on the 3 dimensions.
    """
    p = pipeline()
    maps = p.state_maps(_model(model))
    if not maps:
        raise HTTPException(404, f"Model '{_model(model)}' predicts the rule regimes directly: no states to map")
    if date:
        maps = [m for m in maps if m[0] <= pd.Timestamp(date)] or maps[:1]
    return [
        {
            "first_day_predicted": start.date().isoformat(),
            "states": [{**row, "name_label": t(f"regime.{row['name']}", lang)} for row in table.reset_index().to_dict("records")],
        }
        for start, table in maps
    ]


@app.get("/metrics")
def metrics(model: str | None = None):
    r = pipeline().evaluate(_model(model))
    episodes = r.pop("episodes")
    r.pop("reliability")
    r["episodes"] = episodes.assign(start=episodes["start"].astype(str), end=episodes["end"].astype(str)).to_dict("records")
    return r


@app.get("/scenarios")
def scenarios(fund: str = "balanced", model: str | None = None, lang: Lang = "fr", top_k: int = Query(3, ge=1, le=20)):
    p = pipeline()
    state = p.state(_model(model))
    _, library = load_library(p.settings)
    funds = {f.id: f for f in load_funds(p.settings)}
    if fund not in funds:
        raise HTTPException(404, f"Unknown fund '{fund}'. Available: {', '.join(funds)}")
    ranking = rank_scenarios(library, pd.Series(state.scores), pd.Series(state.probabilities)).head(top_k)
    impacts = impact_table(funds[fund], library, list(ranking["id"])).set_index("id")
    names = {s.id: s.name[lang] for s in library}
    return [
        {**row, "name": names[row["id"]], "fund_impact": float(impacts.loc[row["id"], "total"])}
        for row in ranking.to_dict("records")
    ]


@app.get("/report")
def report(lang: Lang = "fr", model: str | None = None, fmt: Literal["md", "html", "pdf"] = "md"):
    note = build_note(pipeline(), lang, _model(model))
    if fmt == "pdf":
        return Response(to_pdf(note), media_type="application/pdf")
    if fmt == "html":
        return HTMLResponse(to_html(note))
    return PlainTextResponse(to_markdown(note), media_type="text/markdown")
