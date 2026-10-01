"""PFE DRAI dashboard: python -m pfe_drai app  (or: streamlit run app/streamlit_app.py)."""

import os
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pfe_drai.config import load_settings, resolve  # noqa: E402
from pfe_drai.data import available_providers  # noqa: E402
from pfe_drai.features import FEATURES  # noqa: E402
from pfe_drai.i18n import fmt_date, fmt_num, fmt_pct, t  # noqa: E402
from pfe_drai.models import available_models  # noqa: E402
from pfe_drai.pipeline import Pipeline  # noqa: E402
from pfe_drai.reporting import build_note, to_html, to_markdown, to_pdf  # noqa: E402
from pfe_drai.scenarios import Fund, impact_table, load_funds, load_library, rank_scenarios  # noqa: E402
from pfe_drai.validation import evaluate  # noqa: E402

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

tab_dash, tab_hist, tab_alerts, tab_scen = st.tabs(
    [t("tab.dashboard", lang), t("tab.history", lang), t("tab.alerts", lang), t("tab.scenarios", lang)]
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

# ================================================================ HISTORY
with tab_hist:
    result = evaluate(
        probs, pipeline.prices["equity"], pipeline.episodes, pipeline.settings, truth=pipeline.truth, rule=pipeline.labels
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
    m[3].metric(t("hist.brier", lang), f"{result['brier_stress']:.3f}")
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
        rel = result["reliability"]
        fig = go.Figure()
        fig.add_scatter(
            x=[0, 1], y=[0, 1], mode="lines", line=dict(color=MUTED, dash="dot", width=1), showlegend=False, hoverinfo="skip"
        )
        fig.add_scatter(
            x=rel["predicted"],
            y=rel["observed"],
            mode="lines+markers",
            marker=dict(size=9, color=colors["stress"]),
            line=dict(color=colors["stress"], width=2),
            showlegend=False,
            customdata=rel["count"],
            hovertemplate="%{x:.0%} → %{y:.0%} (n=%{customdata})<extra></extra>",
        )
        fig.update_xaxes(title=t("hist.predicted", lang), range=[0, 1], tickformat=".0%")
        fig.update_yaxes(title=t("hist.observed", lang), range=[0, 1], tickformat=".0%")
        st.plotly_chart(base_layout(fig, 320), width="stretch")
        st.caption(t("hist.calibration_help", lang))

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
        )
        rows.append(
            {
                t("app.model", lang): t(f"model.{m_name}", lang),
                t("hist.median_latency", lang): r["median_latency"],
                t("hist.false_positives", lang): round(r["false_positives_per_year"], 2),
                t("hist.detected", lang): f"{r['detected']} / {r['n_episodes']}",
                t("hist.brier", lang): round(r["brier_stress"], 3),
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
