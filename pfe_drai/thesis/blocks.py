"""Blocks the chapters ask for by name: generated tables, figures and verbatim quotes from the docs."""

import html
import re
from dataclasses import dataclass

from ..i18n import fmt_date, fmt_pct, t
from ..publish.page import _latency_chart, _timeline
from .markup import MINUS
from .sources import Sources, ThesisError

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _num(value, digits: int, lang: str, signed: bool = False) -> str:
    if value is None:
        return "–"
    text = f"{abs(value):.{digits}f}"
    text = text.replace(".", ",") if lang == "fr" else text
    if round(value, digits) < 0:
        return MINUS + text
    return ("+" if signed and round(value, digits) > 0 else "") + text


def _pct(value, digits: int, lang: str) -> str:
    return "–" if value is None else fmt_pct(value, lang, digits)


# ---------------------------------------------------------------- tables
@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]
    numeric: list[bool]

    def md(self) -> str:
        def esc(c: str) -> str:
            return str(c).replace("|", "\\|")

        sep = ["---:" if n else "---" for n in self.numeric]
        lines = ["| " + " | ".join(esc(h) for h in self.headers) + " |", "| " + " | ".join(sep) + " |"]
        lines += ["| " + " | ".join(esc(c) for c in r) + " |" for r in self.rows]
        return "\n".join(lines)

    def html(self) -> str:
        head = "".join(
            f'<th class="{"r" if n else "l"}">{html.escape(h)}</th>' for h, n in zip(self.headers, self.numeric, strict=True)
        )
        body = "".join(
            "<tr>"
            + "".join(
                f'<td class="{"r" if n else "l"}{" nw" if _DATE.fullmatch(c) else ""}">{html.escape(c)}</td>'
                for c, n in zip(r, self.numeric, strict=True)
            )
            + "</tr>"
            for r in self.rows
        )
        return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


S = {  # strings of the generated blocks (the chapters carry the prose)
    "metric": {"fr": "Indicateur", "en": "Metric"},
    "value": {"fr": "Valeur", "en": "Value"},
    "target": {"fr": "Objectif", "en": "Target"},
    "met": {"fr": "Atteint", "en": "Met"},
    "yes": {"fr": "oui", "en": "yes"},
    "no": {"fr": "non", "en": "no"},
    "detected": {"fr": "Épisodes détectés", "en": "Episodes detected"},
    "median": {"fr": "Délai médian, épisodes détectés (jours ouvrés)", "en": "Median delay, detected episodes (business days)"},
    "median_all": {"fr": "Délai médian, tous les épisodes (manqué = 60 j)", "en": "Median delay, all episodes (missed = 60 d)"},
    "fp": {"fr": "Fausses alarmes par an", "en": "False alarms per year"},
    "share": {"fr": "Jours calmes en fausse alarme", "en": "Calm days in false alarm"},
    "brier": {"fr": "Brier de P(stress)", "en": "Brier score of P(stress)"},
    "ece": {"fr": "ECE de P(stress)", "en": "ECE of P(stress)"},
    "skill": {"fr": "Brier skill de P(stress)", "en": "Brier skill of P(stress)"},
    "switches": {"fr": "Changements de régime par an", "en": "Regime switches per year"},
    "days": {"fr": "Jours", "en": "Days"},
    "predicted": {"fr": "Probabilité moyenne affichée", "en": "Average probability shown"},
    "observed": {"fr": "Fréquence observée", "en": "Observed frequency"},
    "bin": {"fr": "Tranche", "en": "Bin"},
    "version": {"fr": "Version", "en": "Version"},
    "period": {"fr": "Période", "en": "Period"},
    "fingerprint": {"fr": "Empreinte des réglages", "en": "Settings fingerprint"},
    "param": {"fr": "Paramètre", "en": "Parameter"},
    "rule": {"fr": "Règle gelée", "en": "Frozen rule"},
    "regime": {"fr": "Régime", "en": "Regime"},
    "pstress": {"fr": "P(stress)", "en": "P(stress)"},
    "alarm": {"fr": "Alarme", "en": "Alarm"},
    "on": {"fr": "allumée", "en": "on"},
    "off": {"fr": "éteinte", "en": "off"},
    "ots": {"fr": "Horodatage", "en": "Timestamp"},
    "day": {"fr": "Jour", "en": "Day"},
}
OTS = {
    "bitcoin": {"fr": "ancré dans Bitcoin", "en": "anchored in Bitcoin"},
    "pending": {"fr": "en attente", "en": "pending"},
    "missing": {"fr": "aucun", "en": "none"},
}


def s(key: str, lang: str) -> str:
    return S[key][lang]


def episodes_table(rec: dict, lang: str) -> Table:
    rows = []
    for ep in rec["episodes"]:
        lat = ep.get("latency_days")
        rows.append(
            [
                fmt_date(ep["start"], lang),
                fmt_date(ep["end"], lang),
                t(f"hist.trigger.{ep['trigger']}", lang),
                _pct(ep["max_drawdown"], 1, lang).replace("-", MINUS),
                fmt_date(ep["signal_date"], lang) if ep.get("signal_date") else "–",
                _num(lat, 0, lang, signed=True) if lat is not None else t("tr.status.missed", lang),
            ]
        )
    heads = [
        t(k, lang)
        for k in ("tr.col.start", "tr.col.end", "tr.col.trigger", "tr.col.drawdown", "tr.col.signal_date", "tr.col.latency")
    ]
    return Table(heads, rows, [False, False, False, True, False, True])


def metrics_table(rec: dict, lang: str) -> Table:
    m, tg = rec["metrics"], rec["targets"]
    win = rec["rules"]["detection_window_days"]

    def ok(flag: bool) -> str:
        return s("yes" if flag else "no", lang)

    lat, fp, share = m["median_latency"], m["false_positives_per_year"], m["false_alarm_share"]
    rows = [
        [s("detected", lang), f"{m['detected']} / {m['n_episodes']}", "–", "–"],
        [
            s("median", lang),
            _num(lat, 0, lang),
            f"≤ {tg['max_median_latency_days']}",
            ok(lat is not None and lat <= tg["max_median_latency_days"]),
        ],
        [s("median_all", lang).replace("60", str(win)), _num(m["median_latency_all"], 0, lang), "–", "–"],
        [
            s("fp", lang),
            _num(fp, 2, lang),
            f"≤ {_num(tg['max_false_positives_per_year'], 1, lang)}",
            ok(fp is not None and fp <= tg["max_false_positives_per_year"]),
        ],
        [
            s("share", lang),
            _pct(share, 1, lang),
            f"≤ {_pct(tg['max_false_alarm_share'], 0, lang)}",
            ok(share is not None and share <= tg["max_false_alarm_share"]),
        ],
        [s("brier", lang), _num(m["brier"], 3, lang), "–", "–"],
        [s("ece", lang), _num(m["ece"], 3, lang), "–", "–"],
        [s("skill", lang), _num(m["brier_skill"], 2, lang, signed=True), "> 0", ok(m["brier_skill"] > 0)],
        [s("switches", lang), _num(m["switches_per_year"], 1, lang), "–", "–"],
    ]
    return Table([s("metric", lang), s("value", lang), s("target", lang), s("met", lang)], rows, [False, True, True, False])


def reliability_table(rec: dict, lang: str) -> Table:
    rows = [
        [
            f"{_pct(r['low'], 0, lang)} – {_pct(r['high'], 0, lang)}",
            _pct(r["predicted"], 1, lang),
            _pct(r["observed"], 1, lang),
            f"{r['days']:,}".replace(",", " "),
        ]
        for r in rec["reliability"]
    ]
    return Table([s("bin", lang), s("predicted", lang), s("observed", lang), s("days", lang)], rows, [False, True, True, True])


def versions_table(src: Sources, lang: str) -> Table:
    rows = []
    for rec in src.backtests.values():
        m, p = rec["metrics"], rec["period"]
        rows.append(
            [
                rec.get("model_version") or "–",
                f"{fmt_date(p['start'], lang)} → {fmt_date(p['end'], lang)}",
                f"{m['detected']}/{m['n_episodes']}",
                _num(m["median_latency"], 0, lang),
                _num(m["false_positives_per_year"], 2, lang),
                _num(m["brier"], 3, lang),
                _num(m["ece"], 3, lang),
                rec["config_sha256"][:12],
            ]
        )
    heads = [
        s("version", lang),
        s("period", lang),
        s("detected", lang),
        t("tr.col.latency", lang),
        s("fp", lang),
        "Brier",
        "ECE",
        s("fingerprint", lang),
    ]
    return Table(heads, rows, [False, False, True, True, True, True, True, False])


def rules_table(src: Sources, lang: str) -> Table:
    e = src.settings["validation"]["episodes"]
    fr = lang == "fr"
    rows = [
        [
            "validation.episodes.drawdown_threshold",
            _pct(e["drawdown_threshold"], 0, lang).replace("-", MINUS),
            "baisse depuis le plus haut sur 252 jours" if fr else "drawdown from the 252-day high",
        ],
        [
            "validation.episodes.vol_window / vol_quantile",
            f"{e['vol_window']} / {_pct(e['vol_quantile'], 0, lang)}",
            "volatilité réalisée au-dessus de son quantile (historique croissant)"
            if fr
            else "realised volatility above its expanding quantile",
        ],
        [
            "validation.episodes.min_gap_days",
            str(e["min_gap_days"]),
            "jours ouvrés entre la fin d'un épisode et le début du suivant"
            if fr
            else "business days between an episode end and the next start",
        ],
        [
            "validation.episodes.recovery_drawdown",
            _pct(e["recovery_drawdown"], 0, lang).replace("-", MINUS),
            "fin d'épisode quand la baisse repasse au-dessus" if fr else "the episode ends when the drawdown recovers above this",
        ],
        [
            "validation.episodes.max_duration_days",
            str(e["max_duration_days"]),
            "ou après ce nombre de jours ouvrés" if fr else "or after this many business days",
        ],
        [
            "validation.episodes.lookback_days",
            str(e["lookback_days"]),
            "une détection jusqu'à 20 jours avant le début compte" if fr else "a detection up to this many days early counts",
        ],
        [
            "validation.episodes.detection_window_days",
            str(e["detection_window_days"]),
            "au-delà, l'épisode est manqué" if fr else "later than this, the episode is missed",
        ],
        [
            "validation.confirm_days",
            str(src.settings["validation"]["confirm_days"]),
            "jours consécutifs au-dessus du seuil pour qu'une alarme compte"
            if fr
            else "consecutive days above the threshold for an alarm to count",
        ],
        [
            "validation.stress_probability_threshold",
            _num(src.settings["validation"]["stress_probability_threshold"], 1, lang),
            "seuil d'alarme sur le score du détecteur" if fr else "alarm threshold on the detector score",
        ],
    ]
    return Table([s("param", lang), s("value", lang), "Rôle" if fr else "Role"], rows, [False, True, False])


def live_table(src: Sources, lang: str, limit: int = 15) -> Table:
    rows = []
    for e in src.live.entries[-limit:]:
        p = e.get("p_stress")
        rows.append(
            [
                fmt_date(e["date"], lang),
                t(f"regime.{e['regime']}", lang) if e.get("regime") else "–",
                _pct(p, 0, lang) if p is not None else "–",
                s("on" if e.get("alarm_on") else "off", lang) if e.get("alarm_on") is not None else "–",
                e.get("model_version") or "–",
                OTS.get(e["ots"], OTS["missing"])[lang],
                e["sha256"][:12] + "…",
            ]
        )
    heads = [
        s("day", lang),
        s("regime", lang),
        s("pstress", lang),
        s("alarm", lang),
        s("version", lang),
        s("ots", lang),
        "SHA-256",
    ]
    return Table(heads, rows, [False, False, True, False, False, False, False])


TABLES = {
    "episodes": (episodes_table, "rec"),
    "metrics": (metrics_table, "rec"),
    "reliability": (reliability_table, "rec"),
    "versions": (versions_table, "src"),
    "rules": (rules_table, "src"),
    "live": (live_table, "src"),
}


# ---------------------------------------------------------------- figures
PALETTE = {
    "--page": "#f9f9f7", "--surface": "#fcfcfb", "--ink": "#0b0b0b", "--ink2": "#52514e", "--muted": "#898781",
    "--grid": "#e1e0d9", "--axis": "#c3c2b7", "--p": "#2a78d6", "--score": "#898781", "--band": "#ecebe6",
    "--alarm": "#d03b3b", "--good": "#006300", "--bad": "#b42323",
}  # fmt: skip


def _svg(markup: str) -> str:
    m = re.search(r"<svg.*?</svg>", markup, re.S)
    return m.group(0) if m else ""


def _reliability_svg(rec: dict, lang: str) -> str:
    """Predicted against observed frequency per bin of P(stress): on the diagonal = the probability means what it says."""
    W, H, L, R, top, bottom = 560, 380, 56, 16, 14, 46
    pw, ph = W - L - R, H - top - bottom

    def x(v):
        return L + v * pw

    def y(v):
        return top + (1 - v) * ph

    bins = rec["reliability"]
    top_days = max((b["days"] for b in bins), default=1) or 1
    parts = []
    for v in (0, 0.25, 0.5, 0.75, 1):
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--grid)"/>')
        parts.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{top}" y2="{top + ph}" stroke="var(--grid)"/>')
        parts.append(f'<text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{_pct(v, 0, lang)}</text>')
        parts.append(f'<text x="{x(v):.1f}" y="{top + ph + 16}" text-anchor="middle">{_pct(v, 0, lang)}</text>')
    parts.append(f'<line x1="{x(0)}" x2="{x(1)}" y1="{y(0)}" y2="{y(1)}" stroke="var(--ink2)" stroke-dasharray="5 4"/>')
    pts = [(b["predicted"], b["observed"], b["days"]) for b in bins if b["days"]]
    if len(pts) > 1:
        line = " ".join(f"{x(p):.1f},{y(o):.1f}" for p, o, _ in pts)
        parts.append(f'<polyline points="{line}" fill="none" stroke="var(--p)" stroke-width="2"/>')
    for p, o, d in pts:
        r = 3 + 6 * (d / top_days) ** 0.5
        tip = f"{_pct(p, 1, lang)} → {_pct(o, 1, lang)} ({d})"
        parts.append(
            f'<circle cx="{x(p):.1f}" cy="{y(o):.1f}" r="{r:.1f}" fill="var(--p)" fill-opacity=".75" stroke="var(--surface)" stroke-width="1.5"><title>{html.escape(tip)}</title></circle>'
        )
    xl = "probabilité affichée (moyenne de la tranche)" if lang == "fr" else "probability shown (bin average)"
    yl = "fréquence observée" if lang == "fr" else "observed frequency"
    parts.append(f'<text x="{L + pw / 2:.1f}" y="{H - 8}" text-anchor="middle">{xl}</text>')
    parts.append(
        f'<text x="14" y="{top + ph / 2:.1f}" text-anchor="middle" transform="rotate(-90 14 {top + ph / 2:.1f})">{yl}</text>'
    )
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(yl)}">{"".join(parts)}</svg>'


def timeline_svg(rec: dict, lang: str) -> str:
    return _svg(_timeline("thesis", rec["daily"], rec["episodes"], rec["rules"]["alarm_threshold"], lang))


def latency_svg(rec: dict, lang: str) -> str:
    return _svg(_latency_chart(rec["episodes"], rec["rules"], rec["targets"]["max_median_latency_days"], lang))


FIGURES = {"timeline": timeline_svg, "latency": latency_svg, "reliability": _reliability_svg}

CAPTIONS = {
    "tables": {
        "episodes": {
            "fr": "Épisodes de stress datés par la règle gelée et délai de détection de chacun (jours ouvrés ; négatif : alarme déjà allumée avant le début daté). Version {v}.",
            "en": "Stress episodes dated by the frozen rule and the detection delay of each (business days; negative: alarm already on before the dated start). Version {v}.",
        },
        "metrics": {
            "fr": "Résultats du backtest hors échantillon, version {v}, contre les objectifs fixés avant les tests.",
            "en": "Out-of-sample backtest results, version {v}, against the targets fixed before testing.",
        },
        "reliability": {
            "fr": "Fiabilité de P(stress), version {v} : probabilité moyenne affichée et fréquence observée par tranche de 10 points.",
            "en": "Reliability of P(stress), version {v}: average probability shown and observed frequency in each 10-point bin.",
        },
        "versions": {
            "fr": "Un enregistrement de backtest par configuration, tous conservés dans le dépôt.",
            "en": "One backtest record per configuration, all kept in the repository.",
        },
        "rules": {
            "fr": "Règle de datation des épisodes et de détection, telle qu'elle est dans la configuration (gelée par son hachage).",
            "en": "The episode dating and detection rules as set in the configuration (frozen by their hash).",
        },
        "live": {
            "fr": "Derniers jours publiés (régime, P(stress), alarme, version, horodatage) : lus dans le dépôt, jamais recalculés.",
            "en": "Latest published days (regime, P(stress), alarm, version, timestamp): read from the repository, never recomputed.",
        },
    },
    "figures": {
        "timeline": {
            "fr": "P(stress) (bleu), score du détecteur (gris), seuil d'alarme (pointillés), épisodes (bandes) et alarme de stress (bande rouge), version {v}, hors échantillon.",
            "en": "P(stress) (blue), detector score (grey), alarm threshold (dashed), episodes (bands) and stress alarm (red strip), version {v}, out of sample.",
        },
        "latency": {
            "fr": "Premier jour d'alarme de chaque épisode par rapport au début daté (0), version {v}. Zone grisée : objectif.",
            "en": "First alarm day of each episode relative to the dated start (0), version {v}. Shaded zone: target.",
        },
        "reliability": {
            "fr": "Courbe de fiabilité de P(stress), version {v} : la diagonale est la calibration parfaite, la taille d'un point croît avec le nombre de jours.",
            "en": "Reliability curve of P(stress), version {v}: the diagonal is perfect calibration, dot size grows with the number of days.",
        },
    },
}


def standalone_svg(svg: str) -> str:
    """The SVG as a file of its own: palette values in place of CSS variables, so any viewer draws it."""
    for name, value in PALETTE.items():
        svg = svg.replace(f"var({name})", value)
    style = "text{fill:#898781;font:11px sans-serif}.miss{fill:#b42323}"
    return svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1).replace(">", f"><style>{style}</style>", 1)


# ---------------------------------------------------------------- quotes
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("`", "").replace("**", "")).strip().lower()


def extract_section(text: str, path: str) -> str:
    """The body of the section named by `A > B > C` (heading text, nested), without its heading.

    A segment matches a heading exactly, or by prefix when that is unambiguous. Raises KeyError if absent.
    """
    lines = text.split("\n")
    # Heading positions outside code fences.
    heads, fenced = [], False
    for n, line in enumerate(lines):
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and (m := re.match(r"(#{1,6})\s+(.*?)\s*$", line)):
            heads.append((n, len(m.group(1)), m.group(2)))
    start, end, level = 0, len(lines), 0  # current search span: lines[start:end], headings deeper than `level`
    for segment in [p.strip() for p in path.split(" > ")]:
        cands = [(n, lv, h) for n, lv, h in heads if start <= n < end and lv > level]
        want = _norm(segment)
        exact = [c for c in cands if _norm(c[2]) == want]
        pick = exact or [c for c in cands if _norm(c[2]).startswith(want)]
        if len(pick) != 1:
            raise KeyError(f"section '{segment}' {'not found' if not pick else 'is ambiguous'}")
        n, lv, _ = pick[0]
        nxt = next((m for m, lvl, _h in heads if m > n and lvl <= lv), len(lines))
        start, end, level = n + 1, nxt, lv
    body = "\n".join(lines[start:end]).strip("\n")
    return body.strip()


def quote_block(src: Sources, ref: str, lang: str, declared: set[str]) -> str:
    """A verbatim quote of docs/<doc>#<section path>, as a Markdown blockquote with its provenance."""
    doc, _, path = ref.partition("#")
    if doc not in declared:
        raise ThesisError([f"quote of docs/{doc} but the chapter's manifest entry does not list it under 'sources'"])
    file = src.docs_dir / doc
    if not file.exists():
        raise ThesisError([f"quote: docs/{doc} does not exist"])
    try:
        body = extract_section(file.read_text(encoding="utf-8"), path)
    except KeyError as exc:
        raise ThesisError([f"quote docs/{doc}#{path}: {exc.args[0]}"]) from exc
    # Relative links to other docs mean nothing in a standalone report: keep their text.
    body = re.sub(r"\[([^\]]+)\]\((?!https?://|#)[^)]*\)", r"\1", body)
    out = []
    for line in body.split("\n"):  # a heading inside a quote becomes a bold line: the chapter owns the outline
        m = re.match(r"#{1,6}\s+(.*)", line)
        out.append(f"**{m.group(1)}**" if m else line)
    commit, day = src.doc_commit(doc)
    last = f" (commit {commit}, {fmt_date(day, lang)})" if commit else ""
    label = (
        f"**Citation textuelle** de `docs/{doc}`, section « {path.split(' > ')[-1]} »{last}. Texte original en anglais, seuls les titres internes et les liens relatifs sont adaptés."
        if lang == "fr"
        else f"**Verbatim quote** from `docs/{doc}`, section “{path.split(' > ')[-1]}”{last}. Only inner headings and relative links are adapted."
    )
    quoted = "\n".join(f"> {line}" if line else ">" for line in [label, "", *out])
    return quoted
