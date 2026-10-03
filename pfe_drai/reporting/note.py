"""Risk committee note, in French or English, as Markdown, HTML or PDF."""

import html

import pandas as pd

from ..explain import explain, note_lines
from ..i18n import fmt_date, fmt_num, fmt_pct, t
from ..scenarios import Fund, impact_table, load_funds, load_library, rank_scenarios


def build_note(
    pipeline, lang: str = "fr", model: str | None = None, fund: Fund | None = None, date=None, top_k: int | None = None
) -> dict:
    """Collect everything the note shows, as plain data (easy to test and to render)."""
    settings = pipeline.settings
    state = pipeline.state(model, date)
    top_k = top_k or settings["scenarios"]["top_k"]
    assets, scenarios = load_library(settings)
    fund = fund or load_funds(settings)[1]
    ranking = rank_scenarios(scenarios, pd.Series(state.scores), pd.Series(state.probabilities)).head(top_k)
    impacts = impact_table(fund, scenarios, list(ranking["id"]))
    by_id = {s.id: s for s in scenarios}
    metrics = pipeline.evaluate(state.model)
    reg = lambda r: t(f"regime.{r}", lang)  # noqa: E731

    dims = [
        {
            "name": t(f"dimension.{d}", lang),
            "score": fmt_num(state.scores[d], lang),
            "change": fmt_num(state.scores[d] - state.previous["scores"][d], lang),
        }
        for d in ("stress", "growth", "inflation")
    ]
    drivers = sorted(state.drivers.items(), key=lambda kv: -abs(kv[1]))[:5]
    changes = []
    if state.previous["regime"] != state.regime:
        changes.append(t("dash.regime_changed", lang, old=reg(state.previous["regime"]), new=reg(state.regime)))
    else:
        changes.append(t("dash.regime_same", lang, regime=reg(state.regime)))
    for r, p in state.probabilities.items():
        old = state.previous["probabilities"][r]
        if abs(p - old) >= 0.05:
            changes.append(t("dash.prob_move", lang, regime=reg(r), old=fmt_pct(old, lang), new=fmt_pct(p, lang)))

    scen_rows = []
    for _, row in ranking.iterrows():
        sc = by_id[row["id"]]
        total = float(impacts.set_index("id").loc[row["id"], "total"])
        scen_rows.append(
            {
                "name": sc.name[lang] if lang in sc.name else sc.name["fr"],
                "period": f"{fmt_date(sc.start, lang)} – {fmt_date(sc.end, lang)}",
                "regime": reg(sc.regime),
                "relevance": fmt_pct(row["relevance"], lang),
                "impact": fmt_pct(total, lang, 1),
                "why": t(
                    "scen.why",
                    lang,
                    distance=fmt_num(row["distance"], lang).lstrip("+"),
                    regime=reg(sc.regime),
                    prob=fmt_pct(row["regime_probability"], lang),
                ),
            }
        )
    latency = metrics["median_latency"]
    naming = ""
    if state.states:
        agreement = [s["purity"] for s in state.states]
        naming = " " + t(
            "note.naming", lang, low=fmt_pct(min(agreement), lang), high=fmt_pct(max(agreement), lang), n=len(agreement)
        )
    calibration = ""
    fit = state.calibration.get("calibrator") or {}
    if fit.get("calibrated") and state.calibration["n_days"]:
        calibration = " " + t(
            "note.calibration",
            lang,
            days=state.calibration["n_days"],
            brier=fmt_num(state.calibration["brier"], lang, 3).lstrip("+"),
            ece=fmt_num(state.calibration["ece"], lang, 3).lstrip("+"),
        )
    return {
        "lang": lang,
        "title": t("note.title", lang),
        "as_of": t("note.as_of", lang, date=fmt_date(state.date, lang)),
        "fund": t("note.portfolio" if fund.id == "own" else "note.fund", lang, fund=fund.name.get(lang, fund.id)),
        "summary": t(
            "note.summary",
            lang,
            model=t(f"model.{state.model}", lang),
            regime=reg(state.regime),
            prob=fmt_pct(state.probabilities[state.regime], lang),
        ),
        "regime_desc": t(f"regime.{state.regime}.desc", lang),
        "early": t("note.early", lang, prob=fmt_pct(state.early_warning["stress"], lang)) if state.early_warning else "",
        "alarm": t(
            "note.alarm_on" if state.alarm["on"] else "note.alarm_off",
            lang,
            date=fmt_date(pd.Timestamp(state.alarm["since"]), lang) if state.alarm["on"] else "",
            score=fmt_pct(state.alarm["score"], lang),
            threshold=fmt_pct(state.alarm["threshold"], lang),
        ),
        "dimensions": dims,
        "drivers": [{"name": t(f"feature.{k}", lang), "value": fmt_num(v, lang)} for k, v in drivers],
        # 4 to 6 template sentences on what drives the reading (pfe_drai/explain.py, docs/EXPLAIN.md).
        "why": note_lines(explain(pipeline, state.model, state.date), lang),
        "changes": changes,
        "scenarios": scen_rows,
        "impact_assets": [{"name": t(f"asset.{a}", lang), "weight": fmt_pct(fund.weights.get(a, 0.0), lang)} for a in assets],
        "method": t(
            "note.method",
            lang,
            refit=settings["validation"]["refit_every_days"],
            latency=t("hist.latency_unit", lang, value=f"{latency:.0f}") if latency == latency else "n/a",
            fp=fmt_num(metrics["false_positives_per_year"], lang).lstrip("+"),
            detected=metrics["detected"],
            episodes=metrics["n_episodes"],
        )
        + naming
        + calibration,
        "limits": t("note.limits", lang),
        "disclaimer": t("note.disclaimer", lang),
        "ai": t("note.ai", lang),
        "synthetic": "" if state.is_live_data else t("note.synthetic", lang),
        "sources": t("note.sources", lang, provider=state.data_provider, model=t(f"model.{state.model}", lang)),
    }


def to_markdown(note: dict) -> str:
    lang = note["lang"]
    lines = [f"# {note['title']}", "", f"**{note['as_of']}** · {note['fund']}", ""]
    if note["synthetic"]:
        lines += [f"> ⚠ {note['synthetic']}", ""]
    lines += [f"## {t('note.s1', lang)}", "", note["summary"], "", f"**{note['alarm']}**", "", note["regime_desc"], ""]
    if note["early"]:
        lines += [note["early"], ""]
    lines += [
        f"## {t('note.s2', lang)}",
        "",
        f"| {t('note.col.dimension', lang)} | {t('note.col.score', lang)} | {t('note.col.change', lang)} |",
        "|---|---:|---:|",
    ]
    lines += [f"| {d['name']} | {d['score']} | {d['change']} |" for d in note["dimensions"]]
    lines += ["", f"{t('note.top_drivers', lang)} :" if lang == "fr" else f"{t('note.top_drivers', lang)}:", ""]
    lines += [f"- {d['name']} : {d['value']}" if lang == "fr" else f"- {d['name']}: {d['value']}" for d in note["drivers"]]
    lines += ["", f"### {t('note.why', lang)}", ""] + [f"- {line}" for line in note["why"]]
    lines += ["", f"## {t('note.s3', lang)}", ""] + [f"- {c}" for c in note["changes"]]
    lines += [
        "",
        f"## {t('note.s4', lang)}",
        "",
        "| " + " | ".join(t(f"scen.col.{c}", lang) for c in ("scenario", "period", "regime", "relevance")) + " |",
        "|---|---|---|---:|",
    ]
    lines += [f"| {s['name']} | {s['period']} | {s['regime']} | {s['relevance']} |" for s in note["scenarios"]]
    lines += [""] + [
        f"- **{s['name']}** : {s['why']}" if lang == "fr" else f"- **{s['name']}**: {s['why']}" for s in note["scenarios"]
    ]
    lines += [
        "",
        f"## {t('note.s5', lang)}",
        "",
        f"| {t('scen.col.scenario', lang)} | {t('scen.col.impact', lang)} |",
        "|---|---:|",
    ]
    lines += [f"| {s['name']} | {s['impact']} |" for s in note["scenarios"]]
    lines += ["", f"_{t('scen.indicative', lang)}_", ""]
    lines += [
        f"## {t('note.s6', lang)}",
        "",
        note["method"],
        "",
        note["limits"],
        "",
        f"## {t('note.s7', lang)}",
        "",
        note["disclaimer"],
        "",
        note["ai"],
        "",
        note["sources"],
        "",
    ]
    return "\n".join(lines)


def to_html(note: dict) -> str:
    """Standalone HTML page (printable to PDF from any browser)."""
    lang = note["lang"]
    e = html.escape

    def table(headers, rows):
        head = "".join(f"<th>{e(h)}</th>" for h in headers)
        body = "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>" for r in rows)
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    parts = [f"<h1>{e(note['title'])}</h1>", f"<p class='meta'>{e(note['as_of'])} · {e(note['fund'])}</p>"]
    if note["synthetic"]:
        parts.append(f"<p class='warn'>{e(note['synthetic'])}</p>")
    parts += [
        f"<h2>{e(t('note.s1', lang))}</h2>",
        f"<p><strong>{e(note['summary'])}</strong></p>",
        f"<p><strong>{e(note['alarm'])}</strong></p>",
        f"<p>{e(note['regime_desc'])}</p>",
    ]
    if note["early"]:
        parts.append(f"<p>{e(note['early'])}</p>")
    parts += [
        f"<h2>{e(t('note.s2', lang))}</h2>",
        table(
            [t("note.col.dimension", lang), t("note.col.score", lang), t("note.col.change", lang)],
            [(d["name"], d["score"], d["change"]) for d in note["dimensions"]],
        ),
        f"<p>{e(t('note.top_drivers', lang))}</p>",
        table([t("note.col.indicator", lang), t("note.col.score", lang)], [(d["name"], d["value"]) for d in note["drivers"]]),
        f"<h3>{e(t('note.why', lang))}</h3>",
        "<ul>" + "".join(f"<li>{e(line)}</li>" for line in note["why"]) + "</ul>",
        f"<h2>{e(t('note.s3', lang))}</h2>",
        "<ul>" + "".join(f"<li>{e(c)}</li>" for c in note["changes"]) + "</ul>",
        f"<h2>{e(t('note.s4', lang))}</h2>",
        table(
            [t("scen.col.scenario", lang), t("scen.col.period", lang), t("scen.col.regime", lang), t("scen.col.relevance", lang)],
            [(s["name"], s["period"], s["regime"], s["relevance"]) for s in note["scenarios"]],
        ),
        "<ul>" + "".join(f"<li><strong>{e(s['name'])}</strong> : {e(s['why'])}</li>" for s in note["scenarios"]) + "</ul>",
        f"<h2>{e(t('note.s5', lang))}</h2>",
        table([t("scen.col.scenario", lang), t("scen.col.impact", lang)], [(s["name"], s["impact"]) for s in note["scenarios"]]),
        f"<p class='small'>{e(t('scen.indicative', lang))}</p>",
        f"<h2>{e(t('note.s6', lang))}</h2>",
        f"<p>{e(note['method'])}</p>",
        f"<p>{e(note['limits'])}</p>",
        f"<h2>{e(t('note.s7', lang))}</h2>",
        f"<p class='small'>{e(note['disclaimer'])}</p>",
        f"<p class='small'>{e(note['ai'])}</p>",
        f"<p class='small'>{e(note['sources'])}</p>",
    ]
    style = """body{font-family:Georgia,serif;max-width:820px;margin:40px auto;padding:0 16px;color:#0b0b0b;background:#fcfcfb}
h1{font-size:26px;margin-bottom:4px}h2{font-size:18px;margin-top:28px;border-bottom:1px solid #e0dfdb;padding-bottom:4px}
.meta{color:#52514e}.warn{background:#fff4e0;border-left:4px solid #eda100;padding:8px 12px}
table{border-collapse:collapse;width:100%;margin:8px 0;font-family:Arial,sans-serif;font-size:14px}
th,td{border-bottom:1px solid #e0dfdb;padding:6px 8px;text-align:left}th{color:#52514e;font-weight:600}
.small{font-size:12px;color:#52514e}"""
    return (
        f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'><title>{e(note['title'])}</title>"
        f"<style>{style}</style></head><body>{''.join(parts)}</body></html>"
    )


def _latin1(text: str) -> str:
    return (
        text.replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("≤", "<=")
        .replace("→", "->")
        .replace("⚠", "!")
        .replace(" ", " ")
        .replace("’", "'")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def to_pdf(note: dict) -> bytes:
    """Simple PDF with fpdf2 (core fonts, so a few symbols are replaced by ASCII)."""
    from fpdf import FPDF

    lang = note["lang"]
    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    w = pdf.w - pdf.l_margin - pdf.r_margin

    def para(text, size=10, style="", gap=2):
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(w, size * 0.5, _latin1(text))
        pdf.ln(gap)

    def heading(text):
        pdf.ln(2)
        para(text, 13, "B", 1)

    def rows(pairs):
        pdf.set_font("Helvetica", "", 10)
        for left, right in pairs:
            pdf.cell(w * 0.7, 6, _latin1(left))
            pdf.cell(w * 0.3, 6, _latin1(right), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    para(note["title"], 18, "B")
    para(f"{note['as_of']} - {note['fund']}", 10)
    if note["synthetic"]:
        para(note["synthetic"], 10, "B")
    heading(t("note.s1", lang))
    para(note["summary"], 10, "B")
    para(note["alarm"], 10, "B")
    para(note["regime_desc"])
    if note["early"]:
        para(note["early"])
    heading(t("note.s2", lang))
    rows([(f"{d['name']} ({d['change']})", d["score"]) for d in note["dimensions"]])
    para(t("note.top_drivers", lang), 10, "I")
    rows([(d["name"], d["value"]) for d in note["drivers"]])
    para(t("note.why", lang), 10, "I")
    for line in note["why"]:
        para(f"- {line}")
    heading(t("note.s3", lang))
    for c in note["changes"]:
        para(f"- {c}")
    heading(t("note.s4", lang))
    for s in note["scenarios"]:
        para(f"{s['name']} ({s['period']}) - {s['regime']} - {s['relevance']}", 10, "B", 0)
        para(s["why"])
    heading(t("note.s5", lang))
    rows([(s["name"], s["impact"]) for s in note["scenarios"]])
    para(t("scen.indicative", lang), 8, "I")
    heading(t("note.s6", lang))
    para(note["method"])
    para(note["limits"])
    heading(t("note.s7", lang))
    for key in ("disclaimer", "ai", "sources"):
        para(note[key], 8)
    return bytes(pdf.output())
