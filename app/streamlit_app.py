"""PFE DRAI dashboard: python -m pfe_drai app  (or: streamlit run app/streamlit_app.py)."""

import os
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pfe_drai.config import load_settings, resolve  # noqa: E402
from pfe_drai.data import available_providers  # noqa: E402
from pfe_drai.features import FEATURES  # noqa: E402
from pfe_drai.i18n import fmt_date, fmt_num, fmt_pct, t  # noqa: E402
from pfe_drai.models import available_models  # noqa: E402
from pfe_drai.pipeline import Pipeline  # noqa: E402
from pfe_drai.publish.page import page_html  # noqa: E402
from pfe_drai.reporting import build_note, to_html, to_markdown, to_pdf  # noqa: E402
from pfe_drai.scenarios import Fund, impact_table, load_funds, load_library, rank_scenarios  # noqa: E402
from pfe_drai.validation import evaluate  # noqa: E402
from pfe_drai.validation.calibration import calibration_report  # noqa: E402
from pfe_drai.world import (  # noqa: E402
    HORIZONS,
    REGIONS,
    STATES,
    breadth,
    fetch_prices,
    indicators,
    load_markets,
    load_replay,
    snapshot,
)

st.set_page_config(page_title="PFE DRAI", page_icon="📈", layout="wide")

TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e8e7e3"
DIM_COLORS = {"stress": "#2a78d6", "growth": "#eb6834", "inflation": "#1baf7a"}  # validated all-pairs trio

st.markdown(
    """<style>
    .regime-card{border-left:6px solid var(--c);background:#f3f2ef;border-radius:6px;padding:14px 18px}
    .regime-card .label{color:#52514e;font-size:0.85rem;margin:0}
    .regime-card .name{font-size:1.7rem;font-weight:700;margin:2px 0}
    .regime-card .desc{color:#52514e;margin:0}
    .chip{display:inline-block;padding:1px 8px;border-radius:10px;border:1px solid #d6d5d0;font-size:0.8rem;margin-right:6px}
    </style>""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- data & cache
@st.cache_resource(show_spinner=False)
def get_pipeline(provider: str) -> Pipeline:
    return Pipeline(load_settings(overrides={"data": {"provider": provider}}))


@st.cache_data(show_spinner=False)
def get_probs(provider: str, model: str) -> pd.DataFrame:
    return get_pipeline(provider).probabilities(model)


@st.cache_data(show_spinner=False, ttl=3600)
def get_world(provider: str):
    settings = load_settings()
    prices, errors = fetch_prices(settings, provider)
    return prices, indicators(prices, settings), errors


@st.cache_data(show_spinner=False)
def get_track_record_page(provider: str, lang: str, files: tuple) -> str:
    """The public track-record page (docs/TRACK_RECORD.md), rebuilt when a file of track_record/ changes.

    Built on the configured settings, not on the sidebar threshold: the record is frozen.
    """
    frozen = Pipeline(load_settings(overrides={"data": {"provider": provider}}))
    frozen.__dict__["raw"] = get_pipeline(provider).raw  # same data, fetched once
    return page_html(frozen, resolve(settings["publish"]["dir"]), lang)


def base_layout(fig: go.Figure, height: int = 320, **kw) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(color=TEXT, size=13),
        legend=dict(orientation="h", y=-0.15),
        hoverlabel=dict(font_size=13),
        **kw,
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


# ---------------------------------------------------------------- sidebar
settings = load_settings()
lang_label = st.sidebar.radio("Langue / Language", ["Français", "English"], horizontal=True)
lang = "fr" if lang_label == "Français" else "en"

st.sidebar.header(t("app.settings", lang))
providers = available_providers()
# `python -m pfe_drai --provider fred app` passes its choice through PFE_DRAI_PROVIDER.
default_provider = os.environ.get("PFE_DRAI_PROVIDER") or settings["data"]["provider"]
provider = st.sidebar.selectbox(t("app.data_source", lang), providers, index=providers.index(default_provider))
models = available_models()
model = st.sidebar.selectbox(
    t("app.model", lang), models, index=models.index(settings["models"]["default"]), format_func=lambda m: t(f"model.{m}", lang)
)

try:
    pipeline = get_pipeline(provider)
    with st.spinner(t("app.loading", lang)):
        probs = get_probs(provider, model)
        early_probs = get_probs(provider, "gbm")
except Exception as exc:  # noqa: BLE001 - show the reason instead of a stack trace
    st.error(f"{type(exc).__name__}: {exc}")
    st.stop()

dates = probs.index
as_of = st.sidebar.date_input(t("app.as_of", lang), value=dates[-1].date(), min_value=dates[0].date(), max_value=dates[-1].date())
as_of = dates[dates.searchsorted(pd.Timestamp(as_of), side="right") - 1]
threshold = st.sidebar.slider(
    t("app.stress_threshold", lang), 0.2, 0.9, float(settings["validation"]["stress_probability_threshold"]), 0.05
)
pipeline.settings["validation"]["stress_probability_threshold"] = threshold
pipeline.settings["alerts"]["stress_probability"] = threshold

if pipeline.provider.is_live:
    st.sidebar.success(t("app.live_data", lang))
else:
    st.sidebar.warning(t("app.synthetic_warning", lang))
with st.sidebar.expander(t("app.methodology", lang)):
    st.write(t("method.text", lang))
st.sidebar.caption(t("disclaimer", lang))

regimes = settings["regimes"]["order"]
colors = settings["regimes"]["colors"]
reg = lambda r: t(f"regime.{r}", lang)  # noqa: E731
state = pipeline.state(model, as_of)

st.title(t("app.title", lang))
st.caption(f"{t('app.subtitle', lang)} · {fmt_date(state.date, lang)}")

tab_dash, tab_world, tab_hist, tab_track, tab_alerts, tab_scen = st.tabs(
    [
        t("tab.dashboard", lang),
        t("tab.world", lang),
        t("tab.history", lang),
        t("tab.track_record", lang),
        t("tab.alerts", lang),
        t("tab.scenarios", lang),
    ]
)

# ================================================================ DASHBOARD
with tab_dash:
    c1, c2 = st.columns([1, 1.3])
    with c1:
        p_now = state.probabilities[state.regime]
        st.markdown(
            f"""<div class="regime-card" style="--c:{colors[state.regime]}">
            <p class="label">{t("dash.current_regime", lang)} · {t(f"model.{model}", lang)}</p>
            <p class="name">{reg(state.regime)}</p>
            <p class="desc">{t(f"regime.{state.regime}.desc", lang)}</p>
            <p class="label" style="margin-top:8px">{t("dash.confidence", lang)} : <b>{fmt_pct(p_now, lang)}</b></p>
            </div>""",
            unsafe_allow_html=True,
        )
        alarm = state.alarm
        if alarm["on"]:
            st.error(t("dash.alarm_on", lang, date=fmt_date(pd.Timestamp(alarm["since"]), lang)), icon="🚨")
        else:
            st.success(t("dash.alarm_off", lang))
        st.caption(
            t(
                "dash.alarm_help",
                lang,
                score=fmt_pct(alarm["score"], lang),
                threshold=fmt_pct(alarm["threshold"], lang),
                days=alarm["confirm_days"],
            )
        )
        if state.early_warning:
            st.metric(t("dash.early_warning", lang), fmt_pct(state.early_warning["stress"], lang))
    with c2:
        st.subheader(t("dash.probabilities", lang))
        values = [state.probabilities[r] for r in regimes]
        fig = go.Figure(
            go.Bar(
                x=values,
                y=[reg(r) for r in regimes],
                orientation="h",
                marker_color=[colors[r] for r in regimes],
                text=[fmt_pct(v, lang) for v in values],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{y}: %{x:.1%}<extra></extra>",
            )
        )
        fig.update_xaxes(range=[0, 1.12], tickformat=".0%")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(base_layout(fig, 220, showlegend=False), width="stretch")
        if (state.calibration.get("calibrator") or {}).get("calibrated"):
            st.caption(t("dash.calibrated", lang))

    st.subheader(t("dash.dimensions", lang))
    cols = st.columns(3)
    for col, dim in zip(cols, ["stress", "growth", "inflation"], strict=True):
        delta = state.scores[dim] - state.previous["scores"][dim]
        col.metric(
            t(f"dimension.{dim}", lang),
            fmt_num(state.scores[dim], lang),
            fmt_num(delta, lang),
            delta_color="inverse" if dim in ("stress", "inflation") else "normal",
        )
    st.caption(t("dash.dimension_help", lang))

    with st.expander(t("dash.states", lang)):
        rule = settings["regimes"]["rule"]
        st.markdown(t("dash.states_rule", lang, **{k: fmt_num(v, lang).lstrip("+") for k, v in rule.items()}))
        table = pipeline.state_map(model, as_of)
        if table is None:
            st.markdown(t("dash.states_none", lang))
        else:
            unsupervised = pipeline.unsupervised_model(model)
            st.markdown(t("dash.states_help", lang, model=t(f"model.{unsupervised}", lang)))
            dims = ["stress", "growth", "inflation"]
            labels = [t("dash.state_label", lang, n=i + 1, name=reg(row["name"])) for i, (_, row) in enumerate(table.iterrows())]
            st.dataframe(
                pd.DataFrame(
                    {
                        t("dash.state", lang): labels,
                        **{t(f"dimension.{d}", lang): table[d].map(lambda v: fmt_num(v, lang)) for d in dims},
                        t("dash.state_distance", lang): table["distance"].map(lambda v: fmt_num(v, lang).lstrip("+")),
                        t("dash.state_days", lang): table["days"],
                        t("dash.state_agreement", lang): table["purity"].map(lambda v: fmt_pct(v, lang)),
                    }
                ),
                hide_index=True,
                width="stretch",
            )
            fig = go.Figure()
            for r in regimes:
                fig.add_bar(
                    y=labels,
                    x=table[f"share_{r}"],
                    orientation="h",
                    name=reg(r),
                    marker_color=colors[r],
                    hovertemplate="%{y}<br>" + reg(r) + ": %{x:.0%}<extra></extra>",
                )
            fig.update_xaxes(range=[0, 1], tickformat=".0%")
            fig.update_yaxes(autorange="reversed")
            fig = base_layout(fig, 90 + 40 * len(table), barmode="stack")
            st.plotly_chart(fig.update_layout(legend_traceorder="normal"), width="stretch")
            st.caption(t("dash.states_shares", lang))

            # The three dimensions together: a dot every 5 days, colored by the regime the rule gives it.
            history = pipeline.scores.loc[:as_of].iloc[::5]
            rule_days = pipeline.labels.loc[history.index]
            fig = go.Figure()
            for r in regimes:
                pts = history[rule_days == r]
                fig.add_scatter3d(
                    x=pts["growth"],
                    y=pts["inflation"],
                    z=pts["stress"],
                    mode="markers",
                    name=reg(r),
                    marker=dict(size=2, color=colors[r], opacity=0.4),
                    hoverinfo="skip",
                )
            fig.add_scatter3d(
                x=table["growth"],
                y=table["inflation"],
                z=table["stress"],
                mode="markers+text",
                name=t("dash.state", lang),
                text=[str(i + 1) for i in range(len(table))],
                hovertext=labels,
                hoverinfo="text",
                marker=dict(size=7, color=TEXT, symbol="diamond"),
            )
            now = pipeline.scores.loc[as_of]
            fig.add_scatter3d(
                x=[now["growth"]],
                y=[now["inflation"]],
                z=[now["stress"]],
                mode="markers",
                name=fmt_date(as_of, lang),
                marker=dict(size=9, color=colors[state.regime], line=dict(color=TEXT, width=2)),
            )
            axes = {"xaxis": "growth", "yaxis": "inflation", "zaxis": "stress"}
            fig.update_layout(scene={k: dict(title=t(f"dimension.{d}", lang)) for k, d in axes.items()} | {"aspectmode": "cube"})
            st.plotly_chart(base_layout(fig, 520).update_layout(legend_itemsizing="constant"), width="stretch")
            st.caption(t("dash.states_cube", lang))

    c1, c2 = st.columns(2)
    with c1:
        st.subheader(t("dash.changes", lang))
        prev = state.previous
        if prev["regime"] != state.regime:
            st.markdown(f"- {t('dash.regime_changed', lang, old=reg(prev['regime']), new=reg(state.regime))}")
        else:
            st.markdown(f"- {t('dash.regime_same', lang, regime=reg(state.regime))}")
        for r in regimes:
            old, new = prev["probabilities"][r], state.probabilities[r]
            if abs(new - old) >= 0.05:
                st.markdown(f"- {t('dash.prob_move', lang, regime=reg(r), old=fmt_pct(old, lang), new=fmt_pct(new, lang))}")
        moves = {k: state.drivers[k] - prev["drivers"][k] for k in state.drivers}
        for k, v in sorted(moves.items(), key=lambda kv: -abs(kv[1]))[:3]:
            st.markdown(f"- {t(f'feature.{k}', lang)} : {fmt_num(v, lang)}")
    with c2:
        st.subheader(t("dash.flip", lang))
        for dim, dist in state.flip.items():
            if dist <= 0:
                st.markdown(f"- {t('dash.flip_crossed', lang, dimension=t(f'dimension.{dim}', lang))}")
            else:
                st.markdown(f"- {t(f'dash.flip_{dim}', lang, value=fmt_num(dist, lang).lstrip('+'))}")

    st.subheader(t("dash.drivers", lang))
    names = list(FEATURES)
    fig = go.Figure()
    for dim in ["stress", "growth", "inflation"]:
        feats = [f for f in names if FEATURES[f] == dim]
        fig.add_bar(
            y=[t(f"feature.{f}", lang) for f in feats],
            x=[state.drivers[f] for f in feats],
            orientation="h",
            name=t(f"dimension.{dim}", lang),
            marker_color=DIM_COLORS[dim],
            hovertemplate="%{y}: %{x:+.2f}<extra></extra>",
        )
    fig.update_yaxes(autorange="reversed")
    fig.add_vline(x=0, line_color=MUTED, line_width=1)
    st.plotly_chart(base_layout(fig, 420, bargap=0.25), width="stretch")
    st.caption(t("dash.drivers_help", lang))

    st.subheader(t("dash.timeline", lang))
    equity = pipeline.prices["equity"].loc[probs.index[0] : as_of]
    path = probs.loc[:as_of].idxmax(axis=1)
    fig = go.Figure()
    block = (path != path.shift()).cumsum()
    for _, seg in path.groupby(block):
        fig.add_vrect(
            x0=seg.index[0],
            x1=seg.index[-1] + pd.Timedelta(days=1),
            fillcolor=colors[seg.iloc[0]],
            opacity=0.22,
            line_width=0,
            layer="below",
        )
    fig.add_scatter(
        x=equity.index,
        y=equity.values,
        mode="lines",
        line=dict(color=TEXT, width=2),
        name=t("dash.equity_index", lang),
        hovertemplate="%{x|%d/%m/%Y}: %{y:.0f}<extra></extra>",
    )
    fig.update_xaxes(type="date")
    fig.update_yaxes(type="log")
    fig.update_xaxes(
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1a" if lang == "fr" else "1y", step="year", stepmode="backward"),
                dict(count=5, label="5a" if lang == "fr" else "5y", step="year", stepmode="backward"),
                dict(step="all", label="Tout" if lang == "fr" else "All"),
            ]
        )
    )
    st.plotly_chart(base_layout(fig, 420, hovermode="x unified", showlegend=False), width="stretch")
    st.markdown(
        " ".join(
            f"<span class='chip' style='border-color:{colors[r]}'><span style='color:{colors[r]}'>■</span> {reg(r)}</span>"
            for r in regimes
        ),
        unsafe_allow_html=True,
    )

# ================================================================ WORLD MARKETS
STATE_COLORS = {"calm": "#1baf7a", "elevated": "#eda100", "stress": "#d6453d", None: "#4a5363"}
MAP_BG, MAP_LAND, MAP_BORDER, MAP_TEXT = "#0d1117", "#1c2330", "#2d3646", "#e6edf3"
REGION_VIEW = {
    "world": dict(projection_type="natural earth", lataxis_range=[-58, 84], lonaxis_range=[-180, 180]),
    "europe": dict(projection_type="mercator", lataxis_range=[34, 70], lonaxis_range=[-28, 48]),
    "americas": dict(projection_type="mercator", lataxis_range=[-50, 62], lonaxis_range=[-135, -30]),
    "asia": dict(projection_type="mercator", lataxis_range=[-45, 52], lonaxis_range=[30, 158]),
}


def fmt_ret(value: float, lang: str) -> str:
    if value != value:  # NaN
        return "–"
    text = f"{value * 100:+.1f}"
    return f"{text.replace('.', ',')} %" if lang == "fr" else f"{text}%"


def state_chip(code, lang: str) -> str:
    label = t(f"world.state.{code or 'none'}", lang)
    color = STATE_COLORS[code]
    return f"<span class='chip' style='border-color:{color}'><span style='color:{color}'>■</span> {label}</span>"


with tab_world:
    w_cfg = settings["world"]
    markets = load_markets(settings)
    by_market = {m.id: m for m in markets}
    try:
        w_prices, w_ind, w_errors = get_world(provider)
    except Exception as exc:  # noqa: BLE001 - show the reason, keep the other tabs working
        st.error(f"{type(exc).__name__}: {exc}")
        w_prices = None

    if w_prices is not None:
        first_day, last_day = w_prices.index[0].date(), w_prices.index[-1].date()
        if "world_date" not in st.session_state:
            st.session_state["world_date"] = min(max(as_of.date(), first_day), last_day)
        replay = {r["date"].date(): r["name"][lang] for r in load_replay(settings) if first_day <= r["date"].date() <= last_day}

        def _replay():
            pick = st.session_state.get("world_replay")
            if pick is not None:
                st.session_state["world_date"] = pick

        c = st.columns([2.3, 2.6, 1.1, 1.1, 1.6])
        mode = (
            c[0].segmented_control(
                t("world.mode", lang), ["stress", "returns"], default="stress", format_func=lambda x: t(f"world.mode.{x}", lang)
            )
            or "stress"
        )
        horizon = c[1].segmented_control(t("world.horizon", lang), HORIZONS, default="1M") or "1M"
        region = c[2].selectbox(t("world.region", lang), REGIONS, format_func=lambda x: t(f"world.region.{x}", lang))
        c[3].date_input(t("world.date", lang), min_value=first_day, max_value=last_day, key="world_date")
        c[4].selectbox(
            t("world.replay", lang),
            [None, *replay],
            format_func=lambda d: "–" if d is None else f"{replay[d]} ({fmt_date(d, lang)})",
            key="world_replay",
            on_change=_replay,
        )
        day = w_prices.index[w_prices.index.searchsorted(pd.Timestamp(st.session_state["world_date"]), side="right") - 1]
        snap = snapshot(w_prices, w_ind, markets, day, horizon, w_cfg["stale_days"])
        names = {m.id: m.name[lang] for m in markets}

        # ---- headline numbers
        known = snap["state"].notna().sum()
        m = st.columns(4)
        m[0].metric(t("world.in_stress", lang), f"{(snap['state'] == 'stress').sum()} / {known}")
        m[1].metric(t("world.in_elevated", lang), f"{(snap['state'] == 'elevated').sum()} / {known}")
        m[2].metric(t("world.median_return", lang, horizon=horizon), fmt_ret(snap["return"].median(), lang))
        if probs.index[0] <= day:
            m[3].metric(t("world.us_regime", lang), reg(probs.loc[:day].iloc[-1].idxmax()))
        else:
            m[3].metric(t("world.us_regime", lang), "–", t("world.us_regime_none", lang), delta_color="off")

        # ---- map
        ids = list(snap.index)
        state_label = {code: t(f"world.state.{code or 'none'}", lang) for code in [*STATES, None]}
        hover = [
            f"<b>{names[i]}</b> · {r['ticker']}<br>{state_label[r['state']]}"
            f"<br>{horizon}: {fmt_ret(r['return'], lang)}<br>{t('world.drawdown', lang)}: {fmt_ret(r['drawdown'], lang)}"
            for i, r in snap.iterrows()
        ]
        fig = go.Figure()
        if mode == "returns":
            z = snap["return"] * 100
            lim = max(1.0, float(z.abs().quantile(0.9))) if z.notna().any() else 1.0
            fig.add_choropleth(
                locations=ids,
                z=z,
                zmin=-lim,
                zmax=lim,
                colorscale=[[0, "#d6453d"], [0.5, "#2b3442"], [1, "#1baf7a"]],
                colorbar=dict(title=dict(text="%", font_color=MAP_TEXT), tickfont_color=MAP_TEXT, len=0.6, thickness=12, x=0.99),
                text=hover,
                hovertemplate="%{text}<extra></extra>",
                marker_line_color=MAP_BG,
                marker_line_width=0.6,
            )
            title = t("world.map_title_returns", lang, horizon=horizon, date=fmt_date(day, lang))
        else:
            code = snap["state"].map({"calm": 0, "elevated": 1, "stress": 2}).fillna(3)
            steps = [STATE_COLORS[s] for s in [*STATES, None]]
            fig.add_choropleth(
                locations=ids,
                z=code,
                zmin=0,
                zmax=3,
                colorscale=[[k / 4 + e / 4, col] for k, col in enumerate(steps) for e in (0, 1)],
                showscale=False,
                text=hover,
                hovertemplate="%{text}<extra></extra>",
                marker_line_color=MAP_BG,
                marker_line_width=0.6,
            )
            title = t("world.map_title_stress", lang, date=fmt_date(day, lang))
        # Labels: tickers (and returns); small European and Asian markets only when zoomed in.
        small = {i for i in ids if by_market[i].region == "europe"} | {"KOR", "TWN"}
        shown = [i for i in ids if region != "world" or i not in small]
        fig.add_scattergeo(
            locations=shown,
            text=[
                snap.loc[i, "ticker"] + (f" {fmt_ret(snap.loc[i, 'return'], lang)}" if mode == "returns" else "") for i in shown
            ],
            mode="text",
            textfont=dict(color="#ffffff", size=11, family="Arial Black, Arial"),
            hoverinfo="skip",
        )
        selected = st.session_state.get("world_market", "USA")
        if selected in ids:
            fig.add_choropleth(
                locations=[selected],
                z=[0],
                colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
                showscale=False,
                marker_line_color="#ffffff",
                marker_line_width=2.5,
                hoverinfo="skip",
            )
        fig.update_geos(
            showframe=False,
            showcoastlines=False,
            showland=True,
            landcolor=MAP_LAND,
            showcountries=True,
            countrycolor=MAP_BORDER,
            showlakes=False,
            showocean=True,
            oceancolor=MAP_BG,
            bgcolor=MAP_BG,
            **REGION_VIEW[region],
        )
        fig.update_layout(
            height=540,
            margin=dict(l=0, r=0, t=44, b=0),
            paper_bgcolor=MAP_BG,
            title=dict(text=title, x=0.012, y=0.975, font=dict(color=MAP_TEXT, size=16)),
            showlegend=False,
            hoverlabel=dict(font_size=13),
        )
        event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key="world_map")
        clicked = [p.get("location") for p in (event.selection.points if event else []) if p.get("location") in by_market]
        if clicked and clicked[0] != st.session_state.get("world_last_click"):
            st.session_state["world_last_click"] = clicked[0]
            st.session_state["world_market"] = clicked[0]
            st.rerun()
        if mode == "stress":
            st.markdown(" ".join(state_chip(s, lang) for s in [*STATES, None]), unsafe_allow_html=True)
        st.caption(t("world.data_note", lang))
        if w_errors:
            st.warning(t("world.errors", lang, markets=", ".join(w_errors.values())))

        # ---- one market
        c1, c2 = st.columns([1.15, 1])
        with c1:
            sel = st.selectbox(
                t("world.click_hint", lang),
                ids,
                index=ids.index(selected) if selected in ids else 0,
                format_func=lambda i: f"{names[i]} ({by_market[i].ticker})",
            )
            st.session_state["world_market"] = sel
            mk, row = by_market[sel], snap.loc[sel]
            since = f" · {t('world.since', lang, date=fmt_date(row['since'], lang))}" if row["since"] is not None else ""
            st.markdown(f"{state_chip(row['state'], lang)}{since}", unsafe_allow_html=True)
            st.caption(t("world.proxy", lang, ticker=mk.ticker, tracks=mk.tracks, benchmark=mk.benchmark))
            k = st.columns(4)
            k[0].metric(t("world.close", lang), "–" if row["close"] != row["close"] else f"{row['close']:,.2f}".replace(",", " "))
            k[1].metric(t("world.return", lang, horizon=horizon), fmt_ret(row["return"], lang))
            k[2].metric(t("world.vol", lang), "–" if row["vol"] != row["vol"] else fmt_pct(row["vol"], lang))
            k[3].metric(t("world.drawdown", lang), fmt_ret(row["drawdown"], lang))
            if row["vol_pct"] == row["vol_pct"]:
                st.caption(f"{t('world.vol_pct', lang)} : {fmt_pct(row['vol_pct'], lang)}")
            price = w_prices[sel].loc[day - pd.DateOffset(years=3) : day].dropna()
            path = w_ind["state"][sel].reindex(price.index)
            fig = go.Figure()
            block = (path != path.shift()).cumsum()
            for _, seg in path.groupby(block):
                if seg.iloc[0] in (1, 2):
                    fig.add_vrect(
                        x0=seg.index[0],
                        x1=seg.index[-1] + pd.Timedelta(days=1),
                        fillcolor=STATE_COLORS[STATES[int(seg.iloc[0])]],
                        opacity=0.25,
                        line_width=0,
                        layer="below",
                    )
            fig.add_scatter(
                x=price.index,
                y=price.values,
                mode="lines",
                line=dict(color=TEXT, width=1.8),
                hovertemplate="%{x|%d/%m/%Y}: %{y:.2f}<extra></extra>",
            )
            fig.update_xaxes(type="date")
            fig.update_layout(title=dict(text=t("world.price_chart", lang, name=names[sel], ticker=mk.ticker), font_size=14))
            st.plotly_chart(base_layout(fig, 330, showlegend=False, hovermode="x unified"), width="stretch")
            if sel == "USA":
                st.caption(t("world.us_note", lang))
        with c2:
            b = breadth(w_ind["state"]).loc[:day]
            fig = go.Figure()
            for s in ["stress", "elevated"]:
                fig.add_scatter(
                    x=b.index,
                    y=b[s],
                    stackgroup="one",
                    name=t(f"world.state.{s}", lang),
                    line=dict(width=0.5, color=STATE_COLORS[s]),
                    hovertemplate=f"{t(f'world.state.{s}', lang)}: %{{y:.0%}}<extra></extra>",
                )
            us = probs["stress"].loc[:day]
            fig.add_scatter(
                x=us.index,
                y=us.values,
                name=t("world.us_stress_prob", lang),
                line=dict(color=TEXT, width=1.2),
                hovertemplate=f"{t('world.us_stress_prob', lang)}: %{{y:.0%}}<extra></extra>",
            )
            fig.update_yaxes(range=[0, 1], tickformat=".0%")
            fig.update_xaxes(type="date", range=[day - pd.DateOffset(years=5), day])
            fig.update_layout(title=dict(text=t("world.breadth", lang), font_size=14))
            st.plotly_chart(base_layout(fig, 420, hovermode="x unified"), width="stretch")
            st.caption(t("world.breadth_help", lang))

        # ---- every market
        st.subheader(t("world.table", lang))
        order = snap.assign(_s=snap["state"].map({"stress": 0, "elevated": 1, "calm": 2}).fillna(3)).sort_values(["_s", "return"])
        table = pd.DataFrame(
            {
                t("world.col.market", lang): [names[i] for i in order.index],
                t("world.col.ticker", lang): order["ticker"],
                t("world.state", lang): order["state"].map(lambda s: t(f"world.state.{s or 'none'}", lang)),
                t("world.return", lang, horizon=horizon): order["return"] * 100,
                t("world.vol", lang): order["vol"] * 100,
                t("world.vol_pct", lang): order["vol_pct"] * 100,
                t("world.drawdown", lang): order["drawdown"] * 100,
                t("world.col.since", lang): order["since"].map(lambda d: fmt_date(d, lang) if d else "–"),
            }
        )
        pct = st.column_config.NumberColumn(format="%.1f %%")
        st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            height=36 * (len(table) + 1) + 3,
            column_config={col: pct for col in table.columns[3:7]},
        )
        st.download_button(
            t("world.download", lang),
            order.drop(columns="_s").to_csv(),
            f"world-{day.date()}-{horizon}.csv",
            "text/csv",
        )
        with st.expander(t("world.method", lang)):
            st.markdown(
                t(
                    "world.method_text",
                    lang,
                    stress_pct=round((1 - w_cfg["stress"]["vol_percentile"]) * 100),
                    elevated_pct=round((1 - w_cfg["elevated"]["vol_percentile"]) * 100),
                    dd=fmt_pct(w_cfg["stress"]["drawdown"], lang),
                    days=w_cfg["confirm_days"],
                )
            )

# ================================================================ HISTORY
with tab_hist:
    result = evaluate(
        probs,
        pipeline.prices["equity"],
        pipeline.episodes,
        pipeline.settings,
        truth=pipeline.truth,
        rule=pipeline.labels,
        score=pipeline.alarm_score(model),
    )
    targets = settings["validation"]["targets"]
    st.subheader(t("hist.metrics", lang))
    st.caption(t("hist.targets", lang, latency=targets["max_median_latency_days"], fp=targets["max_false_positives_per_year"]))
    m = st.columns(5)
    lat = result["median_latency"]
    m[0].metric(
        t("hist.median_latency", lang),
        t("hist.latency_unit", lang, value=f"{lat:.0f}") if lat == lat else "–",
        t("hist.target_met", lang) if result["meets_latency_target"] else t("hist.target_missed", lang),
        delta_color="normal" if result["meets_latency_target"] else "inverse",
    )
    m[1].metric(
        t("hist.false_positives", lang),
        fmt_num(result["false_positives_per_year"], lang).lstrip("+"),
        t("hist.target_met", lang) if result["meets_fp_target"] else t("hist.target_missed", lang),
        delta_color="normal" if result["meets_fp_target"] else "inverse",
    )
    m[2].metric(t("hist.detected", lang), f"{result['detected']} / {result['n_episodes']}")
    m[3].metric(t("hist.ece", lang), fmt_num(result["ece"], lang, 3).lstrip("+"))
    if "accuracy_truth" in result:
        m[4].metric(t("hist.accuracy_truth", lang), fmt_pct(result["accuracy_truth"], lang))
    else:
        m[4].metric(t("hist.switches", lang), f"{result['switches_per_year']:.1f}")

    st.subheader(t("hist.regime_probabilities", lang))
    fig = go.Figure()
    for r in regimes:
        fig.add_scatter(
            x=probs.index,
            y=probs[r],
            stackgroup="one",
            name=reg(r),
            line=dict(width=0.5, color=colors[r]),
            hovertemplate=f"{reg(r)}: %{{y:.0%}}<extra></extra>",
        )
    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    st.plotly_chart(base_layout(fig, 320, hovermode="x unified"), width="stretch")

    c1, c2 = st.columns([1.4, 1])
    with c1:
        st.subheader(t("hist.episodes", lang))
        ep = settings["validation"]["episodes"]
        st.caption(t("hist.episode_rule", lang, dd=fmt_pct(ep["drawdown_threshold"], lang), q=int(ep["vol_quantile"] * 100)))
        table = result["episodes"].copy()
        if len(table):
            table = pd.DataFrame(
                {
                    t("hist.col.start", lang): table["start"].map(lambda d: fmt_date(d, lang)),
                    t("hist.col.end", lang): table["end"].map(lambda d: fmt_date(d, lang)),
                    t("hist.col.trigger", lang): table["trigger"].map(lambda x: t(f"hist.trigger.{x}", lang)),
                    t("hist.col.drawdown", lang): table["max_drawdown"].map(lambda v: fmt_pct(v, lang, 1)),
                    t("hist.col.latency", lang): table["latency_days"].map(
                        lambda v: t("hist.not_detected", lang) if pd.isna(v) else f"{v:+.0f}"
                    ),
                }
            )
            st.dataframe(table, hide_index=True, width="stretch")
        st.caption(t("hist.latency_help", lang))
    with c2:
        st.subheader(t("hist.calibration", lang))
        # As known on the chosen date: out-of-sample days whose outcome was already known.
        cal = calibration_report(probs["stress"], pipeline.episodes, pipeline.settings, until=as_of)
        curves = [(t("hist.cal.calibrated", lang), cal, colors["stress"])]
        score = pipeline.alarm_score(model)
        raw = None
        if not score.equals(probs["stress"]):
            raw = calibration_report(score, pipeline.episodes, pipeline.settings, until=as_of)
            curves.append((t("hist.cal.raw", lang), raw, MUTED))
        fig = go.Figure()
        fig.add_scatter(
            x=[0, 1], y=[0, 1], mode="lines", line=dict(color=MUTED, dash="dot", width=1), showlegend=False, hoverinfo="skip"
        )
        for name, report, color in curves:
            rel = report["reliability"]
            fig.add_scatter(
                x=rel["predicted"],
                y=rel["observed"],
                mode="lines+markers",
                name=name,
                marker=dict(size=6 + 18 * (rel["count"] / max(rel["count"].max(), 1)) ** 0.5, color=color),
                line=dict(color=color, width=2, dash="solid" if color != MUTED else "dash"),
                customdata=rel["count"],
                hovertemplate=f"{name}<br>%{{x:.0%}} → %{{y:.0%}} (n=%{{customdata}})<extra></extra>",
            )
        fig.update_xaxes(title=t("hist.predicted", lang), range=[0, 1], tickformat=".0%")
        fig.update_yaxes(title=t("hist.observed", lang), range=[0, 1], tickformat=".0%")
        fig = base_layout(fig, 360)
        fig.update_layout(legend=dict(orientation="h", y=-0.32))
        st.plotly_chart(fig, width="stretch")
        if raw is not None and cal["n_days"]:
            st.caption(
                t(
                    "hist.cal.scores",
                    lang,
                    brier=fmt_num(cal["brier"], lang, 3).lstrip("+"),
                    brier_raw=fmt_num(raw["brier"], lang, 3).lstrip("+"),
                    ece=fmt_num(cal["ece"], lang, 3).lstrip("+"),
                    ece_raw=fmt_num(raw["ece"], lang, 3).lstrip("+"),
                    days=cal["n_days"],
                )
            )
        st.caption(t("hist.calibration_help", lang, h=settings["validation"]["calibration"]["target_horizon_days"]))

    st.subheader(t("hist.compare", lang))
    rows = []
    for m_name in available_models():
        r = evaluate(
            get_probs(provider, m_name),
            pipeline.prices["equity"],
            pipeline.episodes,
            pipeline.settings,
            truth=pipeline.truth,
            rule=pipeline.labels,
            score=pipeline.alarm_score(m_name),
        )
        rows.append(
            {
                t("app.model", lang): t(f"model.{m_name}", lang),
                t("hist.median_latency", lang): r["median_latency"],
                t("hist.false_positives", lang): round(r["false_positives_per_year"], 2),
                t("hist.detected", lang): f"{r['detected']} / {r['n_episodes']}",
                t("hist.brier", lang): round(r["brier"], 3),
                t("hist.ece", lang): round(r["ece"], 3),
                t("hist.switches", lang): round(r["switches_per_year"], 1),
                **({t("hist.accuracy_truth", lang): fmt_pct(r["accuracy_truth"], lang)} if "accuracy_truth" in r else {}),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.subheader(t("hist.track_record", lang))
    index_path = resolve(settings["publish"]["dir"]) / "index.csv"
    if index_path.exists():
        st.dataframe(pd.read_csv(index_path).iloc[::-1], hide_index=True, width="stretch")
    else:
        st.info(t("hist.no_track_record", lang))

# ================================================================ TRACK RECORD
with tab_track:
    records = resolve(settings["publish"]["dir"])
    files = tuple(sorted((p.name, p.stat().st_mtime_ns) for p in records.rglob("*.json*")))
    with st.spinner(t("app.loading", lang)):
        page = get_track_record_page(provider, lang, files)
    st.caption(t("tr.app_help", lang, url=settings["publish"].get("pages_url", "")))
    st.download_button(f"{t('app.download', lang)} HTML", page, f"track-record-{lang}.html", "text/html")
    components.html(page, height=2600, scrolling=True)

# ================================================================ ALERTS
with tab_alerts:
    alerts = pipeline.alerts(model)
    alerts = alerts[alerts["date"] <= as_of]
    st.subheader(t("alerts.rules", lang))
    a = settings["alerts"]
    st.markdown(
        "\n".join(
            [
                f"- {t('alerts.rule.regime_change', lang, days=settings['validation']['confirm_days'])}",
                f"- {t('alerts.rule.stress_probability', lang, value=fmt_pct(threshold, lang))}",
                f"- {t('alerts.rule.early_warning', lang, value=fmt_pct(a['early_warning_probability'], lang))}",
                f"- {t('alerts.rule.score_jump', lang, value=fmt_num(a['score_jump'], lang).lstrip('+'))}",
            ]
        )
    )
    st.caption(t("alerts.channels", lang))

    st.subheader(t("alerts.title", lang))
    types = ["regime_change", "stress_probability", "early_warning", "score_jump"]
    c1, c2 = st.columns([2, 1])
    chosen = c1.multiselect(t("alerts.filter", lang), types, default=types, format_func=lambda x: t(f"alert.type.{x}", lang))
    years = c2.slider(t("alerts.period", lang), 1, 25, 3, format="%d " + ("ans" if lang == "fr" else "years"))
    view = alerts[alerts["type"].isin(chosen) & (alerts["date"] >= as_of - pd.DateOffset(years=years))]

    def message(row) -> str:
        if row["type"] == "regime_change":
            return t("alert.msg.regime_change", lang, old=reg(row["old"]), new=reg(row["new"]))
        if row["type"] == "score_jump":
            return t(
                "alert.msg.score_jump", lang, dimension=t(f"dimension.{row['old']}", lang), value=fmt_num(row["value"], lang)
            )
        return t(f"alert.msg.{row['type']}", lang, value=fmt_pct(row["value"], lang))

    if view.empty:
        st.info(t("alerts.none", lang))
    else:
        st.dataframe(
            pd.DataFrame(
                {
                    t("alerts.date", lang): view["date"].map(lambda d: fmt_date(d, lang)),
                    t("alerts.type", lang): view["type"].map(lambda x: t(f"alert.type.{x}", lang)),
                    t("alerts.severity", lang): view["severity"].map(lambda x: t(f"alert.severity.{x}", lang)),
                    t("alerts.message", lang): view.apply(message, axis=1),
                }
            ),
            hide_index=True,
            width="stretch",
        )

# ================================================================ SCENARIOS & COMMITTEE
with tab_scen:
    assets, scenarios = load_library(settings)
    funds = load_funds(settings)
    c1, c2 = st.columns([1, 1])
    with c1:
        fund_id = st.selectbox(
            t("app.fund", lang),
            [f.id for f in funds],
            index=1,
            format_func=lambda i: next(f.name[lang] for f in funds if f.id == i),
        )
        base = next(f for f in funds if f.id == fund_id)
        with st.expander(t("app.edit_weights", lang)):
            edited = st.data_editor(
                pd.DataFrame(
                    {"asset": [t(f"asset.{a}", lang) for a in assets], "weight": [base.weights.get(a, 0.0) * 100 for a in assets]}
                ),
                hide_index=True,
                disabled=["asset"],
                width="stretch",
                key=f"weights-{fund_id}",
                column_config={
                    "asset": st.column_config.TextColumn(t("scen.by_asset", lang)),
                    "weight": st.column_config.NumberColumn("%", min_value=0.0, max_value=100.0, step=1.0),
                },
            )
            total = edited["weight"].sum()
            st.caption(t("app.weights_sum", lang, value=f"{total:.0f} %"))
        weights = {a: w / 100 for a, w in zip(assets, edited["weight"], strict=True)}
        fund = Fund(id=f"{fund_id}", name=base.name, weights=weights)
    with c2:
        top_k = st.slider(t("scen.selected", lang), 1, len(scenarios), settings["scenarios"]["top_k"])

    st.subheader(t("scen.title", lang))
    st.caption(t("scen.help", lang))
    ranking = rank_scenarios(scenarios, pd.Series(state.scores), pd.Series(state.probabilities))
    impacts = impact_table(fund, scenarios, list(ranking["id"])).set_index("id")
    by_id = {s.id: s for s in scenarios}
    ranking["name"] = ranking["id"].map(lambda i: by_id[i].name[lang])
    st.dataframe(
        pd.DataFrame(
            {
                t("scen.col.scenario", lang): ranking["name"],
                t("scen.col.period", lang): ranking["id"].map(
                    lambda i: f"{fmt_date(by_id[i].start, lang)} – {fmt_date(by_id[i].end, lang)}"
                ),
                t("scen.col.regime", lang): ranking["regime"].map(reg),
                t("scen.col.relevance", lang): ranking["relevance"] * 100,
                t("scen.col.impact", lang): ranking["id"].map(lambda i: fmt_pct(impacts.loc[i, "total"], lang, 1)),
            }
        ),
        hide_index=True,
        width="stretch",
        column_config={
            t("scen.col.relevance", lang): st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f %%")
        },
    )

    st.subheader(t("scen.impact_title", lang))
    chosen_ids = list(ranking["id"].head(top_k))
    sel = impacts.loc[chosen_ids]
    fig = go.Figure(
        go.Bar(
            x=[by_id[i].name[lang] for i in chosen_ids],
            y=sel["total"],
            marker_color=[colors[by_id[i].regime] for i in chosen_ids],
            text=[fmt_pct(v, lang, 1) for v in sel["total"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}: %{y:.1%}<extra></extra>",
        )
    )
    fig.update_yaxes(tickformat=".0%")
    fig.add_hline(y=0, line_color=MUTED, line_width=1)
    st.plotly_chart(base_layout(fig, 320, showlegend=False), width="stretch")
    with st.expander(t("scen.by_asset", lang)):
        contrib = sel[assets].T
        contrib.index = [t(f"asset.{a}", lang) for a in assets]
        contrib.columns = [by_id[i].name[lang] for i in chosen_ids]
        st.dataframe(contrib.map(lambda v: fmt_pct(v, lang, 2)), width="stretch")
    st.caption(t("scen.indicative", lang))

    st.subheader(t("scen.note", lang))
    st.caption(t("scen.note_help", lang))
    note = build_note(pipeline, lang, model, fund=fund, date=as_of, top_k=top_k)
    markdown = to_markdown(note)
    stamp = state.date.date().isoformat()
    d1, d2, d3 = st.columns(3)
    d1.download_button(
        f"{t('app.download', lang)} PDF", to_pdf(note), f"note-{stamp}-{lang}.pdf", "application/pdf", width="stretch"
    )
    d2.download_button(
        f"{t('app.download', lang)} HTML", to_html(note), f"note-{stamp}-{lang}.html", "text/html", width="stretch"
    )
    d3.download_button(
        f"{t('app.download', lang)} Markdown", markdown, f"note-{stamp}-{lang}.md", "text/markdown", width="stretch"
    )
    with st.container(border=True):
        st.markdown(markdown)
