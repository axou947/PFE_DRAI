"""The public track-record page: one self-contained HTML file per language, built from track_record/.

No external file, font or script: the page works offline, from the repository, on GitHub Pages and
inside the app. Charts are inline SVG drawn here (readable without JavaScript); a few lines of
script add the hover readout. The page holds no "generated now" time, so rebuilding it from the
same records gives the same file (the daily job only commits when something changed).
"""

import hashlib
import html
import json
from pathlib import Path

import pandas as pd

from ..i18n import fmt_date, fmt_pct, t
from .record import (
    LiveRecord,
    backtest_record,
    find_backtest,
    list_backtests,
    live_scorecard,
    ots_status,
    read_live,
    record_backtest,
)

LANGS = {"en": "index.html", "fr": "fr.html"}

# Reference palette (dataviz skill): series-1 blue for P(stress), muted ink for the detector score,
# status critical for the alarm, a neutral band for the episodes. Text stays in ink tokens.
CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);--p:#2a78d6;--score:#898781;--band:#ecebe6;
--alarm:#d03b3b;--good:#006300;--bad:#b42323;--chip:#f0efec;--warn-bg:#fff4e0;--warn-ink:#6b4500}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;
--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--p:#3987e5;
--score:#898781;--band:#2a2a28;--alarm:#e66767;--good:#0ca30c;--bad:#e66767;--chip:#2a2a28;--warn-bg:#3a2c10;--warn-ink:#f5d9a6}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--grid:#2c2c2a;
--axis:#383835;--border:rgba(255,255,255,.10);--p:#3987e5;--band:#2a2a28;--alarm:#e66767;--good:#0ca30c;--bad:#e66767;
--chip:#2a2a28;--warn-bg:#3a2c10;--warn-ink:#f5d9a6}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:0 auto;padding:28px 16px 48px}
header .top{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}
h1{font-size:1.9rem;margin:0 0 4px}h2{font-size:1.35rem;margin:40px 0 6px}h3{font-size:1.05rem;margin:26px 0 6px}
p{margin:6px 0}a{color:var(--p)}.muted{color:var(--ink2)}.small{font-size:.85rem}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 18px;margin:12px 0}
.notice{background:var(--warn-bg);color:var(--warn-ink);border-radius:8px;padding:10px 14px;margin:12px 0}
.badge{display:inline-block;font-size:.75rem;font-weight:600;letter-spacing:.04em;text-transform:uppercase;
padding:2px 8px;border-radius:999px;background:var(--chip);color:var(--ink2);margin-right:6px}
.badge.live{background:var(--p);color:#fff}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:12px 0}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.tile .k{color:var(--ink2);font-size:.82rem}.tile .v{font-size:1.55rem;font-weight:650;margin:2px 0}
.tile .s{font-size:.8rem;color:var(--ink2)}.ok{color:var(--good)}.ko{color:var(--bad)}
.ok::before{content:"✓ "}.ko::before{content:"✗ "}
.alarm-on{color:var(--alarm);font-weight:650}.alarm-on::before{content:"● "}
.table-wrap{overflow-x:auto;margin:8px 0}
table{border-collapse:collapse;width:100%;font-size:.88rem;background:var(--surface)}
th,td{padding:6px 10px;border-bottom:1px solid var(--grid);text-align:left;white-space:nowrap}
th{color:var(--ink2);font-weight:600}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
code{font:12.5px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--chip);padding:1px 5px;border-radius:4px}
pre{background:var(--chip);padding:10px 12px;border-radius:8px;overflow-x:auto;font-size:12.5px}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.82rem;color:var(--ink2);margin:6px 0}
.legend i{display:inline-block;width:16px;height:0;border-top:2px solid;vertical-align:middle;margin-right:5px}
.legend i.box{height:10px;border:0;border-radius:2px}
.chart{position:relative;overflow-x:auto}.chart svg{width:100%;min-width:640px;height:auto;display:block}
.chart text{fill:var(--muted);font-size:11px;font-family:inherit}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--border);border-radius:8px;
padding:8px 10px;font-size:.8rem;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;min-width:170px}
.tip b{font-variant-numeric:tabular-nums}
details{margin:8px 0}summary{cursor:pointer;color:var(--ink2)}
footer{margin-top:48px;color:var(--ink2);font-size:.82rem;border-top:1px solid var(--grid);padding-top:12px}
"""

SCRIPT = """
document.querySelectorAll('.chart[data-series]').forEach(function(box){
  var d=JSON.parse(document.getElementById(box.dataset.series).textContent);
  var svg=box.querySelector('svg'),tip=box.querySelector('.tip'),line=box.querySelector('.cross');
  var L=+box.dataset.left,R=+box.dataset.right,W=+box.dataset.width,t0=+box.dataset.t0,t1=+box.dataset.t1;
  var lab=JSON.parse(box.dataset.labels);
  var ts=d.date.map(function(s){return Date.parse(s)});
  function show(ev){
    var r=svg.getBoundingClientRect(),x=(ev.clientX-r.left)*W/r.width;
    if(x<L||x>W-R){hide();return}
    var target=t0+(x-L)/(W-L-R)*(t1-t0),lo=0,hi=ts.length-1;
    while(hi-lo>1){var m=(lo+hi)>>1;if(ts[m]<target)lo=m;else hi=m}
    var i=Math.abs(ts[lo]-target)<Math.abs(ts[hi]-target)?lo:hi,px=L+(ts[i]-t0)/(t1-t0)*(W-L-R);
    line.setAttribute('x1',px);line.setAttribute('x2',px);line.style.display='';
    tip.textContent='';
    function row(v,k){var p=document.createElement('div'),b=document.createElement('b');b.textContent=v;
      p.appendChild(b);p.appendChild(document.createTextNode(' '+k));tip.appendChild(p)}
    var h=document.createElement('div');h.textContent=d.date[i];h.style.color='var(--ink2)';tip.appendChild(h);
    row(d.p_stress[i]==null?'–':Math.round(d.p_stress[i]*100)+'%',lab.p);
    if(d.score&&d.score[i]!=null)row(Math.round(d.score[i]*100)+'%',lab.score);
    row(d.alarm[i]?lab.on:lab.off,lab.alarm);
    if(d.episode&&d.episode[i])row('●',lab.episode);
    tip.style.display='block';
    var left=(px*r.width/W)+12;if(left+tip.offsetWidth>r.width)left=(px*r.width/W)-tip.offsetWidth-12;
    tip.style.left=left+'px';tip.style.top='8px';
  }
  function hide(){tip.style.display='none';line.style.display='none'}
  svg.addEventListener('pointermove',show);svg.addEventListener('pointerleave',hide);
});
"""


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _date(value, lang: str) -> str:
    return "–" if value is None else fmt_date(value, lang)


def _pct(value, lang: str, digits: int = 0) -> str:
    return "–" if value is None else fmt_pct(value, lang, digits)


def _num(value, lang: str, digits: int = 2) -> str:
    if value is None:
        return "–"
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if lang == "fr" else text


def _signed(value) -> str:
    return "–" if value is None else f"{value:+d}" if value else "0"


def _table(headers: list[tuple[str, bool]], rows: list[list[str]]) -> str:
    """headers: (label, numeric). Cells are already escaped HTML."""
    head = "".join(f'<th class="n">{h}</th>' if n else f"<th>{h}</th>" for h, n in headers)
    body = "".join(
        "<tr>"
        + "".join(f'<td class="n">{c}</td>' if n else f"<td>{c}</td>" for c, (_, n) in zip(r, headers, strict=True))
        + "</tr>"
        for r in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _note(text: str, cls: str = "") -> str:
    """Plain text (escaped) in a muted paragraph, or in a card."""
    return f'<div class="card">{_e(text)}</div>' if cls == "card" else f'<p class="small muted">{_e(text)}</p>'


def _tile(label: str, value: str, sub: str = "", ok: bool | None = None) -> str:
    cls = "s" if ok is None else ("s ok" if ok else "s ko")
    sub_html = f'<div class="{cls}">{sub}</div>' if sub else ""
    return f'<div class="tile"><div class="k">{label}</div><div class="v">{value}</div>{sub_html}</div>'


# ---------------------------------------------------------------- charts
def _timeline(series_id: str, daily: dict, episodes: list[dict], threshold: float | None, lang: str) -> str:
    """P(stress) (and the detector score) over time, episode bands, and an alarm strip below the plot."""
    dates = pd.to_datetime(daily["date"])
    if len(dates) < 2:
        return ""
    W, H, L, R, top, plot_h = 1000, 300, 56, 12, 10, 210
    strip_y = top + plot_h + 14
    t0, t1 = dates[0].value // 10**6, dates[-1].value // 10**6

    def x(d) -> float:
        return L + (pd.Timestamp(d).value // 10**6 - t0) / max(t1 - t0, 1) * (W - L - R)

    def y(v) -> float:
        return top + (1 - v) * plot_h

    parts = []
    for v in (0, 0.25, 0.5, 0.75, 1):
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{_e(_pct(v, lang))}</text>')
    for ep in episodes:
        x0, x1 = x(max(pd.Timestamp(ep["start"]), dates[0])), x(min(pd.Timestamp(ep["end"]), dates[-1]))
        parts.append(
            f'<rect x="{x0:.1f}" y="{top}" width="{max(x1 - x0, 1.5):.1f}" height="{plot_h}" fill="var(--band)">'
            f"<title>{_e(t('tr.lg.episode', lang))} {_e(_date(ep['start'], lang))}</title></rect>"
        )
    years = pd.date_range(dates[0], dates[-1], freq="YS")
    step = max(1, len(years) // 9)
    for d in years[::step]:
        parts.append(f'<text x="{x(d):.1f}" y="{strip_y + 30}" text-anchor="middle">{d.year}</text>')
    if len(years) == 0 or len(dates) < 60:
        for d, anchor in ((dates[0], "start"), (dates[-1], "end")):
            parts.append(f'<text x="{x(d):.1f}" y="{strip_y + 30}" text-anchor="{anchor}">{_e(_date(d, lang))}</text>')
    if threshold is not None:
        parts.append(
            f'<line x1="{L}" x2="{W - R}" y1="{y(threshold):.1f}" y2="{y(threshold):.1f}" stroke="var(--ink2)" '
            'stroke-width="1" stroke-dasharray="4 4"/>'
        )
    xs = [x(d) for d in dates]
    if daily.get("score") and any(v is not None for v in daily["score"]):
        pts = " ".join(f"{a:.1f},{y(v):.1f}" for a, v in zip(xs, daily["score"], strict=True) if v is not None)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="var(--score)" stroke-width="1" opacity=".75"/>')
    pts = " ".join(f"{a:.1f},{y(v):.1f}" for a, v in zip(xs, daily["p_stress"], strict=True) if v is not None)
    parts.append(f'<polyline points="{pts}" fill="none" stroke="var(--p)" stroke-width="2" stroke-linejoin="round"/>')
    # Alarm strip: one bar per stretch of days with the alarm on.
    parts.append(f'<text x="{L - 6}" y="{strip_y + 9}" text-anchor="end">{_e(t("tr.lg.alarm_short", lang))}</text>')
    parts.append(f'<rect x="{L}" y="{strip_y}" width="{W - L - R}" height="12" fill="var(--band)" rx="2"/>')
    on = daily["alarm"]
    i = 0
    while i < len(on):
        if on[i]:
            j = i
            while j + 1 < len(on) and on[j + 1]:
                j += 1
            x0, x1 = xs[i], xs[j]
            parts.append(
                f'<rect x="{x0:.1f}" y="{strip_y}" width="{max(x1 - x0, 2):.1f}" height="12" fill="var(--alarm)" rx="1"/>'
            )
            i = j + 1
        else:
            i += 1
    parts.append(
        f'<line class="cross" y1="{top}" y2="{strip_y + 12}" stroke="var(--ink2)" stroke-width="1" style="display:none"/>'
    )
    labels = {
        "p": t("tr.lg.p", lang),
        "score": t("tr.lg.score", lang),
        "alarm": t("tr.lg.alarm", lang),
        "on": t("tr.on", lang),
        "off": t("tr.off", lang),
        "episode": t("tr.lg.episode", lang),
    }
    payload = dict(daily)
    mask = pd.Series(0, index=dates)
    for ep in episodes:
        mask.loc[pd.Timestamp(ep["start"]) : pd.Timestamp(ep["end"])] = 1
    payload["episode"] = [int(v) for v in mask]
    legend = (
        f'<div class="legend"><span><i style="border-color:var(--p)"></i>{_e(t("tr.lg.p", lang))}</span>'
        + (f'<span><i style="border-color:var(--score)"></i>{_e(t("tr.lg.score", lang))}</span>' if daily.get("score") else "")
        + (
            f'<span><i style="border-color:var(--ink2);border-top-style:dashed"></i>{_e(t("tr.lg.threshold", lang))}</span>'
            if threshold is not None
            else ""
        )
        + f'<span><i class="box" style="background:var(--band)"></i>{_e(t("tr.lg.episode", lang))}</span>'
        f'<span><i class="box" style="background:var(--alarm)"></i>{_e(t("tr.lg.alarm", lang))}</span></div>'
    )
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    return (
        f'{legend}<div class="chart" data-series="{series_id}" data-left="{L}" data-right="{R}" data-width="{W}" '
        f'data-t0="{t0}" data-t1="{t1}" data-labels=\'{_e(json.dumps(labels))}\'>'
        f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_e(t("tr.bt.chart", lang))}">{"".join(parts)}</svg>'
        f'<div class="tip"></div></div><script type="application/json" id="{series_id}">{data}</script>'
    )


def _latency_chart(episodes: list[dict], rules: dict, target: float, lang: str) -> str:
    """One row per episode: where the first alarm fell, from `lookback` days early to the window end."""
    if not episodes:
        return ""
    lo, hi = -rules["lookback_days"], rules["detection_window_days"]
    W, L, R, row_h, top = 1000, 120, 70, 24, 22
    H = top + row_h * len(episodes) + 26

    def x(v) -> float:
        return L + (v - lo) / (hi - lo) * (W - L - R)

    parts = [
        f'<rect x="{x(lo):.1f}" y="{top - 6}" width="{x(target) - x(lo):.1f}" height="{row_h * len(episodes) + 6}" '
        'fill="var(--band)" rx="3"/>',
        f'<text x="{x(target) - 4:.1f}" y="{top - 10}" text-anchor="end">{_e(t("tr.bt.target_zone", lang, v=int(target)))}'
        "</text>",
    ]
    for v in range(lo, hi + 1, 10):
        parts.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{top - 6}" y2="{H - 22}" stroke="var(--grid)"/>')
        parts.append(f'<text x="{x(v):.1f}" y="{H - 6}" text-anchor="middle">{v:+d}</text>' if v else "")
    parts.append(f'<line x1="{x(0):.1f}" x2="{x(0):.1f}" y1="{top - 6}" y2="{H - 22}" stroke="var(--axis)" stroke-width="2"/>')
    parts.append(f'<text x="{x(0):.1f}" y="{H - 6}" text-anchor="middle">{_e(t("tr.bt.start_day", lang))}</text>')
    for i, ep in enumerate(episodes):
        cy = top + row_h * i + row_h / 2 - 3
        parts.append(f'<text x="{L - 10}" y="{cy + 4:.1f}" text-anchor="end">{_e(_date(ep["start"], lang))}</text>')
        lat = ep.get("latency_days")
        status = ep.get("status")
        if lat is None:
            label = t("tr.status.pending", lang) if status == "pending" else t("tr.status.missed", lang)
            parts.append(f'<text x="{W - R + 6}" y="{cy + 4:.1f}" class="miss">{_e(label)}</text>')
            continue
        tip = f"{_date(ep['start'], lang)}: {_signed(lat)} {t('tr.bd', lang)}"
        parts.append(f'<line x1="{x(0):.1f}" x2="{x(lat):.1f}" y1="{cy:.1f}" y2="{cy:.1f}" stroke="var(--p)" stroke-width="2"/>')
        parts.append(
            f'<circle cx="{x(lat):.1f}" cy="{cy:.1f}" r="5" fill="var(--p)" stroke="var(--surface)" stroke-width="2">'
            f"<title>{_e(tip)}</title></circle>"
        )
        anchor, dx, dy = ("end", -9, 4) if lat < 0 else ("start", 9, 4)
        if lat < lo + 4:  # no room on the left: above the dot
            anchor, dx, dy = "middle", 0, -8
        parts.append(f'<text x="{x(lat) + dx:.1f}" y="{cy + dy:.1f}" text-anchor="{anchor}">{_signed(lat)}</text>')
    return (
        f'<div class="chart"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{_e(t("tr.bt.latency", lang))}">'
        f"{''.join(parts)}</svg></div>"
    )


# ---------------------------------------------------------------- sections
def _episode_rows(episodes: list[dict], lang: str, live: bool = False) -> list[list[str]]:
    rows = []
    for ep in episodes:
        lat = ep.get("latency_days")
        if lat is not None:
            status = t("tr.status.detected", lang)
        else:
            status = t("tr.status.pending" if ep.get("status") == "pending" else "tr.status.missed", lang)
        rows.append(
            [
                _e(_date(ep["start"], lang)),
                _e(_date(ep["end"], lang)),
                _e(t(f"hist.trigger.{ep['trigger']}", lang)),
                _e(_pct(ep["max_drawdown"], lang, 1)),
                _e(_date(ep.get("signal_date"), lang)),
                _e(_signed(lat)),
                _e(status),
            ]
        )
    return rows


def _episode_headers(lang: str):
    return [
        (t("tr.col.start", lang), False),
        (t("tr.col.end", lang), False),
        (t("tr.col.trigger", lang), False),
        (t("tr.col.drawdown", lang), True),
        (t("tr.col.signal_date", lang), False),
        (t("tr.col.latency", lang), True),
        (t("tr.col.status", lang), False),
    ]


def _alarm_table(alarms: list[dict], lang: str) -> str:
    rows = []
    for a in alarms:
        if a.get("pending"):
            kind = _e(t("tr.kind.pending", lang))
        elif a["false_alarm"]:
            kind = f'<span class="ko">{_e(t("tr.kind.false", lang))}</span>'
        else:
            kind = _e(t("tr.kind.crisis", lang, date=_date(a["episode_start"], lang)))
        end = t("tr.kind.open", lang) if a.get("open") else _date(a["end"], lang)
        rows.append(
            [
                _e(_date(a["start"], lang)),
                _e(end),
                _e(a["days"]),
                _e(_pct(a.get("peak_score"), lang)),
                kind,
            ]
        )
    headers = [
        (t("tr.col.alarm_on", lang), False),
        (t("tr.col.alarm_off", lang), False),
        (t("tr.col.days", lang), True),
        (t("tr.col.peak", lang), True),
        (t("tr.col.kind", lang), False),
    ]
    return _table(headers, rows)


def _live_section(live: LiveRecord, score: dict, threshold: float, lang: str) -> str:
    out = [f'<h2><span class="badge live">{_e(t("tr.badge.live", lang))}</span>{_e(t("tr.live.title", lang))}</h2>']
    out.append(f'<p class="muted">{t("tr.live.intro", lang)}</p>')
    if not live.entries:
        out.append(f'<div class="card">{_e(t("tr.live.empty", lang))}</div>')
        return "".join(out)
    last = live.last
    counts = {k: sum(e["ots"] == k for e in live.entries) for k in ("bitcoin", "pending", "missing")}
    alarm = (
        f'<span class="alarm-on">{_e(t("tr.on", lang))}</span>'
        if last.get("alarm_on")
        else _e(t("tr.off", lang))
        if last.get("alarm_on") is not None
        else "–"
    )
    alarm_sub = t("tr.live.since", lang, date=_date(last.get("alarm_since"), lang)) if last.get("alarm_on") else ""
    out.append('<div class="tiles">')
    out.append(_tile(t("tr.live.latest", lang), _e(_date(last["date"], lang)), _e(t(f"regime.{last['regime']}", lang))))
    out.append(_tile(t("tr.lg.p", lang), _e(_pct(last.get("p_stress"), lang)), _e(t("tr.live.p_help", lang))))
    out.append(_tile(t("tr.lg.alarm", lang), alarm, _e(alarm_sub)))
    out.append(
        _tile(
            t("tr.live.days", lang),
            _e(len(live.entries)),
            _e(t("tr.live.since", lang, date=_date(live.first, lang))),
        )
    )
    chain = t("tr.live.chain_ok", lang) if live.chain_ok else t("tr.live.chain_broken", lang, n=len(live.problems))
    out.append(
        _tile(
            t("tr.live.integrity", lang),
            _e(t("tr.live.ots_count", lang, n=counts["bitcoin"], total=len(live.entries))),
            _e(chain),
            ok=live.chain_ok,
        )
    )
    out.append("</div>")
    if live.problems:
        out.append('<div class="notice">' + "<br>".join(_e(p) for p in live.problems) + "</div>")
    if score.get("missing_days"):
        out.append(f'<p class="small muted">{_e(t("tr.live.missing", lang, n=score["missing_days"]))}</p>')

    daily = {
        "date": [e["date"] for e in live.entries],
        "p_stress": [e.get("p_stress") for e in live.entries],
        "score": [e.get("alarm_score") for e in live.entries],
        "alarm": [int(bool(e.get("alarm_on"))) for e in live.entries],
    }
    if len(live.entries) >= 2:
        out.append(_timeline(f"live-{lang}", daily, score.get("episodes", []), threshold, lang))

    out.append(f"<h3>{_e(t('tr.live.crises', lang))}</h3>")
    if score.get("unscored"):
        out.append(_note(t("tr.live.unscored", lang), "card"))
        return "".join(out) + _days_table(live, lang)
    out.append(f'<p class="small muted">{_e(t("tr.live.crises_help", lang))}</p>')
    if score.get("episodes"):
        out.append(_table(_episode_headers(lang), _episode_rows(score["episodes"], lang, live=True)))
    else:
        last_day = score.get("last_market_day") or live.last["date"]
        out.append(_note(t("tr.live.no_crisis", lang, start=_date(live.first, lang), end=_date(last_day, lang)), "card"))

    out.append(f"<h3>{_e(t('tr.live.alarms', lang))}</h3>")
    if score.get("alarms"):
        out.append(_alarm_table(score["alarms"], lang))
    else:
        out.append(f'<div class="card">{_e(t("tr.live.no_alarm", lang, date=_date(live.first, lang)))}</div>')

    return "".join(out) + _days_table(live, lang)


def _days_table(live: LiveRecord, lang: str) -> str:
    ots_label = {k: t(f"tr.ots.{k}", lang) for k in ("bitcoin", "pending", "missing")}
    rows = []
    for e in reversed(live.entries):
        files = f'<a href="{_e(e["file"])}">json</a>' + (
            f' · <a href="{_e(e["file"])}.ots">ots</a>' if e["ots"] != "missing" else ""
        )
        rows.append(
            [
                _e(_date(e["date"], lang)),
                _e(t(f"regime.{e['regime']}", lang) if e.get("regime") else "–"),
                _e(_pct(e.get("p_stress"), lang)),
                f'<span class="alarm-on">{_e(t("tr.on", lang))}</span>' if e.get("alarm_on") else _e(t("tr.off", lang)),
                _e((e.get("published_at") or "–").replace("T", " ").replace("+00:00", " UTC")),
                _e(e.get("model_version") or "–"),
                f"<code>{_e(e['sha256'][:12])}</code>" + ("" if e["hash_ok"] else ' <span class="ko"></span>'),
                _e(ots_label[e["ots"]]),
                files,
            ]
        )
    headers = [
        (t("tr.col.date", lang), False),
        (t("tr.col.regime", lang), False),
        (t("tr.lg.p", lang), True),
        (t("tr.lg.alarm", lang), False),
        (t("tr.col.published", lang), False),
        (t("tr.col.version", lang), False),
        ("SHA-256", False),
        ("OpenTimestamps", False),
        (t("tr.col.files", lang), False),
    ]
    table = _table(headers, rows)
    if len(rows) > 15:
        table = f"<details><summary>{_e(t('tr.live.show_days', lang, n=len(rows)))}</summary>{table}</details>"
    return f"<h3>{_e(t('tr.live.days_table', lang))}</h3>{table}"


def _verify_section(live: LiveRecord, lang: str) -> str:
    day = live.last["date"] if live.entries else "2026-10-02"
    return (
        f'<h3>{_e(t("tr.verify.title", lang))}</h3><div class="card"><p>{t("tr.verify.intro", lang)}</p>'
        f"<pre>sha256sum {day}.json            # = {_e(t('tr.verify.c1', lang))}\n"
        f"ots verify {day}.json.ots        # {_e(t('tr.verify.c2', lang))}</pre>"
        f'<p class="small muted">{t("tr.verify.outro", lang)}</p></div>'
    )


def _backtest_section(bt: dict | None, bt_meta: dict, repo: str, lang: str) -> str:
    if bt is None:
        return (
            f'<h2><span class="badge">{_e(t("tr.badge.backtest", lang))}</span>{_e(t("tr.bt.title_none", lang))}</h2>'
            f'<div class="card">{_e(t("tr.bt.none", lang))}</div>'
        )
    m, rules, targets = bt["metrics"], bt["rules"], bt["targets"]
    out = [
        f'<h2><span class="badge">{_e(t("tr.badge.backtest", lang))}</span>'
        f"{_e(t('tr.bt.title', lang, start=_date(bt['period']['start'], lang), end=_date(bt['period']['end'], lang)))}</h2>"
    ]
    if not bt.get("is_live_data"):
        out.append(f'<div class="notice"><b>{_e(t("tr.simulated", lang))}</b></div>')
    out.append(f'<div class="notice">{t("tr.bt.warning", lang, doc=f"{repo}/blob/main/docs/DETECTION_V2.md")}</div>')
    lat, lat_all = m["median_latency"], m["median_latency_all"]
    out.append('<div class="tiles">')
    out.append(_tile(t("tr.bt.detected", lang), f"{m['detected']} / {m['n_episodes']}", _e(t("tr.bt.detected_sub", lang))))
    out.append(
        _tile(
            t("tr.bt.median_latency", lang),
            _e(t("tr.bt.days", lang, v=_num(lat, lang, 0) if lat is not None else "–")),
            _e(t("tr.bt.target", lang, v=targets["max_median_latency_days"])),
            ok=lat is not None and lat <= targets["max_median_latency_days"],
        )
    )
    out.append(
        _tile(
            t("tr.bt.median_latency_all", lang),
            _e(t("tr.bt.days", lang, v=_num(lat_all, lang, 0) if lat_all is not None else "–")),
            _e(t("tr.bt.median_all_sub", lang, v=rules["detection_window_days"])),
        )
    )
    out.append(
        _tile(
            t("tr.bt.fp", lang),
            _e(_num(m["false_positives_per_year"], lang)),
            _e(t("tr.bt.target", lang, v=_num(targets["max_false_positives_per_year"], lang, 1))),
            ok=m["false_positives_per_year"] is not None
            and m["false_positives_per_year"] <= targets["max_false_positives_per_year"],
        )
    )
    out.append(
        _tile(
            t("tr.bt.false_share", lang),
            _e(_pct(m["false_alarm_share"], lang, 1)),
            _e(t("tr.bt.target", lang, v=_pct(targets["max_false_alarm_share"], lang))),
            ok=m["false_alarm_share"] is not None and m["false_alarm_share"] <= targets["max_false_alarm_share"],
        )
    )
    out.append(
        _tile(
            t("tr.bt.brier", lang),
            _e(_num(m["brier"], lang, 3)),
            _e(t("tr.bt.brier_sub", lang, ece=_num(m["ece"], lang, 3))),
        )
    )
    out.append("</div>")

    out.append(f"<h3>{_e(t('tr.bt.chart', lang))}</h3>")
    out.append(
        _note(
            t(
                "tr.bt.chart_help",
                lang,
                h=rules["calibration_horizon_days"],
                thr=_pct(rules["alarm_threshold"], lang),
                n=rules["confirm_days"],
            )
        )
    )
    out.append(_timeline(f"bt-{lang}", bt["daily"], bt["episodes"], rules["alarm_threshold"], lang))

    out.append(f"<h3>{_e(t('tr.bt.latency', lang))}</h3>")
    out.append(
        _note(
            t(
                "tr.bt.latency_help",
                lang,
                dd=_pct(-rules["drawdown_threshold"], lang),
                q=int(rules["vol_quantile"] * 100),
                lb=rules["lookback_days"],
                win=rules["detection_window_days"],
            )
        )
    )
    out.append(_latency_chart(bt["episodes"], rules, targets["max_median_latency_days"], lang))
    out.append(_table(_episode_headers(lang), _episode_rows(bt["episodes"], lang)))

    out.append(f"<h3>{_e(t('tr.bt.alarms', lang))}</h3>")
    out.append(_note(t("tr.bt.alarms_help", lang, n=m["n_alarms"], f=m["n_false_alarms"], lb=rules["lookback_days"])))
    table = _alarm_table(bt["alarms"], lang)
    out.append(f"<details><summary>{_e(t('tr.bt.show_alarms', lang, n=m['n_alarms']))}</summary>{table}</details>")

    out.append(f"<h3>{_e(t('tr.bt.reliability', lang))}</h3>")
    out.append(f'<p class="small muted">{_e(t("tr.bt.reliability_help", lang, h=rules["calibration_horizon_days"]))}</p>')
    rows = [
        [
            _e(f"{_pct(r['low'], lang)} – {_pct(r['high'], lang)}"),
            _e(_pct(r["predicted"], lang, 1)),
            _e(_pct(r["observed"], lang, 1)),
            _e(r["days"]),
        ]
        for r in bt["reliability"]
    ]
    headers = [
        (t("tr.col.bin", lang), False),
        (t("tr.col.predicted", lang), True),
        (t("tr.col.observed", lang), True),
        (t("tr.col.days", lang), True),
    ]
    out.append(_table(headers, rows))

    out.append(f"<h3>{_e(t('tr.bt.identity', lang))}</h3>")
    ident = [
        (t("tr.id.file", lang), f'<a href="{_e(bt_meta.get("file", ""))}">{_e(bt_meta.get("file", "–"))}</a>'),
        ("SHA-256", f"<code>{_e(bt_meta.get('sha256', '–'))}</code>"),
        ("OpenTimestamps", _e(t(f"tr.ots.{bt_meta.get('ots', 'missing')}", lang))),
        (t("tr.id.generated", lang), _e(bt["generated_at"].replace("T", " ").replace("+00:00", " UTC"))),
        (
            t("tr.id.code", lang),
            f'<a href="{_e(repo)}/commit/{_e(bt["code_version"])}"><code>{_e(bt["code_version"])}</code></a>',
        ),
        (t("tr.id.data", lang), _e(bt["data_provider"])),
        (t("tr.id.version", lang), _e(bt.get("model_version") or "–")),
        (t("tr.id.model", lang), _e(f"{bt['model']} ({', '.join(bt.get('stress_sources') or [])}; {bt['combination']})")),
        (t("tr.id.config", lang), f"<code>{_e(bt['config_sha256'][:16])}…</code>"),
        (t("tr.id.rule", lang), f"<code>{_e(bt['episode_rule_sha256'][:16])}…</code>"),
    ]
    out.append(
        _table([("", False), ("", False)], [[_e(k), v] for k, v in ident]).replace(
            "<thead><tr><th></th><th></th></tr></thead>", ""
        )
    )
    return "".join(out)


def version_changes(live: LiveRecord) -> list[dict]:
    """Days the published model changed: the first day of each new settings fingerprint in the live record."""
    changes, previous = [], None
    for e in live.entries:
        sha = e.get("config_sha256")
        if sha is None:
            continue  # published before days carried their fingerprint
        if previous is not None and sha != previous["config_sha256"]:
            changes.append(
                {"date": e["date"], "from": previous.get("model_version"), "to": e.get("model_version"), "config_sha256": sha}
            )
        previous = e
    return changes


def _versions_section(versions: list[dict], current: str | None, live: LiveRecord, repo: str, lang: str) -> str:
    """Every model configuration ever recorded, and the days the published one changed."""
    if not versions and not version_changes(live):
        return ""
    out = [f"<h3>{_e(t('tr.ver.title', lang))}</h3>", _note(t("tr.ver.help", lang, doc=f"{repo}/blob/main/docs/TRACK_RECORD.md"))]
    for change in version_changes(live):
        text = t("tr.ver.changed", lang, date=_date(change["date"], lang), old=change["from"] or "–", new=change["to"] or "–")
        out.append(f'<div class="notice">{_e(text)}</div>')
    rows = []
    for v in versions:
        m, period = v.get("metrics") or {}, v.get("period") or {}
        mark = f' <span class="badge">{_e(t("tr.ver.current", lang))}</span>' if v["config_sha256"] == current else ""
        rows.append(
            [
                _e(v.get("model_version") or "–") + mark,
                f"<code>{_e((v.get('config_sha256') or '')[:12])}</code>",
                _e(_date((v.get("generated_at") or "")[:10] or None, lang)),
                _e(f"{_date(period.get('start'), lang)} – {_date(period.get('end'), lang)}"),
                _e(f"{m.get('detected', '–')} / {m.get('n_episodes', '–')}"),
                _e(_num(m.get("false_positives_per_year"), lang)),
                _e(_num(m.get("brier"), lang, 3)),
                f'<a href="{_e(v["file"])}">json</a>',
            ]
        )
    headers = [
        (t("tr.col.version", lang), False),
        (t("tr.id.config", lang), False),
        (t("tr.id.generated", lang), False),
        (t("tr.ver.period", lang), False),
        (t("tr.bt.detected", lang), True),
        (t("tr.bt.fp", lang), True),
        ("Brier", True),
        (t("tr.col.files", lang), False),
    ]
    out.append(_table(headers, rows))
    return "".join(out)


def _method(settings: dict, repo: str, lang: str) -> str:
    cfg = settings["validation"]
    return t(
        "tr.method.text",
        lang,
        repo=repo,
        dd=fmt_pct(-cfg["episodes"]["drawdown_threshold"], lang),
        q=int(cfg["episodes"]["vol_quantile"] * 100),
        thr=fmt_pct(cfg["stress_probability_threshold"], lang),
        n=cfg["confirm_days"],
    )


def render(
    live: LiveRecord,
    score: dict,
    bt: dict | None,
    bt_meta: dict,
    settings: dict,
    lang: str,
    switch: bool = True,
    versions: list[dict] | None = None,
    theme: str | None = None,
) -> str:
    """The whole page in `lang` (fr or en). `switch`: link to the other language's page (not inside the app).
    `theme`: "light" or "dark" to force it (the app); None follows the reader's system.

    `versions`: every backtest record (list_backtests), shown with the days the published model changed.
    """
    repo = settings["publish"].get("repository_url", "").rstrip("/")
    other = "fr" if lang == "en" else "en"
    body = [
        '<header><div class="top">'
        f"<h1>{_e(t('tr.title', lang))}</h1>"
        + (f'<a href="{LANGS[other]}" hreflang="{other}">{_e(t("tr.lang_switch", lang))}</a>' if switch else "")
        + "</div>"
        f'<p class="muted">{_e(t("tr.subtitle", lang))}</p>'
        f'<p class="small muted">{_e(t("disclaimer", lang))} {_e(t("tr.no_signal", lang))}</p></header>',
        _live_section(live, score, settings["validation"]["stress_probability_threshold"], lang),
        _verify_section(live, lang),
        _backtest_section(bt, bt_meta, repo, lang),
        _versions_section(versions or [], bt["config_sha256"] if bt else None, live, repo, lang),
        f'<h2>{_e(t("tr.method.title", lang))}</h2><div class="card">{_method(settings, repo, lang)}</div>',
        f"<footer>{t('tr.footer', lang, repo=repo)}</footer>",
    ]
    forced = f' data-theme="{theme}"' if theme in ("light", "dark") else ""
    return (
        f'<!doctype html><html lang="{lang}"{forced}><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_e(t('tr.page_title', lang))}</title>"
        f'<meta name="description" content="{_e(t("tr.subtitle", lang))}">'
        f"<style>{CSS}</style></head><body><main>{''.join(body)}</main><script>{SCRIPT}</script></body></html>\n"
    )


def write_pages(
    folder: Path,
    live: LiveRecord,
    score: dict,
    bt: dict | None,
    bt_meta: dict,
    settings: dict,
    versions: list[dict] | None = None,
) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for lang, name in LANGS.items():
        path = folder / name
        path.write_text(render(live, score, bt, bt_meta, settings, lang, versions=versions), encoding="utf-8")
        paths.append(path)
    return paths


def _score(pipeline, live: LiveRecord) -> dict:
    """Live episodes and alarms, scored on real market data only: simulated episodes would mean nothing."""
    if not pipeline.provider.is_live:
        return {"episodes": [], "alarms": [], "missing_days": 0, "last_market_day": None, "unscored": True}
    return live_scorecard(live, pipeline.episodes, pipeline.scores.index, pipeline.settings)


def _meta(path: Path, base: Path) -> dict:
    return {
        "file": path.relative_to(base).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "ots": ots_status(path),
    }


def build_site(pipeline, records_dir: Path, out_dir: Path | None = None) -> dict:
    """Write the backtest record if this configuration has none yet, then the pages (index.html, fr.html).

    `records_dir`: the official track record (read only, except for the one-time backtest record).
    `out_dir`: where to write; another folder makes a preview that leaves the track record untouched.
    """
    out_dir = out_dir or records_dir
    path, bt, written = record_backtest(pipeline, records_dir, out_dir)
    base = out_dir if path.is_relative_to(out_dir) else records_dir
    live = read_live(records_dir)
    score = _score(pipeline, live)
    versions = _versions(records_dir, out_dir)
    pages = write_pages(out_dir, live, score, bt, _meta(path, base), pipeline.settings, versions)
    return {"backtest": path, "backtest_written": written, "pages": pages, "live": live, "score": score}


def page_html(pipeline, records_dir: Path, lang: str, theme: str | None = None) -> str:
    """The page for the app, written nowhere: the recorded backtest of this configuration, or one computed now."""
    found = find_backtest(records_dir, pipeline.settings)
    if found:
        bt, meta = found[1], _meta(found[0], records_dir)
    else:
        bt, meta = backtest_record(pipeline), {"file": None, "sha256": None, "ots": "missing"}
    live = read_live(records_dir)
    versions = _versions(records_dir)
    return render(live, _score(pipeline, live), bt, meta, pipeline.settings, lang, switch=False, versions=versions, theme=theme)


def _versions(records_dir: Path, out_dir: Path | None = None) -> list[dict]:
    """Backtest records of the track record, plus those of a preview folder."""
    found = {v["config_sha256"]: v for v in list_backtests(records_dir)}
    if out_dir is not None and out_dir.resolve() != records_dir.resolve():
        for v in list_backtests(out_dir):
            found.setdefault(v["config_sha256"], v)
    return sorted(found.values(), key=lambda v: v["generated_at"] or "")
