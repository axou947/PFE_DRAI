"""Regime outlook from history: how long the current regime's spells have lasted before, how long this one
has run, and which regime came next when such a spell ended.

Base rates only, never a forecast (docs/OUTLOOK.md). Read-only: the spells are runs of the regime the app
displays, i.e. the out-of-sample walk-forward path of the model (the same path as the dashboard timeline),
up to the date shown. Nothing is fitted, published or backtested here.

- A spell is a run of the displayed regime. A run shorter than `MIN_DAYS` market days is a blip: it is put
  back into the regime before it, so a two-day flicker does not split a long spell in two or count as a
  "next regime". The run on the date shown is never folded, even when it is younger than that.
- Lengths are counted in market days (days of the data) and only on complete spells: the first spell started
  before the history (its length is unknown) and the current one has not ended.
- Next-regime shares count every spell that ended, the first one included.

`outlook()` returns plain JSON data; `sentences()` turns it into FR/EN text from i18n templates.
"""

import pandas as pd

from .i18n import fmt_date, fmt_pct, t

MIN_DAYS = 5  # market days: a run shorter than a week is a blip, not a spell
FEW = 5  # fewer complete spells than this: the shares rest on too little to read much into


def raw_runs(path: pd.Series) -> pd.DataFrame:
    """Unbroken runs of the same value: regime, first and last day, length in days of the series."""
    block = (path != path.shift()).cumsum()
    runs = path.groupby(block).agg(regime="first", days="size")
    runs["start"] = path.index.to_series().groupby(block.values).first().values
    runs["end"] = path.index.to_series().groupby(block.values).last().values
    return runs.reset_index(drop=True)[["regime", "start", "end", "days"]]


def spells(path: pd.Series, min_days: int = MIN_DAYS) -> pd.DataFrame:
    """Spells of the path: blips folded into the regime before them, then equal neighbours merged.

    Columns: regime, start, end, days, blips (runs folded into the spell), next (regime of the following
    spell, None for the last), complete (False for the first spell, cut by the start of the history, and the
    last, still running).
    """
    runs = raw_runs(path)
    if runs.empty:
        return pd.DataFrame(columns=["regime", "start", "end", "days", "blips", "next", "complete"])
    regime = runs["regime"].tolist()
    blip = [False] * len(runs)
    for i in range(1, len(runs) - 1):  # neither the first (its length is unknown) nor the running one
        if runs.at[i, "days"] < min_days:
            regime[i], blip[i] = regime[i - 1], True
    runs = runs.assign(regime=regime, blip=blip)
    group = (runs["regime"] != runs["regime"].shift()).cumsum()
    out = runs.groupby(group).agg(
        regime=("regime", "first"), start=("start", "first"), end=("end", "last"), days=("days", "sum"), blips=("blip", "sum")
    )
    out = out.reset_index(drop=True)
    out["blips"] = out["blips"].astype(int)
    out["days"] = out["days"].astype(int)
    out["next"] = pd.Series(out["regime"].tolist()[1:] + [None], index=out.index, dtype=object)
    out["complete"] = True
    out.loc[out.index[0], "complete"] = False
    out.loc[out.index[-1], "complete"] = False
    return out


def _summary(days: pd.Series) -> dict:
    if days.empty:
        return {"spells": 0, "median": None, "q25": None, "q75": None, "shortest": None, "longest": None}
    return {
        "spells": int(len(days)),
        "median": float(days.median()),
        "q25": float(days.quantile(0.25)),
        "q75": float(days.quantile(0.75)),
        "shortest": int(days.min()),
        "longest": int(days.max()),
    }


def outlook(pipeline, model: str | None = None, date=None, min_days: int = MIN_DAYS) -> dict:
    """Base rates for the regime displayed on `date` (default: latest), from the displayed path up to that day."""
    model = model or pipeline.settings["models"]["default"]
    path = pipeline.regimes(model)
    day = path.index[-1] if date is None else path.index[path.index.searchsorted(pd.Timestamp(date), side="right") - 1]
    path = path.loc[:day]
    order = pipeline.settings["regimes"]["order"]
    table = spells(path, min_days)
    now = table.iloc[-1]
    regime = str(now["regime"])
    unbroken = raw_runs(path).iloc[-1]
    done = table[table["complete"]]
    ended = table[table["next"].notna()]

    durations = {r: _summary(done.loc[done["regime"] == r, "days"]) for r in order}
    following = {}
    for r in order:
        nxt = ended.loc[ended["regime"] == r, "next"]
        to = {}
        for o in order:
            if o != r:
                to[o] = {"count": int((nxt == o).sum()), "share": float((nxt == o).mean()) if len(nxt) else None}
        following[r] = {"ended": int(len(nxt)), "to": to}

    age = int(now["days"])
    past = done.loc[done["regime"] == regime, "days"]
    longer = past[past > age]
    reached = {
        "spells": int(len(past)),
        "longer": int(len(longer)),
        "share_longer": float(len(longer) / len(past)) if len(past) else None,
        "median_total": float(longer.median()) if len(longer) else None,
        "median_more": float((longer - age).median()) if len(longer) else None,
    }
    switches = len(table) - 1
    years = (path.index[-1] - path.index[0]).days / 365.25
    return {
        "date": day.date().isoformat(),
        "model": model,
        "regime": regime,
        "min_days": min_days,
        "period": {
            "start": path.index[0].date().isoformat(),
            "end": day.date().isoformat(),
            "market_days": int(len(path)),
            "years": round(years, 1),
            "spells": int(len(table)),
            "complete_spells": int(len(done)),
            "switches_per_year": round(switches / years, 2) if years > 0 else None,
        },
        "current": {
            "start": now["start"].date().isoformat(),
            "market_days": age,
            "calendar_days": int((day - now["start"]).days) + 1,
            "unbroken_start": unbroken["start"].date().isoformat(),
            "unbroken_days": int(unbroken["days"]),
            "blips": int(now["blips"]),
            "new": bool(age < min_days),
            "from_history_start": not bool(len(table) > 1),
        },
        "duration": durations,
        "reached": reached,
        "next": following,
        "few": durations[regime]["spells"] < FEW,
        "spells": [
            {
                "regime": str(row.regime),
                "start": row.start.date().isoformat(),
                "end": row.end.date().isoformat(),
                "market_days": int(row.days),
                "next": row.next,
                "complete": bool(row.complete),
            }
            for row in table.itertuples()
        ],
    }


def _days(value: float) -> str:
    return f"{round(value):.0f}"  # half a market day is not worth showing


def next_items(out: dict, lang: str, regime: str | None = None) -> list[str]:
    """'Expansion 60% (6)' for each regime that followed `regime`, most frequent first."""
    info = out["next"][regime or out["regime"]]
    rows = sorted(info["to"].items(), key=lambda kv: -kv[1]["count"])
    return [
        t("outlook.next_item", lang, regime=t(f"regime.{r}", lang), share=fmt_pct(v["share"], lang), count=v["count"])
        for r, v in rows
        if v["count"]
    ]


def sentences(out: dict, lang: str = "fr") -> dict:
    """The outlook in plain sentences (template text, nothing generated)."""
    regime = t(f"regime.{out['regime']}", lang)
    cur, dur, reached, period = out["current"], out["duration"][out["regime"]], out["reached"], out["period"]
    since = fmt_date(cur["start"], lang)
    if cur["from_history_start"]:
        so_far = t("outlook.so_far_start", lang, regime=regime, days=cur["market_days"], start=since)
    else:
        so_far = t("outlook.so_far", lang, regime=regime, days=cur["market_days"], calendar=cur["calendar_days"], start=since)
    if cur["blips"]:
        so_far += " " + t(
            "outlook.blips", lang, n=cur["blips"], unbroken=cur["unbroken_days"], start=fmt_date(cur["unbroken_start"], lang)
        )
    if cur["new"]:
        so_far += " " + t("outlook.new", lang, min_days=out["min_days"])

    if dur["spells"] == 0:
        usual = t("outlook.usual_none", lang, regime=regime)
        reach = ""
    else:
        usual = t(
            "outlook.usual",
            lang,
            regime=regime,
            n=dur["spells"],
            median=_days(dur["median"]),
            q25=_days(dur["q25"]),
            q75=_days(dur["q75"]),
            shortest=dur["shortest"],
            longest=dur["longest"],
        )
        if reached["longer"] == 0:
            reach = t("outlook.reached_none", lang, n=reached["spells"], days=cur["market_days"])
        elif reached["longer"] == reached["spells"]:
            more = _days(reached["median_more"])
            reach = t("outlook.reached_all", lang, n=reached["spells"], days=cur["market_days"], more=more)
        else:
            reach = t(
                "outlook.reached",
                lang,
                k=reached["longer"],
                n=reached["spells"],
                days=cur["market_days"],
                more=_days(reached["median_more"]),
            )

    ended = out["next"][out["regime"]]["ended"]
    items = next_items(out, lang)
    if ended:
        nxt = t("outlook.next", lang, regime=regime, n=ended, items=", ".join(items))
    else:
        nxt = t("outlook.next_none", lang, regime=regime)
    notes = []
    if out["few"]:
        notes.append(t("outlook.few", lang, n=dur["spells"]))
    if out["regime"] == "slowdown":
        notes.append(t("outlook.slowdown", lang))
    caveat = t(
        "outlook.caveat",
        lang,
        start=fmt_date(period["start"], lang),
        end=fmt_date(period["end"], lang),
        model=t(f"model.{out['model']}", lang),
        spells=period["spells"],
        min_days=out["min_days"],
    )
    return {"so_far": so_far, "usual": usual, "reached": reach, "next": nxt, "notes": notes, "caveat": caveat}


__all__ = ["MIN_DAYS", "next_items", "outlook", "raw_runs", "sentences", "spells"]
