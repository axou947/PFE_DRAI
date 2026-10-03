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


@lru_cache
def world_fx():
    from pfe_drai.world import fetch_fx, fx_rates, load_markets

    settings = pipeline().settings
    prices = world_data()[0]
    fx, errors = fetch_fx(settings)
    rates = fx_rates(fx, load_markets(settings), prices.index, settings["world"]["fx_fill_days"])
    last = max((c.last_valid_index() for _, c in fx.items() if c.notna().any()), default=None)
    return rates, errors, last


@lru_cache
def world_link():
    from pfe_drai.world import link_to_us

    prices, ind, _ = world_data()
    return link_to_us(prices, ind, pipeline().settings)


@app.get("/world")
def world(
    date: str | None = None,
    horizon: Literal["1D", "1W", "1M", "3M", "YTD", "1Y"] = "1M",
    lang: Lang = "fr",
    currency: Literal["usd", "local"] = "usd",
):
    """Country equity markets (country ETFs as proxies): return over `horizon` and market stress state.

    The state is market-only (own volatility and drawdown, docs/WORLD.md), not the US macro regime.
    `currency=local` adds, per market, `return_local`, `currency` (USD return minus local return),
    `vol_local` and `fx_status` (ok, usd, pending: rate not yet published, missing); `return`
    and the state stay in USD. Exchange rates are never carried past their last published date.
    """
    from pfe_drai.world import breadth, load_markets, local_view, snapshot

    prices, ind, errors = world_data()
    settings = pipeline().settings
    day = prices.index[prices.index.searchsorted(pd.Timestamp(date or prices.index[-1]), side="right") - 1]
    markets = load_markets(settings)
    names = {m.id: m.name[lang] for m in markets}
    snap = snapshot(prices, ind, markets, day, horizon, settings["world"]["stale_days"])
    extra = []
    if currency == "local":
        rates, fx_errors, fx_last = world_fx()
        snap = snap.join(local_view(prices, rates, markets, day, horizon, settings["world"]["vol_window"]))
        extra = ["return_local", "currency", "vol_local"]
    rows = []
    for i, r in snap.iterrows():
        row = {
            "id": i,
            "name": names[i],
            "ticker": r["ticker"],
            "state": r["state"],
            "since": r["since"].date().isoformat() if r["since"] is not None else None,
            **{k: None if r[k] != r[k] else round(float(r[k]), 4) for k in ["close", "return", "vol", "vol_pct", "drawdown"]},
        }
        if currency == "local":
            row.update({k: None if r[k] != r[k] else round(float(r[k]), 4) for k in extra}, fx_status=r["fx_status"])
        rows.append(row)
    b = breadth(ind["state"]).loc[:day].iloc[-1]
    body = {
        "date": day.date().isoformat(),
        "horizon": horizon,
        "share_stress": round(float(b["stress"]), 4),
        "share_elevated": round(float(b["elevated"]), 4),
        "markets": rows,
        "not_loaded": errors,
    }
    if currency == "local":
        body.update(
            currency="local",
            fx_last_published=fx_last.date().isoformat() if fx_last is not None else None,
            fx_not_loaded=fx_errors,
        )
    return body


@app.get("/world/link")
def world_link_view(date: str | None = None, window: int = 252, lang: Lang = "fr"):
    """How closely each market moves with the US (SPY): rolling correlation and beta on 5-day returns.

    `window` is one of world.link.windows (business days). Also the same measures on days the US market
    is in stress or not, the 1-day lead/lag, and the average correlation of the other markets.
    Descriptive ("moves with"), not causal, not a forecast; Asian ETFs are biased by trading hours.
    """
    from pfe_drai.world import link_snapshot, load_markets

    prices = world_data()[0]
    settings = pipeline().settings
    windows = settings["world"]["link"]["windows"]
    if window not in windows:
        raise HTTPException(400, f"window must be one of {windows}")
    stats = world_link()
    day = prices.index[prices.index.searchsorted(pd.Timestamp(date or prices.index[-1]), side="right") - 1]
    markets = load_markets(settings)
    snap = link_snapshot(stats, markets, prices, day, window, settings["world"]["stale_days"])
    rows = [
        {
            "id": i,
            "name": next(m.name[lang] for m in markets if m.id == i),
            **{k: None if v != v else round(float(v), 4) for k, v in r.items()},
        }
        for i, r in snap.iterrows()
    ]
    avg = stats.avg_corr[window].loc[:day].dropna()
    return {
        "date": day.date().isoformat(),
        "window_days": window,
        "average_correlation": round(float(avg.iloc[-1]), 4) if len(avg) else None,
        "markets": rows,
    }


@app.get("/regime/explain")
def regime_explain(model: str | None = None, date: str | None = None, lang: Lang = "fr"):
    """Why the regime on `date` (default: latest) is what it is (docs/EXPLAIN.md).

    Each input's contribution to the three scores (today, a week and a month ago), the rule step that
    decides, the move each input would need alone to flip the rule, the highest stress source and the
    inputs that moved it since last week (occlusion). `text` holds the same in plain sentences.
    """
    from pfe_drai.explain import explain, sentences

    p = pipeline()
    probs = p.probabilities(_model(model))
    if date and pd.Timestamp(date) < probs.index[0]:
        raise HTTPException(404, t("api.not_found", lang))
    body = explain(p, _model(model), date)
    body["text"] = sentences(body, lang)
    return body


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
    r.pop("calibration")
    r["episodes"] = episodes.assign(start=episodes["start"].astype(str), end=episodes["end"].astype(str)).to_dict("records")
    return r


@app.get("/calibration")
def calibration(model: str | None = None, date: str | None = None):
    """Is P(stress) a probability? Brier, ECE, log loss and the reliability table (docs/CALIBRATION.md).

    Out-of-sample days whose outcome was known on `date` (default: all). For the calibrated
    `combined` model, the same scores for the uncalibrated detector score, and the calibrator in use.
    """
    from pfe_drai.validation.calibration import calibration_report, to_json

    p = pipeline()
    name = _model(model)
    out = {"model": name, "probability": to_json(p.calibration(name, date)), "calibrator": p.calibrator_fit(name, date)}
    score = p.alarm_score(name)
    if not score.equals(p.probabilities(name)["stress"]):
        out["detector_score"] = to_json(calibration_report(score, p.episodes, p.settings, until=date))
    return out


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
