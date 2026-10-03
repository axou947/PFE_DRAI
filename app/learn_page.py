"""Learn tabs of the dashboard (docs/LEARN.md): the same concepts for beginners and for professionals.

`render(level, ctx)` draws one tab. Both tabs read the same cards, key points, live numbers and Fed odds;
only the depth of the text and of the charts changes with the level.
"""

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pfe_drai.config import load_settings
from pfe_drai.i18n import fmt_date, fmt_pct, t
from pfe_drai.learn.cards import REGIME_CARD, THEMES, leads_from, load_cards, load_episodes, load_glossary, search
from pfe_drai.learn.data import compute_all, fetch, load_indicators, series_catalog, target_range
from pfe_drai.learn.fed import OUTCOMES, outlook, taylor_history, taylor_rules
from pfe_drai.learn.history import ANALOGUE_FEATURES, analogues, numbers, regime_mix, snapshot
from pfe_drai.learn.lab import (
    bond,
    curve_recession_probability,
    debt_path,
    mortgage_payment,
    purchasing_power,
    real_change,
    stabilising_balance,
)
from pfe_drai.learn.today import checklist, in_focus, readings

SECTIONS = ["today", "concepts", "map", "history", "lab", "glossary", "quiz", "ask"]
THEME_COLORS = {"macro": "#2a78d6", "micro": "#1baf7a", "model": "#7a5cc7"}


@dataclass
class Context:
    lang: str
    theme: object
    provider: str
    state: object  # pipeline State on the sidebar date
    regimes: pd.Series  # the model's daily regimes (for the base rates by regime)
    regime_colors: dict
    style: object  # base_layout(fig, height, **kw)
    usrec: pd.Series | None = None  # NBER recession flags for the chart shading (set by render)


# ---------------------------------------------------------------- data
@st.cache_data(show_spinner=False, ttl=3600)
def learn_data(provider: str):
    settings = load_settings()
    data, live, errors = fetch(settings, provider)
    return data, compute_all(load_indicators(settings), data), live, errors


@st.cache_data(show_spinner=False, ttl=3600)
def fed_outlook(provider: str, date: str, model: str, _regimes: pd.Series):
    data, values, _, _ = learn_data(provider)
    return outlook(data, values, pd.Timestamp(date), load_settings(), _regimes)


@st.cache_data(show_spinner=False, ttl=3600)
def rule_history(provider: str):
    data, values, _, _ = learn_data(provider)
    return taylor_history(data, values, load_settings())


# ---------------------------------------------------------------- formatting
def fmt_value(value, unit: str, lang: str, signed: bool = False) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "–"
    digits = 0 if unit in ("k", "usd") else 1 if unit in ("pct", "m", "tn", "pts") else 2
    text = f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"
    if lang == "fr":
        text = text.replace(".", ",")
    suffix = {
        "pct": " %" if lang == "fr" else "%",
        "pt": " pt",
        "k": " k",
        "m": " M",
        "tn": "000 Md$" if lang == "fr" else " tn$",
        "usd": " $",
        "pts": "",
    }.get(unit, "")
    if unit == "pct" and signed:
        suffix = " pt"
    return text + suffix


def ind_name(name: str, lang: str) -> str:
    return t(f"learn.ind.{name}", lang)


def _chart(fig: go.Figure, key: str) -> None:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)


def _odds_bar(probs: dict, ctx: Context, height: int = 90) -> go.Figure:
    colors = {"cut": ctx.theme.accent, "hold": ctx.theme.muted, "hike": ctx.theme.states["stress"]}
    fig = go.Figure()
    for outcome in OUTCOMES:
        p = probs.get(outcome, 0.0)
        fig.add_bar(
            x=[p],
            y=[""],
            orientation="h",
            name=t(f"learn.fed.{outcome}", ctx.lang),
            marker_color=colors[outcome],
            text=[f"{t(f'learn.fed.{outcome}', ctx.lang)} {fmt_pct(p, ctx.lang)}" if p >= 0.12 else ""],
            textposition="inside",
            insidetextanchor="middle",
            hovertemplate=f"{t(f'learn.fed.{outcome}', ctx.lang)}: {fmt_pct(p, ctx.lang)}<extra></extra>",
        )
    ctx.style(fig, height, barmode="stack", showlegend=False)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
    fig.update_xaxes(range=[0, 1], visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _history_chart(
    values: dict, names, ctx: Context, recessions: pd.Series | None, start=None, end=None, height=300, window=None
):
    fig = go.Figure()
    palette = [ctx.theme.dims["stress"], ctx.theme.dims["growth"], ctx.theme.dims["inflation"], ctx.theme.muted]
    for i, name in enumerate(names):
        s = values.get(name)
        if s is None or s.empty:
            continue
        s = s.loc[start:end] if start is not None or end is not None else s
        fig.add_scatter(x=s.index, y=s.values, name=ind_name(name, ctx.lang), line=dict(color=palette[i % 4], width=1.8))
    if recessions is not None and not recessions.empty:
        rec = recessions.loc[start:end] if start is not None or end is not None else recessions
        for a, b in _spans(rec > 0.5):
            fig.add_vrect(x0=a, x1=b, fillcolor=ctx.theme.muted, opacity=0.15, line_width=0)
    if window:
        fig.add_vrect(
            x0=window[0], x1=window[1], fillcolor=ctx.theme.accent, opacity=0.10, line_width=1, line_color=ctx.theme.accent
        )
    return ctx.style(fig, height)


def _spans(flag: pd.Series):
    """(start, end) of each run of True."""
    out, start = [], None
    for d, v in flag.items():
        if v and start is None:
            start = d
        if not v and start is not None:
            out.append((start, d))
            start = None
    if start is not None:
        out.append((start, flag.index[-1]))
    return out


# ---------------------------------------------------------------- entry point
def render(level: str, ctx: Context) -> None:
    lang = ctx.lang
    settings = load_settings()
    data, values, live, errors = learn_data(ctx.provider)
    indicators = load_indicators(settings)
    cards = load_cards(settings)
    date = ctx.state.date
    ctx.usrec = data.get("USREC")
    st.markdown(t(f"learn.intro.{level}", lang))
    if not live:
        st.warning(t("learn.simulated", lang) + (f" ({'; '.join(errors.values())})" if errors else ""))
    elif errors:
        st.caption(t("learn.missing_series", lang, series=", ".join(sorted(errors))))
    section_key = f"learn_{level}_section"
    if st.session_state.get(section_key) not in SECTIONS:
        st.session_state[section_key] = "today"
    st.segmented_control(
        t("learn.section", lang),
        SECTIONS,
        key=section_key,
        format_func=lambda s: t(f"learn.section.{s}", lang),
        label_visibility="collapsed",
        on_change=_keep_section,
        args=(section_key,),
    )
    section = st.session_state[section_key]
    st.session_state[f"{section_key}_last"] = section
    if section == "today":
        _today(level, ctx, data, values, indicators, settings, date)
    elif section == "concepts":
        _concepts(level, ctx, values, indicators, cards, settings, date)
    elif section == "map":
        _map(level, ctx, values, indicators, cards, date)
    elif section == "history":
        _history(level, ctx, values, cards, settings, date)
    elif section == "lab":
        _lab(level, ctx, data, values, settings, date)
    elif section == "glossary":
        _glossary(level, ctx, cards, settings)
    elif section == "quiz":
        _quiz(level, ctx, cards)
    else:
        _ask(level, ctx)
    st.divider()
    # Publishers only: notes in brackets (release, route) stay in indicators.yaml.
    owners = sorted({re.sub(r"\s*\(.*\)", "", v["owner"]) for v in series_catalog(settings).values()})
    st.caption(t("learn.footer", lang, sources=", ".join(owners)))


def _keep_section(section_key: str) -> None:
    """Clicking the open section again would unselect it: stay on it instead."""
    if st.session_state.get(section_key) is None:
        st.session_state[section_key] = st.session_state.get(f"{section_key}_last", "today")


def open_card(level: str, card_id: str) -> None:
    """Callback: show a card in the Concepts section of this level's tab."""
    st.session_state[f"learn_{level}_card"] = card_id
    st.session_state[f"learn_{level}_section"] = "concepts"
    st.session_state[f"learn_{level}_theme"] = "all"
    st.session_state[f"learn_{level}_search"] = ""


# ---------------------------------------------------------------- today
def _today(level, ctx: Context, data, values, indicators, settings, date):
    lang = ctx.lang
    state = ctx.state
    st.subheader(t("learn.today.title", lang, date=fmt_date(date, lang)))
    rng = target_range(data, date)
    policy = values["policy_rate"]
    cols = st.columns(5)
    cols[0].metric(t("learn.today.regime", lang), t(f"regime.{state.regime}", lang))
    rate_text = (
        f"{rng[0]:.2f}–{rng[1]:.2f}".replace(".", "," if lang == "fr" else ".")
        if rng
        else fmt_value(float(policy.loc[:date].iloc[-1]) if not policy.loc[:date].empty else None, "pct", lang)
    )
    cols[1].metric(t("learn.today.policy_rate", lang), rate_text)
    for col, name in zip(cols[2:], ["core_pce_yoy", "unrate", "curve_10y_3m"], strict=True):
        r = readings(indicators, values, [name], date)
        if r:
            delta = r[0]["change_12m"]
            col.metric(
                ind_name(name, lang),
                fmt_value(r[0]["value"], r[0]["unit"], lang),
                None if delta is None else fmt_value(delta, "pt" if r[0]["unit"] == "pct" else r[0]["unit"], lang, signed=True),
                delta_color="off",
                help=t("learn.today.delta_help", lang, date=fmt_date(r[0]["date"], lang)),
            )

    st.markdown(f"#### {t('learn.fed.title', lang)}")
    view = fed_outlook(ctx.provider, date.date().isoformat(), state.model, ctx.regimes)
    meeting = view["next_meeting"]
    if meeting:
        key = "learn.fed.next_meeting_sep" if meeting["sep"] else "learn.fed.next_meeting"
        st.caption(t(key, lang, date=fmt_date(meeting["date"], lang), days=meeting["days"]))
    if level == "beginner":
        _fed_beginner(ctx, view)
    else:
        _fed_pro(ctx, view)
    st.caption(t("learn.fed.not_advice", lang))

    st.markdown(f"#### {t('learn.check.title', lang)}")
    items = checklist(values, date, settings, alarm_on=bool(state.alarm.get("on")) if state.alarm else None)
    icons = {"green": "🟢", "amber": "🟠", "red": "🔴", None: "⚪"}
    cols = st.columns(len(items))
    for col, item in zip(cols, items, strict=True):
        value = item["value"]
        shown = {
            "sahm": lambda v: fmt_value(v, "pt", lang),
            "curve": lambda v: fmt_value(v, "pt", lang, signed=True),
            "claims": lambda v: fmt_pct(v, lang),
            "payrolls": lambda v: fmt_value(v, "k", lang, signed=True),
            "gdp": lambda v: fmt_value(v, "pct", lang),
        }.get(item["id"], lambda v: "")
        name = t(f"learn.check.{item['id']}", lang)
        col.markdown(f"{icons[item['status']]} **{name}**")
        if value is not None:
            col.caption(shown(value))
        col.caption(t(f"learn.check.{item['id']}.{level}", lang))
    reds = sum(i["status"] == "red" for i in items)
    st.caption(t("learn.check.summary", lang, red=reds, total=sum(i["status"] is not None for i in items)))


def _fed_beginner(ctx: Context, view):
    lang = ctx.lang
    head = view["headline"]
    if not head:
        st.info(t("learn.fed.no_data", lang))
        return
    in_ten = int(round(head["probability"] * 10))
    st.markdown(t(f"learn.fed.headline.{head['outcome']}", lang, n=in_ten))
    _chart(_odds_bar(head["probabilities"], ctx), "learn_beginner_fed_odds")
    lines = []
    if "history" in view["agreement"]:
        lines.append(t("learn.fed.history_agrees" if view["agreement"]["history"] else "learn.fed.history_differs", lang))
    direction = view["taylor"].get("direction")
    if direction:
        lines.append(t(f"learn.fed.taylor_says.{direction}", lang))
    for line in lines:
        st.markdown(f"- {line}")
    with st.expander(t("learn.fed.how_beginner", lang)):
        st.markdown(t("learn.fed.how_beginner_text", lang))


def _fed_pro(ctx: Context, view):
    lang = ctx.lang
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"**1 · {t('learn.fed.lens.bills', lang)}**")
        for h in view["bills"]["horizons"]:
            st.caption(
                t(
                    "learn.fed.bill_line",
                    lang,
                    bill=h["bill"],
                    y=fmt_value(h["yield"], "pct", lang),
                    basis=fmt_value(h["basis"] * 100, "k", lang).replace(" k", " bp" if lang == "en" else " pb"),
                    days=h["basis_days"],
                    meetings=len(h["meetings"]),
                    change=f"{h['change_pct'] * 100:+.0f}",
                )
            )
            _chart(_odds_bar(h["probabilities"], ctx, 60), f"learn_pro_fed_{h['bill']}")
        if view["bills"]["horizons"]:
            path = view["bills"]["horizons"][-1]
            if path["meetings"]:
                fig = go.Figure()
                fig.add_scatter(
                    x=[pd.Timestamp(view["date"])] + [pd.Timestamp(m) for m in path["meetings"]],
                    y=[view["bills"]["effr"]] + path["path"],
                    mode="lines+markers",
                    line_shape="hv",
                    name=t("learn.fed.implied_path", lang),
                    line=dict(color=ctx.theme.accent),
                )
                ctx.style(fig, 200, title=dict(text=t("learn.fed.implied_path", lang), font=dict(size=13)))
                _chart(fig, "learn_pro_fed_path")
        st.caption(t("learn.fed.bills_caveat", lang))
    with c2:
        st.markdown(f"**2 · {t('learn.fed.lens.taylor', lang)}**")
        rule = view["taylor"]
        if rule["rules"]:
            inp = rule["inputs"]
            st.caption(
                t(
                    "learn.fed.taylor_inputs",
                    lang,
                    pi=fmt_value(inp["inflation"], "pct", lang),
                    u=fmt_value(inp["unemployment"], "pct", lang),
                    ustar=fmt_value(inp["natural_unemployment"], "pct", lang),
                    i=fmt_value(inp["policy_rate"], "pct", lang),
                )
            )
            table = pd.DataFrame(
                {
                    t("learn.fed.rule", lang): [t(f"learn.fed.rule.{k}", lang) for k in rule["rules"]],
                    t("learn.fed.prescribed", lang): [fmt_value(v, "pct", lang) for v in rule["rules"].values()],
                    t("learn.fed.gap", lang): [
                        fmt_value(v - inp["policy_rate"], "pt", lang, signed=True) for v in rule["rules"].values()
                    ],
                }
            )
            st.dataframe(table, hide_index=True, width="stretch")
            st.markdown(t(f"learn.fed.taylor_says.{rule['direction']}", lang))
        else:
            st.info(t("learn.fed.no_data", lang))
        st.caption(t("learn.fed.taylor_caveat", lang))
    with c3:
        st.markdown(f"**3 · {t('learn.fed.lens.history', lang)}**")
        hist = view["history"]
        if hist.get("probabilities"):
            st.caption(t("learn.fed.history_line", lang, k=hist["sample"], n=hist["months"], h=hist["horizon_months"]))
            _chart(_odds_bar(hist["probabilities"], ctx, 60), "learn_pro_fed_history")
            similar = pd.DataFrame(hist["similar"])
            similar = pd.DataFrame(
                {
                    t("learn.fed.month", lang): [fmt_date(d, lang)[3:] if lang == "fr" else d[:7] for d in similar["date"]],
                    t("learn.ind.core_pce_yoy", lang): [fmt_value(v, "pct", lang) for v in similar["inflation"]],
                    t("learn.ind.unemp_gap", lang): [fmt_value(v, "pt", lang, signed=True) for v in similar["unemployment_gap"]],
                    t("learn.fed.then", lang): [t(f"learn.fed.{o}", lang) for o in similar["outcome"]],
                }
            )
            st.dataframe(similar, hide_index=True, width="stretch")
            if hist.get("by_regime"):
                rows = {
                    t(f"regime.{r}", lang): {t(f"learn.fed.{o}", lang): v for o, v in counts.items()}
                    for r, counts in hist["by_regime"].items()
                }
                st.caption(t("learn.fed.by_regime", lang))
                st.dataframe(pd.DataFrame(rows).T, width="stretch")
        else:
            st.info(t("learn.fed.no_data", lang))
        st.caption(t("learn.fed.history_caveat", lang))


# ---------------------------------------------------------------- concepts
def _concepts(level, ctx: Context, values, indicators, cards, settings, date):
    lang = ctx.lang
    by_id = {c.id: c for c in cards}
    card_key, theme_key, search_key = f"learn_{level}_card", f"learn_{level}_theme", f"learn_{level}_search"
    if st.session_state.get(card_key) not in by_id:
        st.session_state[card_key] = REGIME_CARD.get(ctx.state.regime, cards[0].id)
    hot = in_focus(cards, indicators, values, date)
    c1, c2, c3 = st.columns([1.3, 1.3, 2])
    theme = c1.selectbox(
        t("learn.filter.theme", lang),
        ["all", *THEMES],
        key=theme_key,
        format_func=lambda x: t(f"learn.theme.{x}", lang),
    )
    query = c2.text_input(t("learn.filter.search", lang), key=search_key, placeholder=t("learn.filter.search_hint", lang))
    shown = [c for c in search(cards, query or "", level, lang) if theme in ("all", c.theme)]
    if not shown:
        st.info(t("learn.filter.none", lang))
        return
    if st.session_state[card_key] not in {c.id for c in shown}:
        st.session_state[card_key] = shown[0].id
    c3.selectbox(
        t("learn.filter.card", lang),
        [c.id for c in shown],
        key=card_key,
        format_func=lambda cid: f"{by_id[cid].icon} {by_id[cid].title[lang]}" + ("  🔎" if cid in hot else ""),
    )
    st.caption(t("learn.filter.hot", lang))
    card = by_id[st.session_state[card_key]]
    text = card.text(level, lang)

    st.markdown(f"### {card.icon} {card.title[lang]}")
    st.markdown(f"*{text['summary']}*")
    st.info("**" + t("learn.card.facts", lang) + "**\n\n" + "\n".join(f"- {f}" for f in card.facts[lang]))
    a, b = st.columns(2)
    with a:
        st.markdown(f"**{t('learn.card.what', lang)}**")
        st.markdown(text["what"])
        st.markdown(f"**{t('learn.card.good', lang)}**")
        st.markdown(text["good"])
    with b:
        st.markdown(f"**{t('learn.card.next', lang)}**")
        st.markdown(text["next"])
        st.markdown(f"**{t('learn.card.bad', lang)}**")
        st.markdown(text["bad"])
    if level == "pro":
        with st.expander(t("learn.card.mechanics", lang), expanded=True):
            st.markdown(text["mechanics"])
        with st.expander(t("learn.card.reading", lang)):
            st.markdown(text["reading"])

    st.markdown(f"#### {t('learn.card.today', lang)}")
    if card.theme == "model":
        _model_today(level, ctx)
    found = readings(indicators, values, card.indicators, date)
    if found:
        _readings(level, ctx, found)
        start = date - pd.DateOffset(years=5 if level == "beginner" else 40)
        _chart(_history_chart(values, card.chart, ctx, ctx.usrec, start, date, 260), f"learn_{level}_card_chart")
        st.caption(t("learn.card.chart_note", lang))
    elif card.theme != "model":
        st.info(t("learn.fed.no_data", lang))

    _links(level, ctx, cards, card)
    _card_quiz(level, ctx, card)


def _readings(level, ctx: Context, found):
    lang = ctx.lang
    if level == "beginner":
        for r in found:
            trend = t(f"learn.trend.{r['trend']}", lang) if r["trend"] else ""
            line = t(
                "learn.reading.beginner",
                lang,
                name=ind_name(r["id"], lang),
                value=fmt_value(r["value"], r["unit"], lang),
                trend=trend,
            )
            if r["ref"] is not None:
                gap = r["value"] - r["ref"]
                key = (
                    "learn.reading.above"
                    if gap > 0.05 * max(1, abs(r["ref"]))
                    else "learn.reading.below"
                    if gap < -0.05 * max(1, abs(r["ref"]))
                    else "learn.reading.near"
                )
                line += " " + t(key, lang, ref=fmt_value(r["ref"], r["unit"], lang))
            st.markdown(f"- {line}")
    else:
        table = pd.DataFrame(
            {
                t("learn.reading.indicator", lang): [ind_name(r["id"], lang) for r in found],
                t("learn.reading.value", lang): [fmt_value(r["value"], r["unit"], lang) for r in found],
                t("learn.reading.chg3m", lang): [
                    fmt_value(r["change_3m"], "pt" if r["unit"] == "pct" else r["unit"], lang, signed=True) for r in found
                ],
                t("learn.reading.chg12m", lang): [
                    fmt_value(r["change_12m"], "pt" if r["unit"] == "pct" else r["unit"], lang, signed=True) for r in found
                ],
                t("learn.reading.rank", lang): [
                    t("learn.reading.rank_value", lang, p=fmt_pct(r["percentile"], lang), since=r["since"]) for r in found
                ],
                t("learn.reading.ref", lang): [
                    fmt_value(r["ref"], r["unit"], lang) if r["ref"] is not None else "–" for r in found
                ],
                t("learn.reading.date", lang): [fmt_date(r["date"], lang) for r in found],
            }
        )
        st.dataframe(table, hide_index=True, width="stretch")


def _model_today(level, ctx: Context):
    lang = ctx.lang
    state = ctx.state
    st.markdown(
        t(
            "learn.model.regime",
            lang,
            regime=t(f"regime.{state.regime}", lang),
            p=fmt_pct(state.probabilities[state.regime], lang),
        )
    )
    cols = st.columns(3)
    for col, dim in zip(cols, ["stress", "growth", "inflation"], strict=True):
        col.metric(t(f"dimension.{dim}", lang), f"{state.scores[dim]:+.2f}".replace(".", "," if lang == "fr" else "."))
    alarm = state.alarm or {}
    if alarm:
        key = "learn.model.alarm_on" if alarm.get("on") else "learn.model.alarm_off"
        st.markdown(t(key, lang, score=fmt_pct(alarm["score"], lang), threshold=fmt_pct(alarm["threshold"], lang)))
    if level == "pro" and state.calibration:
        brier = state.calibration.get("brier")
        if brier is not None:
            st.caption(t("learn.model.calibration", lang, brier=f"{brier:.3f}"))


def _links(level, ctx: Context, cards, card):
    lang = ctx.lang
    by_id = {c.id: c for c in cards}
    causes = leads_from(cards, card.id)
    st.markdown(f"#### {t('learn.card.links', lang)}")
    a, b = st.columns(2)
    with a:
        st.caption(t("learn.card.caused_by", lang))
        for src, edge in causes:
            label = f"{src.icon} {src.title[lang]}" + (f" · {edge[lang]}" if level == "pro" else "")
            st.button(label, key=f"learn_{level}_from_{src.id}_{card.id}", on_click=open_card, args=(level, src.id))
        if not causes:
            st.caption("–")
    with b:
        st.caption(t("learn.card.leads_to", lang))
        for edge in card.leads_to:
            dst = by_id[edge["card"]]
            label = f"{dst.icon} {dst.title[lang]}" + (f" · {edge[lang]}" if level == "pro" else "")
            st.button(label, key=f"learn_{level}_to_{card.id}_{dst.id}", on_click=open_card, args=(level, dst.id))


def _ask_question(level, ctx: Context, item: dict, key: str):
    lang = ctx.lang
    choice = st.radio(item["q"], range(len(item["options"])), index=None, key=key, format_func=lambda i: str(item["options"][i]))
    if choice is not None:
        if choice == item["answer"]:
            st.success(t("learn.quiz.right", lang) + " " + item["why"])
        else:
            st.error(t("learn.quiz.wrong", lang, answer=item["options"][item["answer"]]) + " " + item["why"])
    return choice


def _card_quiz(level, ctx: Context, card):
    questions = card.quiz.get(level, [])
    if not questions:
        return
    st.markdown(f"#### {t('learn.quiz.card', ctx.lang)}")
    for i, q in enumerate(questions):
        _ask_question(level, ctx, q[ctx.lang], f"learn_{level}_cardquiz_{card.id}_{i}_{ctx.lang}")


# ---------------------------------------------------------------- map
def _dot(cards, edges, ctx: Context, level, hot, focus=None, rankdir="LR", fontsize=11) -> str:
    theme = ctx.theme
    lines = [
        "digraph G {",
        f'graph [rankdir={rankdir}, bgcolor="transparent", nodesep=0.3, ranksep=0.6, fontname="Helvetica"];',
        f'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize={fontsize}, fontcolor="{theme.text}", '
        f'color="{theme.border}", fillcolor="{theme.surface}", margin="0.15,0.08"];',
        f'edge [color="{theme.muted}", fontcolor="{theme.muted}", fontsize={fontsize - 2}, arrowsize=0.6];',
    ]
    for c in cards:
        border = THEME_COLORS[c.theme]
        width = 3 if c.id in hot or c.id == focus else 1.2
        fill = f"{border}33" if c.id in hot or c.id == focus else theme.surface
        label = f"{c.icon} {c.title[ctx.lang]}".replace('"', "'")
        lines.append(f'"{c.id}" [label="{label}", color="{border}", penwidth={width}, fillcolor="{fill}"];')
    for src, edge in edges:
        label = edge[ctx.lang].replace('"', "'") if level == "pro" else ""
        lines.append(f'"{src}" -> "{edge["card"]}" [label="{label}"];')
    lines.append("}")
    return "\n".join(lines)


def _map(level, ctx: Context, values, indicators, cards, date):
    """One concept with its causes (left) and consequences (right); the whole web in an expander."""
    lang = ctx.lang
    hot = in_focus(cards, indicators, values, date)
    by_id = {c.id: c for c in cards}
    st.caption(t(f"learn.map.help.{level}", lang))
    default = st.session_state.get(f"learn_{level}_card") or "inflation"
    ids = [c.id for c in cards]
    focus = st.selectbox(
        t("learn.map.focus", lang),
        ids,
        index=ids.index(default) if default in ids else 0,
        format_func=lambda cid: f"{by_id[cid].icon} {by_id[cid].title[lang]}",
        key=f"learn_{level}_map_pick",
    )
    causes = leads_from(cards, focus)
    edges = [(c.id, e) for c, e in causes] + [(focus, e) for e in by_id[focus].leads_to]
    shown = [by_id[x] for x in dict.fromkeys([c.id for c, _ in causes] + [focus] + [e["card"] for e in by_id[focus].leads_to])]
    st.graphviz_chart(_dot(shown, edges, ctx, level, hot, focus=focus, fontsize=13), width="content")
    legend = (
        " · ".join(f"<span style='color:{THEME_COLORS[k]}'>■</span> {t(f'learn.theme.{k}', lang)}" for k in THEMES)
        + f" · <b>{t('learn.map.hot', lang)}</b>"
    )
    st.markdown(legend, unsafe_allow_html=True)
    st.button(t("learn.map.go", lang), key=f"learn_{level}_map_go", on_click=open_card, args=(level, focus))
    with st.expander(t("learn.map.all", lang)):
        every = [(c.id, e) for c in cards for e in c.leads_to]
        st.graphviz_chart(_dot(cards, every, ctx, level, hot, rankdir="TB", fontsize=12), width="stretch")


# ---------------------------------------------------------------- history lessons
@st.cache_data(show_spinner=False, ttl=3600)
def episode_analogues(provider: str, date: str):
    _, values, _, _ = learn_data(provider)
    return analogues(values, load_episodes(load_settings()), pd.Timestamp(date))


def pick_episode(level: str, episode_id: str) -> None:
    """Callback: show an episode in the History section."""
    st.session_state[f"learn_{level}_episode"] = episode_id


def _history(level, ctx: Context, values, cards, settings, date):
    lang = ctx.lang
    episodes = sorted(load_episodes(settings), key=lambda e: e["start"])
    by_ep = {e["id"]: e for e in episodes}
    order = [e["id"] for e in episodes]
    key = f"learn_{level}_episode"
    if st.session_state.get(key) not in by_ep:
        st.session_state[key] = order[-1]

    # Every episode on one timeline of the Fed's rate and inflation.
    st.markdown(f"#### {t('learn.history.overview', lang)}")
    names = ["policy_rate", "core_pce_yoy"] if level == "beginner" else ["policy_rate", "core_pce_yoy", "unrate"]
    fig = _history_chart(values, names, ctx, ctx.usrec, None, date, 300)
    for i, ep in enumerate(episodes, start=1):
        fig.add_vrect(
            x0=ep["start"],
            x1=ep["end"],
            fillcolor=ctx.theme.accent,
            opacity=0.30 if ep["id"] == st.session_state[key] else 0.10,
            line_width=0,
            annotation_text=str(i),
            annotation_position="top left",
            annotation_font=dict(size=10, color=ctx.theme.text),
        )
    _chart(fig, f"learn_{level}_episodes_overview")
    st.caption(t("learn.history.overview_help", lang))

    # The past episodes that started in conditions most like the analysis date.
    close = episode_analogues(ctx.provider, str(pd.Timestamp(date).date()))
    st.markdown(f"#### {t('learn.history.analogue_title', lang)}")
    st.caption(t(f"learn.history.analogue_help.{level}", lang))
    if close:
        for row in close:
            label = f"{order.index(row['id']) + 1}. {by_ep[row['id']]['title'][lang]}"
            if level == "pro":
                distance = f"{row['distance']:.2f}".replace(".", "," if lang == "fr" else ".")
                label += f" ({t('learn.history.distance', lang)} {distance})"
            st.button(f"🔍 {label}", key=f"learn_{level}_analogue_{row['id']}", on_click=pick_episode, args=(level, row["id"]))
    else:
        st.caption(t("learn.history.analogue_none", lang))

    st.divider()
    pick = st.selectbox(
        t("learn.history.pick", lang),
        order,
        format_func=lambda e: f"{order.index(e) + 1}. {by_ep[e]['title'][lang]}",
        key=key,
    )
    ep = by_ep[pick]
    start, end = pd.Timestamp(ep["start"]), pd.Timestamp(ep["end"])
    span = (start - pd.DateOffset(years=3), end + pd.DateOffset(years=3))
    names = (
        ["policy_rate", "core_pce_yoy", "unrate"]
        if level == "beginner"
        else ["policy_rate", "core_pce_yoy", "unrate", "curve_10y_3m"]
    )
    fig = _history_chart(values, names, ctx, ctx.usrec, span[0], span[1], 320, window=(start, end))
    _chart(fig, f"learn_{level}_episode_plot")
    st.caption(t("learn.history.chart_note", lang))

    text = ep[level][lang]
    cols = st.columns(3)
    for col, part in zip(cols, ["happened", "fed", "lesson"], strict=True):
        col.markdown(f"**{t(f'learn.history.{part}', lang)}**")
        col.markdown(text[part])

    _episode_numbers(level, ctx, values, ep)

    if ep.get("timeline"):
        st.markdown(f"**{t('learn.history.timeline', lang)}**")
        st.markdown("\n".join(f"- **{fmt_date(e['date'], lang)}** · {e[lang]}" for e in ep["timeline"]))

    _episode_vs_today(level, ctx, values, ep, date)

    if level == "pro":
        if ep.get("debate"):
            st.markdown(f"**{t('learn.history.debate', lang)}**")
            st.markdown(ep["debate"][lang])
        st.markdown(f"**{t('learn.history.model', lang)}**")
        mix = regime_mix(ctx.regimes, start, end)
        if mix:
            ranked = sorted(mix.items(), key=lambda x: -x[1])
            st.markdown(" · ".join(f"{t(f'regime.{r}', lang)} {fmt_pct(v, lang)}" for r, v in ranked))
            st.caption(t("learn.history.model_help", lang))
        else:
            st.caption(t("learn.history.model_none", lang))
        if ep.get("reading"):
            st.markdown(f"**{t('learn.history.reading', lang)}**")
            st.markdown("\n".join(f"- {r}" for r in ep["reading"]))

    by_id = {c.id: c for c in cards}
    st.caption(t("learn.history.cards", lang))
    cols = st.columns(len(ep["cards"]))
    for col, cid in zip(cols, ep["cards"], strict=True):
        col.button(
            f"{by_id[cid].icon} {by_id[cid].title[lang]}",
            key=f"learn_{level}_ep_{pick}_{cid}",
            on_click=open_card,
            args=(level, cid),
        )


def _episode_numbers(level, ctx: Context, values, ep):
    lang = ctx.lang
    n = numbers(values, ep, ctx.usrec)
    if not n:
        return
    st.markdown(f"**{t('learn.history.numbers', lang)}**")
    items = []
    if "rate_start" in n:
        rng = t(
            "learn.history.n.rate_range",
            lang,
            low=fmt_value(n["rate_low"], "pct", lang),
            high=fmt_value(n["rate_high"], "pct", lang),
        )
        items.append(
            (
                t("learn.history.n.rate", lang),
                f"{fmt_value(n['rate_start'], 'pct', lang)} → {fmt_value(n['rate_end'], 'pct', lang)}",
                rng,
            )
        )
    for k, unit in (("inflation_high", "pct"), ("unemployment_high", "pct"), ("vix_high", "pts")):
        if k in n:
            items.append((t(f"learn.history.n.{k}", lang), fmt_value(n[k], unit, lang), None))
    if "recession_months" in n:
        items.append((t("learn.history.n.recession_months", lang), str(n["recession_months"]), None))
    if level == "pro":
        if "oil_low" in n:
            oil = f"{n['oil_low']:.0f} – {n['oil_high']:.0f} USD"  # two $ signs would render as LaTeX
            items.append((t("learn.history.n.oil", lang), oil, None))
        if "curve_low" in n:
            items.append((t("learn.history.n.curve_low", lang), fmt_value(n["curve_low"], "pt", lang, signed=True), None))
    cols = st.columns(min(len(items), 4))
    for i, (label, value, delta) in enumerate(items):
        cols[i % len(cols)].metric(label, value, delta, delta_color="off")


def _episode_vs_today(level, ctx: Context, values, ep, date):
    """The episode's starting conditions next to the analysis date's."""
    lang = ctx.lang
    then, now = snapshot(values, ep["start"]), snapshot(values, date)
    names = list(ANALOGUE_FEATURES) if level == "pro" else ["policy_rate", "core_pce_yoy", "unrate"]
    rows = []
    for name in names:
        label = t("learn.history.fed_last_year", lang) if name == "fed_last_year" else ind_name(name, lang)
        unit = "pt" if name in ("fed_last_year", "curve_10y_3m") else "pct"
        signed = unit == "pt"
        rows.append(
            {
                " ": label,
                t("learn.history.then", lang, date=fmt_date(ep["start"], lang)): fmt_value(then[name], unit, lang, signed),
                t("learn.history.now", lang, date=fmt_date(date, lang)): fmt_value(now[name], unit, lang, signed),
            }
        )
    st.markdown(f"**{t('learn.history.compare', lang)}**")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# ---------------------------------------------------------------- what-if lab
LAB_TABS = {"beginner": ("fed", "rates", "household", "debt"), "pro": ("fed", "rates", "household", "debt", "phillips")}


def _lab(level, ctx: Context, data, values, settings, date):
    lang = ctx.lang

    def last(name, default):
        s = values.get(name)
        if s is None or s.loc[:date].dropna().empty:
            return default
        return float(s.loc[:date].dropna().iloc[-1])

    st.caption(t(f"learn.lab.intro.{level}", lang))
    tabs = st.tabs([t(f"learn.lab.tab.{k}", lang) for k in LAB_TABS[level]])
    for tab, name in zip(tabs, LAB_TABS[level], strict=True):
        with tab:
            {
                "fed": _lab_fed,
                "rates": _lab_rates,
                "household": _lab_household,
                "debt": _lab_debt,
                "phillips": _lab_phillips,
            }[name](level, ctx, values, settings, date, last)


def _money(value: float, lang: str) -> str:
    return f"{value:,.0f} $".replace(",", " ") if lang == "fr" else f"${value:,.0f}"


def _lab_fed(level, ctx: Context, values, settings, date, last):
    lang = ctx.lang
    cfg = settings["learn"]["fed"]["taylor"]
    pi0, u0, ustar0, i0 = last("core_pce_yoy", 2.5), last("unrate", 4.2), last("nrou", 4.2), last("policy_rate", 3.0)
    st.markdown(f"#### {t('learn.lab.taylor', lang)}")
    st.caption(t(f"learn.lab.taylor_help.{level}", lang))
    c1, c2 = st.columns([1.2, 1])
    with c1:
        pi = st.slider(t("learn.lab.inflation", lang), -2.0, 12.0, round(pi0, 1), 0.1, key=f"learn_{level}_lab_pi")
        u = st.slider(t("learn.lab.unemployment", lang), 2.0, 15.0, round(u0, 1), 0.1, key=f"learn_{level}_lab_u")
        r_star, ustar = cfg["r_star"], ustar0
        if level == "pro":
            ustar = st.slider(t("learn.lab.natural", lang), 3.0, 7.0, round(ustar0, 1), 0.1, key=f"learn_{level}_lab_ustar")
            r_star = st.slider(t("learn.lab.r_star", lang), -1.0, 3.0, float(cfg["r_star"]), 0.25, key=f"learn_{level}_lab_rstar")
    rules = taylor_rules(
        {"inflation": pi, "unemployment": u, "natural_unemployment": ustar, "policy_rate": i0}, settings, r_star=r_star
    )
    with c2:
        shown = rules if level == "pro" else {"balanced": rules["balanced"]}
        for name, value in shown.items():
            st.metric(
                t(f"learn.fed.rule.{name}", lang),
                fmt_value(value, "pct", lang),
                fmt_value(value - i0, "pt", lang, signed=True),
                delta_color="off",
                help=t("learn.lab.vs_actual", lang, rate=fmt_value(i0, "pct", lang)),
            )
        if min(rules.values()) < 0:
            st.caption(t("learn.lab.elb", lang))
    if level == "pro":
        hist = rule_history(ctx.provider)
        if not hist.empty:
            fig = go.Figure()
            palette = [ctx.theme.dims["stress"], ctx.theme.dims["growth"], ctx.theme.dims["inflation"]]
            for k, name in enumerate([c for c in hist.columns if c != "actual"]):
                fig.add_scatter(
                    x=hist.index, y=hist[name], name=t(f"learn.fed.rule.{name}", lang), line=dict(width=1.2, color=palette[k % 3])
                )
            fig.add_scatter(
                x=hist.index, y=hist["actual"], name=t("learn.ind.policy_rate", lang), line=dict(width=2.2, color=ctx.theme.text)
            )
            ctx.style(fig, 300, title=dict(text=t("learn.lab.taylor_history", lang), font=dict(size=13)))
            _chart(fig, "learn_pro_taylor_history")


def _lab_rates(level, ctx: Context, values, settings, date, last):
    lang = ctx.lang
    # Real rate (Fisher).
    st.markdown(f"#### {t('learn.lab.fisher', lang)}")
    c1, c2, c3 = st.columns(3)
    nominal = c1.number_input(
        t("learn.lab.nominal", lang), -1.0, 20.0, round(last("us10y", 4.0), 2), 0.05, key=f"learn_{level}_lab_nom"
    )
    expected = c2.number_input(
        t("learn.lab.expected", lang), -3.0, 15.0, round(last("breakeven_10y", 2.3), 2), 0.05, key=f"learn_{level}_lab_exp"
    )
    real = real_change(nominal, expected) if level == "pro" else nominal - expected
    c3.metric(t("learn.lab.real", lang), fmt_value(real, "pct", lang))
    st.caption(t(f"learn.lab.fisher_help.{level}", lang))

    # Bond prices when rates move.
    st.markdown(f"#### {t('learn.lab.bond', lang)}")
    st.caption(t(f"learn.lab.bond_help.{level}", lang))
    c1, c2, c3 = st.columns(3)
    years = c1.select_slider(t("learn.lab.bond_years", lang), [1, 2, 5, 10, 20, 30], 10, key=f"learn_{level}_lab_byears")
    y0 = c2.number_input(
        t("learn.lab.bond_yield", lang), 0.0, 15.0, round(last("us10y", 4.0), 2), 0.05, key=f"learn_{level}_lab_byield"
    )
    shift = c3.slider(t("learn.lab.bond_shift", lang), -3.0, 3.0, 1.0, 0.25, key=f"learn_{level}_lab_bshift")
    coupon = y0
    if level == "pro":
        coupon = st.number_input(t("learn.lab.bond_coupon", lang), 0.0, 15.0, y0, 0.25, key=f"learn_{level}_lab_bcoupon")
    b = bond(y0, coupon, years, shift)
    m1, m2, m3 = st.columns(3)
    m1.metric(t("learn.lab.bond_change", lang), fmt_value(b["change_pct"], "pct", lang, signed=True).replace(" pt", " %"))
    m2.metric(t("learn.lab.bond_value", lang), _money(10_000 * (1 + b["change_pct"] / 100), lang))
    if level == "pro":
        m3.metric(
            t("learn.lab.bond_duration", lang),
            f"{b['duration']:.2f}".replace(".", "," if lang == "fr" else "."),
            t("learn.lab.bond_estimate", lang, pct=f"{b['estimate_pct']:+.2f}".replace(".", "," if lang == "fr" else ".")),
            delta_color="off",
        )

    # Recession odds from the yield curve (NY Fed model).
    st.markdown(f"#### {t('learn.lab.curve', lang)}")
    st.caption(t(f"learn.lab.curve_help.{level}", lang))
    c1, c2 = st.columns([1.2, 1])
    spread0 = last("curve_10y_3m", 1.0)
    spread = c1.slider(
        t("learn.lab.curve_spread", lang), -3.0, 4.0, float(round(spread0 * 4) / 4), 0.05, key=f"learn_{level}_lab_spread"
    )
    c2.metric(
        t("learn.lab.curve_prob", lang),
        fmt_pct(curve_recession_probability(spread), lang),
        t("learn.lab.curve_today", lang, pct=fmt_pct(curve_recession_probability(spread0), lang)),
        delta_color="off",
    )
    if level == "pro":
        s = values.get("curve_10y_3m")
        if s is not None and not s.empty:
            monthly = s.loc[:date].resample("ME").mean().dropna()
            prob = monthly.map(curve_recession_probability)
            fig = go.Figure()
            fig.add_scatter(
                x=prob.index,
                y=prob.values * 100,
                name=t("learn.lab.curve_prob", lang),
                line=dict(color=ctx.theme.states["stress"]),
            )
            usrec = ctx.usrec
            if usrec is not None and not usrec.empty:
                for a, z in _spans(usrec.loc[prob.index[0] :] > 0.5):
                    fig.add_vrect(x0=a, x1=z, fillcolor=ctx.theme.muted, opacity=0.15, line_width=0)
            ctx.style(fig, 260, yaxis_title="%")
            _chart(fig, "learn_pro_curve_history")
            st.caption(t("learn.lab.curve_chart_help", lang))


def _lab_household(level, ctx: Context, values, settings, date, last):
    lang = ctx.lang
    # Mortgage.
    st.markdown(f"#### {t('learn.lab.mortgage', lang)}")
    c1, c2, c3 = st.columns(3)
    loan = c1.number_input(t("learn.lab.loan", lang), 10_000, 5_000_000, 300_000, 10_000, key=f"learn_{level}_lab_loan")
    rate = c2.number_input(
        t("learn.lab.rate", lang), 0.0, 20.0, round(last("us10y", 4.3) + 1.8, 2), 0.05, key=f"learn_{level}_lab_rate"
    )
    pay, pay_up = mortgage_payment(loan, rate), mortgage_payment(loan, rate + 1)
    c3.metric(
        t("learn.lab.payment", lang),
        _money(pay, lang),
        t("learn.lab.payment_up", lang, pct=fmt_pct(pay_up / pay - 1, lang, 1)),
        delta_color="off",
    )
    st.caption(t("learn.lab.mortgage_help", lang))

    # Purchasing power of a dollar (CPI).
    st.markdown(f"#### {t('learn.lab.ppower', lang)}")
    cpi = _cpi_index(values)
    if cpi is not None:
        first = int(cpi.index[0].year) + 1
        now_year = pd.Timestamp(date).year
        c1, c2, c3 = st.columns(3)
        amount = c1.number_input(t("learn.lab.ppower_amount", lang), 1, 1_000_000, 100, 10, key=f"learn_{level}_lab_pp_amount")
        year = c2.slider(
            t("learn.lab.ppower_year", lang), first, now_year, max(first, now_year - 20), key=f"learn_{level}_lab_pp_year"
        )
        worth = purchasing_power(cpi, amount, f"{year}-06-30", date)
        if worth is not None:
            c3.metric(
                t("learn.lab.ppower_result", lang, year=year),
                _money(worth, lang),
                t("learn.lab.ppower_loss", lang, pct=fmt_pct(1 - amount / worth, lang)),
                delta_color="off",
            )
        st.caption(t(f"learn.lab.ppower_help.{level}", lang))

    # Real wages.
    st.markdown(f"#### {t('learn.lab.wage', lang)}")
    c1, c2, c3 = st.columns(3)
    wage = c1.number_input(
        t("learn.lab.wage_growth", lang), -10.0, 20.0, round(last("wages_yoy", 4.0), 1), 0.1, key=f"learn_{level}_lab_wage"
    )
    infl = c2.number_input(
        t("learn.lab.wage_inflation", lang), -5.0, 20.0, round(last("cpi_yoy", 3.0), 1), 0.1, key=f"learn_{level}_lab_winfl"
    )
    c3.metric(t("learn.lab.wage_real", lang), fmt_value(real_change(wage, infl), "pct", lang, signed=True).replace(" pt", " %"))
    st.caption(t(f"learn.lab.wage_help.{level}", lang))


def _cpi_index(values: dict) -> pd.Series | None:
    """The CPI level (indicator cpi_level), for prices of one year in dollars of another."""
    s = values.get("cpi_level")
    return None if s is None or s.dropna().empty else s.dropna()


def _lab_debt(level, ctx: Context, values, settings, date, last):
    lang = ctx.lang
    st.markdown(f"#### {t('learn.lab.debt', lang)}")
    st.caption(t(f"learn.lab.debt_help.{level}", lang))
    c1, c2 = st.columns([1.2, 1])
    with c1:
        d0 = st.slider(
            t("learn.lab.debt_start", lang), 20.0, 200.0, float(round(last("debt_gdp", 120.0))), 1.0, key=f"learn_{level}_lab_d0"
        )
        deficit = st.slider(t("learn.lab.debt_deficit", lang), -4.0, 8.0, 3.0, 0.25, key=f"learn_{level}_lab_pdef")
        r = st.slider(t("learn.lab.debt_rate", lang), 0.0, 8.0, 3.5, 0.25, key=f"learn_{level}_lab_r")
        g = st.slider(t("learn.lab.debt_growth", lang), 0.0, 8.0, 4.0, 0.25, key=f"learn_{level}_lab_g")
    path = debt_path(d0, deficit, r, g, 20)
    with c2:
        st.metric(
            t("learn.lab.debt_end", lang),
            fmt_value(path[-1], "pct", lang),
            fmt_value(path[-1] - d0, "pt", lang, signed=True),
            delta_color="off",
        )
        if level == "pro":
            st.metric(t("learn.lab.debt_stabilise", lang), fmt_value(stabilising_balance(d0, r, g), "pct", lang, signed=True))
    fig = go.Figure()
    years = list(range(pd.Timestamp(date).year, pd.Timestamp(date).year + len(path)))
    fig.add_scatter(x=years, y=path, name=t("learn.lab.debt_path", lang), line=dict(color=ctx.theme.accent, width=2.2))
    ctx.style(fig, 260, yaxis_title="% PIB" if lang == "fr" else "% of GDP", showlegend=False)
    _chart(fig, f"learn_{level}_debt_path")


def _lab_phillips(level, ctx: Context, values, settings, date, last):
    lang = ctx.lang
    st.markdown(f"#### {t('learn.lab.phillips', lang)}")
    gap, infl = values.get("unemp_gap"), values.get("core_pce_yoy")
    if gap is None or infl is None or gap.empty or infl.empty:
        return
    months = infl.index
    frame = pd.DataFrame({"gap": gap.reindex(months, method="ffill"), "pi": infl}).dropna()
    frame["decade"] = (frame.index.year // 10 * 10).astype(str) + "s"
    fig = go.Figure()
    for dec, part in frame.groupby("decade"):
        fig.add_scatter(x=part["gap"], y=part["pi"], mode="markers", name=dec, marker=dict(size=4, opacity=0.7))
    if not frame.loc[:date].empty:
        now = frame.loc[:date].iloc[-1]
        fig.add_scatter(
            x=[now["gap"]],
            y=[now["pi"]],
            mode="markers",
            name=t("learn.lab.now", lang),
            marker=dict(size=13, symbol="star", color=ctx.theme.states["stress"]),
        )
    ctx.style(fig, 400, xaxis_title=t("learn.ind.unemp_gap", lang), yaxis_title=t("learn.ind.core_pce_yoy", lang))
    fig.update_layout(legend=dict(y=-0.28))  # below the axis title
    _chart(fig, "learn_pro_phillips")
    st.caption(t("learn.lab.phillips_help", lang))


# ---------------------------------------------------------------- glossary
def _glossary(level, ctx: Context, cards, settings):
    lang = ctx.lang
    by_id = {c.id: c for c in cards}
    terms = sorted(load_glossary(settings), key=lambda x: x["term"][lang].lower())
    query = st.text_input(t("learn.glossary.search", lang), key=f"learn_{level}_glossary_q").strip().lower()
    if query:
        terms = [x for x in terms if query in x["term"][lang].lower() or query in x[level][lang].lower()]
    st.caption(t("learn.glossary.count", lang, n=len(terms)))
    for x in terms:
        cols = st.columns([4, 1.4])
        cols[0].markdown(f"**{x['term'][lang]}** — {x[level][lang]}")
        if x.get("card") in by_id:
            c = by_id[x["card"]]
            cols[1].button(
                f"{c.icon} {c.title[lang]}", key=f"learn_{level}_gl_{x['term']['en']}", on_click=open_card, args=(level, c.id)
            )


# ---------------------------------------------------------------- quiz
def _quiz(level, ctx: Context, cards):
    lang = ctx.lang
    st.caption(t(f"learn.quiz.help.{level}", lang))
    keys = []
    for card in cards:
        for i, q in enumerate(card.quiz.get(level, [])):
            item = q[lang]
            key = f"learn_{level}_quiz_{card.id}_{i}_{lang}"
            keys.append((key, item["answer"]))
            st.markdown(f"**{card.icon} {card.title[lang]}**")
            _ask_question(level, ctx, item, key)
    answered = [(k, a) for k, a in keys if st.session_state.get(k) is not None]
    right = sum(st.session_state.get(k) == a for k, a in answered)
    st.metric(
        t("learn.quiz.score", lang), f"{right} / {len(answered)}", t("learn.quiz.of_total", lang, n=len(keys)), delta_color="off"
    )

    def reset():
        for k, _ in keys:
            st.session_state.pop(k, None)

    st.button(t("learn.quiz.reset", lang), key=f"learn_{level}_quiz_reset", on_click=reset)


# ---------------------------------------------------------------- AI tutor (not open yet)
def _ask(level, ctx: Context):
    lang = ctx.lang
    st.markdown(f"#### {t('learn.ask.title', lang)}")
    st.caption(t(f"learn.ask.help.{level}", lang))
    st.text_area(t("learn.ask.label", lang), key=f"learn_{level}_ask_q", placeholder=t(f"learn.ask.example.{level}", lang))
    if st.button(t("learn.ask.send", lang), key=f"learn_{level}_ask_send", type="primary"):
        st.session_state[f"learn_{level}_ask_clicked"] = True
    cols = st.columns(3)
    for i, col in enumerate(cols):
        if col.button(t(f"learn.ask.sample{i + 1}.{level}", lang), key=f"learn_{level}_ask_sample_{i}"):
            st.session_state[f"learn_{level}_ask_clicked"] = True
    if st.session_state.get(f"learn_{level}_ask_clicked"):
        st.info(t("learn.ask.soon", lang), icon="🚧")
    st.caption(t("learn.ask.promise", lang))
