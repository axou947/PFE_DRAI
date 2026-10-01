"""Command line: python -m pfe_drai <command>.

status     current regime and probabilities
backtest   walk-forward metrics for every model
report     committee note (md, html or pdf)
publish    write today's track record entry (real data only)
track-record  build the public track-record page (track_record/index.html, fr.html); --out for a preview
episodes   list the stress episodes dated by the frozen rule
states     how the model's states map to the regimes, at every walk-forward refit
holdout    pre-registered holdout of the onset detector, before the out-of-sample period
calibration  is P(stress) a probability? v2 against the calibrated version (docs/CALIBRATION.md)
slowdown   is Slowdown a real regime? growth score before/after against an outside reference (docs/SLOWDOWN.md)
data       history covered by each series and where the backtest starts
world      country equity markets: return and market stress state on a date (docs/WORLD.md)
app        start the Streamlit dashboard
api        start the FastAPI server
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .config import ROOT, load_settings
from .i18n import fmt_pct, t


def _pipeline(args):
    from .pipeline import Pipeline

    overrides = {}
    if getattr(args, "provider", None):
        overrides = {"data": {"provider": args.provider}}
    return Pipeline(load_settings(args.config, overrides, getattr(args, "region", None)))


def cmd_status(args):
    p = _pipeline(args)
    state = p.state(args.model)
    print(f"{t('dash.current_regime', args.lang)} ({state.date.date()}): {t(f'regime.{state.regime}', args.lang)}")
    for regime, prob in state.probabilities.items():
        print(f"  {t(f'regime.{regime}', args.lang):<28} {fmt_pct(prob, args.lang):>6}")
    if not state.is_live_data:
        print(f"\n{t('app.synthetic_warning', args.lang)}")


def cmd_backtest(args):
    import pandas as pd

    from .models import available_models
    from .models.combined import combination, combine
    from .validation import evaluate

    p = _pipeline(args)
    models = [args.model] if args.model else available_models()
    results = {m: p.evaluate(m) for m in models}
    sources = p.settings["models"].get("combined", {}).get("stress_sources", ["gbm"])
    calibrated = combination(p.settings) == "calibrated"
    if "combined" in models:
        parts = [p.probabilities(name) for name in ("jump", *sources)]
        if calibrated:
            # v2 as published (P(stress) = detector score) in the same run: same alarm, raw probability.
            results["v2"] = evaluate(combine(*parts), p.prices["equity"], p.episodes, p.settings, truth=p.truth, rule=p.labels)
        if list(sources) != ["gbm"]:
            # v1 (jump + gbm, docs/DETECTION.md) in the same run, to compare with the configured version.
            v1 = combine(p.probabilities("jump"), p.probabilities("gbm"))
            results["v1"] = evaluate(v1, p.prices["equity"], p.episodes, p.settings, truth=p.truth, rule=p.labels)
    print(
        f"{'model':<8} {'episodes':>9} {'detected':>9} {'median lat.':>12} {'all eps.':>9} "
        f"{'FP/yr':>7} {'alarm':>6} {'switch/yr':>10} {'Brier':>7} {'ECE':>6} {'logloss':>8} {'acc.':>6}"
    )
    for m, r in results.items():
        acc = r.get("accuracy_truth", float("nan"))
        print(
            f"{m:<8} {r['n_episodes']:>9} {r['detected']:>9} {r['median_latency']:>12.1f} {r['median_latency_all']:>9.1f} "
            f"{r['false_positives_per_year']:>7.2f} {r['false_alarm_share']:>6.1%} {r['switches_per_year']:>10.1f} "
            f"{r['brier']:>7.3f} {r['ece']:>6.3f} {r['log_loss']:>8.3f} {acc:>6.2f}"
        )
    window = p.settings["validation"]["episodes"]["detection_window_days"]
    horizon = p.settings["validation"]["calibration"]["target_horizon_days"]
    print(f"all eps. = median latency over every episode, a missed one counting as {window} days")
    print("alarm = share of calm days (outside episodes) with the stress signal on")
    print(
        f"Brier, ECE, logloss = P(stress) against the stress event (inside an episode or one starts within {horizon} days), "
        "lower is better (docs/CALIBRATION.md)"
    )
    shown_combination = "calibrated P(stress)" if calibrated else "P(stress) = detector score"
    print(f"combined = jump + stress sources {list(sources)}, {shown_combination}; v1 = jump + gbm")
    if calibrated:
        print("v2 = same models and same alarm, P(stress) = detector score (highest source, not calibrated)")
    # Every latency of the default (or chosen) model, missed episodes included.
    shown = args.model or p.settings["models"]["default"]
    columns = [shown] + (["v1"] if "v1" in results else [])
    print(f"\nLatency per episode ({', '.join(columns)}; business days; negative = signal already on):")
    tables = [results[c]["episodes"] for c in columns]
    for i, row in tables[0].iterrows():
        cells = []
        for table in tables:
            latency = table.loc[i, "latency_days"]
            cells.append("missed" if pd.isna(latency) else f"{int(latency):+d}")
        print(
            f"  {row['start'].date()!s:<12} {row['trigger']:<11} {row['max_drawdown']:>7.1%} "
            + " ".join(f"{c:>7}" for c in cells)
        )


def cmd_calibration(args):
    from .models.combined import combine
    from .validation.calibration import calibration_report

    p = _pipeline(args)
    sources = p.settings["models"]["combined"]["stress_sources"]
    raw = combine(*(p.probabilities(name) for name in ("jump", *sources)))["stress"]
    cal = p.calibrated()
    horizon = p.settings["validation"]["calibration"]["target_horizon_days"]
    data = "real" if p.provider.is_live else "SIMULATED"
    print(
        f"Calibration of P(stress) ({data} data, provider {p.provider.name}), out-of-sample from {cal.stress.index[0].date()} "
        f"to {cal.stress.index[-1].date()}. Event: inside an episode of the frozen rule, or one starts within {horizon} "
        "business days. See docs/CALIBRATION.md."
    )
    reports = {"v2 (detector score)": calibration_report(raw, p.episodes, p.settings)}
    reports["calibrated"] = calibration_report(cal.stress, p.episodes, p.settings)
    print(f"\n{'P(stress)':<22} {'days':>6} {'Brier':>7} {'ECE':>6} {'logloss':>8} {'skill':>6} {'mean P':>7} {'observed':>9}")
    for name, r in reports.items():
        print(
            f"{name:<22} {r['n_days']:>6} {r['brier']:>7.3f} {r['ece']:>6.3f} {r['log_loss']:>8.3f} {r['brier_skill']:>6.2f} "
            f"{r['mean_p']:>7.1%} {r['base_rate']:>9.1%}"
        )
    print("(lower is better for Brier, ECE and logloss; skill = 1 - Brier / Brier of always saying the observed frequency)")
    for name, r in reports.items():
        print(f"\nReliability, {name}: days grouped by predicted P(stress)")
        print(f"  {'bin':<11} {'days':>6} {'predicted':>10} {'observed':>9}")
        for row in r["reliability"].itertuples():
            print(f"  {row.low:>4.0%}-{row.high:<5.0%} {row.count:>6} {row.predicted:>10.1%} {row.observed:>9.1%}")
    fits = cal.fits
    weights = [c for c in fits.columns if c not in ("first_day", "intercept", "train_days", "event_days")]
    print(f"\nCalibrator at each refit (P = sigmoid(intercept + weight x logit(input)); inputs: {', '.join(weights)}):")
    print(f"  {'first day':<12} {'train days':>10} {'event days':>10} {'intercept':>10} " + " ".join(f"{w:>8}" for w in weights))
    for row in fits.to_dict("records"):
        head = f"  {row['first_day'].date()!s:<12} {row['train_days']:>10} {row['event_days']:>10}"
        if row["intercept"] != row["intercept"]:
            print(f"{head}   too few event days: P(stress) = detector score")
            continue
        print(f"{head} {row['intercept']:>10.2f} " + " ".join(f"{row[w]:>8.2f}" for w in weights))


def cmd_report(args):
    from .reporting import build_note, to_html, to_markdown, to_pdf

    note = build_note(_pipeline(args), args.lang, args.model)
    out = Path(args.out or f"note-{args.lang}.{args.format}")
    if args.format == "pdf":
        out.write_bytes(to_pdf(note))
    else:
        out.write_text(to_markdown(note) if args.format == "md" else to_html(note), encoding="utf-8")
    print(out)


def cmd_publish(args):
    from .publish import publish
    from .publish.snapshot import NotEnabledError

    try:
        path = publish(_pipeline(args), args.model)
    except NotEnabledError as exc:
        raise SystemExit(str(exc)) from exc
    print(path or "Already published for the latest market day: nothing to do.")


def cmd_track_record(args):
    from .config import resolve
    from .publish import build_site

    p = _pipeline(args)
    records = resolve(p.settings["publish"]["dir"])
    out = Path(args.out).resolve() if args.out else records
    result = build_site(p, records, out)
    live, score = result["live"], result["score"]
    action = "written now" if result["backtest_written"] else "already recorded"
    print(f"Backtest record: {result['backtest']} ({action})")
    bt = json.loads(result["backtest"].read_text(encoding="utf-8"))
    m, period = bt["metrics"], bt["period"]
    print(
        f"  {bt['data_provider']} data, {period['start']} to {period['end']}: detected {m['detected']}/{m['n_episodes']}, "
        f"median latency {m['median_latency']} (all episodes {m['median_latency_all']}), "
        f"{m['false_positives_per_year']:.2f} false alarms/yr, {m['false_alarm_share']:.1%} of calm days in false alarm, "
        f"{m['n_alarms']} alarms ({m['n_false_alarms']} false), Brier {m['brier']:.3f}, ECE {m['ece']:.3f}"
    )
    for ep in bt["episodes"]:
        latency = "missed" if ep["latency_days"] is None else f"{ep['latency_days']:+d}"
        print(f"  {ep['start']}  {ep['trigger']:<11} {ep['max_drawdown']:>7.1%}  {latency:>7}")
    print(f"Live record: {len(live.entries)} day(s) published, hash chain {'intact' if live.chain_ok else 'BROKEN'}")
    for problem in live.problems:
        print(f"  {problem}")
    print(f"Live episodes scored: {len(score['episodes'])}, live alarms: {len(score['alarms'])}")
    for page in result["pages"]:
        print(page)
    if not live.chain_ok:
        sys.exit(1)


def cmd_episodes(args):
    from .validation import rule_fingerprint

    p = _pipeline(args)
    print(f"Episode rule sha256: {rule_fingerprint(p.settings)} (data: {p.provider.name})")
    print(f"{'start':<12} {'end':<12} {'trigger':<11} {'max drawdown':>13}")
    for ep in p.episodes:
        print(f"{ep.start.date()!s:<12} {ep.end.date()!s:<12} {ep.trigger:<11} {ep.max_drawdown:>13.1%}")


def cmd_states(args):
    import statistics

    from .features import DIMENSIONS
    from .regimes import regime_centres

    p = _pipeline(args)
    model = args.model or p.settings["models"]["default"]
    maps = p.state_maps(model)
    if not maps:
        print(f"Model '{model}' predicts the rule regimes directly: it has no states to name.")
        return
    order = p.settings["regimes"]["order"]
    first, table = maps[-1]
    cut = p.scores.index.get_loc(first)
    print(
        f"States of the {p.unsupervised_model(model)} model behind '{model}' ({p.provider.name} data), "
        f"latest fit: trained on {p.scores.index[0].date()} to {p.scores.index[cut - 1].date()}. See docs/REGIMES.md."
    )
    dims = " ".join(f"{d:>9}" for d in DIMENSIONS)
    print(f"\nRegime centres (average training day the rule puts in each regime):\n{'regime':<12} {'days':>5}  {dims}")
    for regime, row in regime_centres(p.scores.iloc[:cut], p.labels.iloc[:cut], p.settings).iterrows():
        print(f"{regime:<12} {int(row['days']):>5}  " + " ".join(f"{row[d]:>+9.2f}" for d in DIMENSIONS))
    shares = " ".join(f"{r[:11]:>11}" for r in order)
    print("\nStates: name = closest regime centre; share = the state's training days in each rule regime.")
    print(f"{'state':<6} {'name':<12} {'dist.':>6} {'days':>5}  {dims}  {shares}")
    for state, row in table.iterrows():
        centre = " ".join(f"{row[d]:>+9.2f}" for d in DIMENSIONS)
        share = " ".join(f"{row[f'share_{r}']:>11.0%}" for r in order)
        print(f"{state:<6} {row['name']:<12} {row['distance']:>6.2f} {row['days']:>5}  {centre}  {share}")
    print("\nEvery refit (first day predicted: state names with the share of their days the rule agrees with):")
    for start, table in maps:
        names = " | ".join(
            f"{row['name']} {row['purity']:.0%}{'*' if row['purity'] < 0.5 else ''}"
            for _, row in table.sort_values("name").iterrows()
        )
        absent = [r for r in order if r not in set(table["name"])]
        print(f"{start.date()!s:<12} {names}" + (f"   no state: {', '.join(absent)}" if absent else ""))
    purity = [row["purity"] for _, table in maps for _, row in table.iterrows() if row["days"]]
    print(
        f"\nAgreement with the rule: median {statistics.median(purity):.0%}, lowest {min(purity):.0%}, over {len(maps)} refits."
    )
    print("* = fewer than half of the state's days are in the regime it is named after: a mixed state.")


def cmd_holdout(args):
    import pandas as pd

    from .validation.holdout import run_holdout

    p = _pipeline(args)
    res = run_holdout(p.settings)
    data = "real" if res.is_live else "SIMULATED"
    print(
        f"Onset detector holdout ({data} data, provider {res.provider}): predictions from {res.first_prediction.date()} "
        f"to {res.last_day.date()}, episodes by the frozen rule."
    )
    print(
        f"\n{'candidate':<26} {'episodes':>9} {'detected':>9} {'median lat.':>12} {'all eps.':>9} "
        f"{'FP/yr':>7} {'alarm':>6} {'Brier':>7}"
    )
    for _, r in res.rows.iterrows():
        print(
            f"{r['candidate']:<26} {r['episodes']:>9} {r['detected']:>9} {r['median_latency']:>12.1f} "
            f"{r['median_latency_all']:>9.1f} {r['fp_per_year']:>7.2f} {r['false_alarm_share']:>6.1%} {r['brier']:>7.3f}"
        )
    print("(all eps. = median latency, a missed episode counting as the window end; alarm = share of calm days in false alarm)")
    print("\nLatency per episode (business days; negative = signal already on; - = missed):")
    names = [c for c in res.latencies.columns if c != "max_drawdown"]
    print(f"{'start':<12} {'max dd':>7}  " + "  ".join(f"{i + 1:>4}" for i in range(len(names))))
    for start, row in res.latencies.iterrows():
        cells = "  ".join(f"{'-' if pd.isna(row[n]) else f'{int(row[n]):+d}':>4}" for n in names)
        print(f"{start.date()!s:<12} {row['max_drawdown']:>7.1%}  {cells}")
    print("  (columns = candidates in the order above)")
    if res.chosen is None:
        print("\nNo candidate meets the false-alarm targets (validation.targets): v2 stops here.")
    else:
        print(f"\nSelected by the pre-registered rule: {res.rows.loc[res.chosen, 'candidate']}")


def cmd_slowdown(args):
    import pandas as pd

    from .config import _deep_merge
    from .validation.slowdown import decide, growth_holdout, slowdown_report

    if args.holdout:
        settings = load_settings(args.config, {"data": {"provider": args.provider}} if args.provider else None)
        res = growth_holdout(settings)
        data = "real" if res["is_live"] else "SIMULATED"
        print(
            f"Growth score holdout ({data} data, provider {res['provider']}), {res['first_day'].date()} to "
            f"{res['last_day'].date()}. Reference: {res['reference']} (below-trend growth on "
            f"{res['reference_share']:.0%} of days). See docs/SLOWDOWN.md."
        )
        print(f"\n{'#':>2} {'candidate':<34} {'days':>5} {'bal. acc.':>10} {'below':>6} {'spells/yr':>10} {'median spell':>13}")
        for _, r in res["rows"].iterrows():
            number = "-" if pd.isna(r["order"]) else int(r["order"]) + 1
            print(
                f"{number:>2} {r['candidate']:<34} {r['days']:>5} {r['balanced_accuracy']:>10.3f} "
                f"{r['below_share']:>6.0%} {r['spells_per_year']:>10.2f} {r['median_spell']:>13.0f}"
            )
        print(
            "(bal. acc. = average of the shares right on below-trend days and on the other days; "
            "below = days under the threshold)"
        )
        if res["chosen"] is None:
            print("\nNo candidate qualifies: the growth score stays as it is.")
        else:
            print(f"\nSelected by the pre-registered rule: {res['rows'].loc[res['chosen'], 'candidate']}")
        return

    p = _pipeline(args)
    model = args.model or p.settings["models"]["default"]

    def variant(name):
        cfg = p.settings["validation"]["slowdown"][name]
        return p.with_settings(_deep_merge(p.settings, {"features": {"growth": cfg["growth"]}, "regimes": {"rule": cfg["rule"]}}))

    # --tested: the pre-registered v2.2 against the published v2.1; otherwise the current settings against v2.1.
    runs = {"before": variant("before"), "after": variant("tested") if args.tested else p}
    p = runs["after"]
    results = {name: {"slowdown": slowdown_report(q, model), "detection": q.evaluate(model)} for name, q in runs.items()}
    reference = results["after"]["slowdown"]["reference"]
    data = "real" if p.provider.is_live else "SIMULATED"
    index = p.probabilities(model).index
    print(
        f"Slowdown regime, before and after ({data} data, provider {p.provider.name}, model {model}), out-of-sample from "
        f"{index[0].date()} to {index[-1].date()}. Reference: {reference or 'none (no below-trend growth series)'}. "
        "See docs/SLOWDOWN.md."
    )
    rows = [
        ("rule: days in Slowdown", "slowdown_share", "{:.1%}"),
        ("rule: Slowdown spells a year", "spells_per_year", "{:.2f}"),
        ("rule: median Slowdown spell (days)", "median_spell", "{:.0f}"),
        ("growth below threshold vs reference (bal. acc.)", "growth_ba", "{:.3f}"),
        ("refits with a state named Slowdown, >= 50% agreement", "state_share", "{:.0%}"),
        ("displayed: days shown as Slowdown", "shown_share", "{:.1%}"),
        ("displayed Slowdown vs reference (bal. acc.)", "shown_ba", "{:.3f}"),
        ("displayed: reference slowdown days found", "shown_recall", "{:.1%}"),
        ("displayed: Slowdown days that are reference slowdown", "shown_precision", "{:.1%}"),
        ("reference: days of below-trend growth", "reference_share", "{:.1%}"),
    ]
    print(f"\n{'':<54} {'before':>9} {'after':>9}")
    for label, key, fmt in rows:
        cells = [results[n]["slowdown"]["summary"][key] for n in ("before", "after")]
        print(f"{label:<54} " + " ".join(f"{'-' if c != c else fmt.format(c):>9}" for c in cells))
    det = [
        ("stress episodes detected", lambda r: f"{r['detected']}/{r['n_episodes']}"),
        ("median latency (days)", lambda r: f"{r['median_latency']:.1f}"),
        ("median latency, all episodes", lambda r: f"{r['median_latency_all']:.1f}"),
        ("false positives a year", lambda r: f"{r['false_positives_per_year']:.2f}"),
        ("calm days in false alarm", lambda r: f"{r['false_alarm_share']:.1%}"),
        ("regime switches a year", lambda r: f"{r['switches_per_year']:.1f}"),
        ("Brier", lambda r: f"{r['brier']:.3f}"),
        ("ECE", lambda r: f"{r['ece']:.3f}"),
    ]
    for label, fmt in det:
        print(f"{label:<54} " + " ".join(f"{fmt(results[n]['detection']):>9}" for n in ("before", "after")))
    lat = [results[n]["detection"]["episodes"].set_index("start")["latency_days"] for n in ("before", "after")]
    print("\nLatency per episode (business days; negative = signal already on):")
    for start in lat[0].index:
        cells = ["missed" if v != v or v is None else f"{int(v):+d}" for v in (lat[0].get(start), lat[1].get(start))]
        print(f"  {start.date()!s:<12} {cells[0]:>7} {cells[1]:>7}")
    states = results["after"]["slowdown"]["states"]
    if len(states):
        print("\nAfter: Slowdown in the jump model at each refit (first day predicted, states named Slowdown, best agreement):")
        for row in states.itertuples():
            best = "-" if row.best_agreement != row.best_agreement else f"{row.best_agreement:.0%}"
            print(f"  {row.first_day.date()!s:<12} {row.slowdown_states:>2} {best:>5}{'' if row.named else '  *'}")
        print("  * = no state named Slowdown with at least half of its days Slowdown by the rule")
    if reference is None:
        print("\nNo reference series for this provider: the decision needs --provider fred.")
        return
    decision = decide(
        *({"slowdown": results[n]["slowdown"]["summary"], "detection": results[n]["detection"]} for n in ("before", "after")),
        p.settings,
    )
    print("\nPre-registered decision (docs/SLOWDOWN.md):")
    for label, ok in decision["checks"].items():
        print(f"  [{'x' if ok else ' '}] {label}")
    verdict = "ADOPT the new growth score" if decision["adopt"] else "KEEP the growth score as it was"
    print(f"Decision: {verdict}.")


def cmd_data(args):
    p = _pipeline(args)
    euro = p.settings.get("region") == "euro"
    lags = p.settings["data"].get("euro", {}).get("series", {})
    print(f"{'series':<14} {'first':<12} {'last':<12} dated by" + ("" if not euro else "  (lag, vintage, licence)"))
    for name, series in p.raw.items():
        if euro:
            spec = lags.get(name, {})
            lag = spec.get("lag_days", spec.get("all", {}).get("lag_days", ""))
            used = p.provider.used_filters.get(name)
            dated = f"release day, lag {lag} d  |  {spec.get('vintage')}  |  {spec.get('licence')}"
            if used:
                dated += f"  |  eurostat {spec['dataset']} {used}"
        else:
            dated = "release day (ALFRED)" if name in p.provider.release_dated else "reference period"
        print(f"{name:<14} {series.index.min().date()!s:<12} {series.index.max().date()!s:<12} {dated}")
    index, min_train = p.features.index, p.settings["validation"]["min_train_days"]
    print(f"\nFeatures from {index[0].date()} ({p.provider.name}).")
    if len(index) > min_train:
        print(f"Out-of-sample from {index[min_train].date()} (validation.min_train_days: {min_train}).")


def cmd_world(args):
    import pandas as pd

    from .world import breadth, fetch_prices, indicators, load_markets, snapshot

    settings = load_settings(args.config, {"data": {"provider": args.provider}} if args.provider else None)
    prices, errors = fetch_prices(settings)
    ind = indicators(prices, settings)
    day = prices.index[prices.index.searchsorted(pd.Timestamp(args.date or prices.index[-1]), side="right") - 1]
    markets = load_markets(settings)
    snap = snapshot(prices, ind, markets, day, args.horizon, settings["world"]["stale_days"])
    data = "SIMULATED" if settings["data"]["provider"] == "synthetic" else "country ETFs, USD"
    print(f"World markets on {day.date()} ({data}; provider {settings['data']['provider']}). See docs/WORLD.md.")
    print(f"\n{'market':<16} {'etf':<5} {'state':<9} {args.horizon:>7} {'vol 21d':>8} {'vol rank':>9} {'drawdown':>9}  since")
    names = {m.id: m.name["en"] for m in markets}
    for i, r in snap.iterrows():
        since = r["since"].date() if r["since"] is not None else "-"
        print(
            f"{names[i]:<16} {r['ticker']:<5} {r['state'] or 'no data':<9} {r['return']:>7.1%} {r['vol']:>8.1%} "
            f"{r['vol_pct']:>9.0%} {r['drawdown']:>9.1%}  {since}"
        )
    b = breadth(ind["state"]).loc[:day].iloc[-1]
    print(f"\nIn stress: {b['stress']:.0%} of {int(b['markets'])} markets; elevated: {b['elevated']:.0%}.")
    for market, error in errors.items():
        print(f"Not loaded: {market} ({error})")


def cmd_app(args):
    env = {**os.environ, **({"PFE_DRAI_PROVIDER": args.provider} if args.provider else {})}
    try:
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(ROOT / "app" / "streamlit_app.py")], check=False, env=env)
    except KeyboardInterrupt:  # Ctrl+C stops the app: no traceback
        pass


def cmd_api(args):
    try:
        subprocess.run([sys.executable, "-m", "uvicorn", "api.main:app", "--reload"], cwd=ROOT, check=False)
    except KeyboardInterrupt:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pfe_drai", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="path to a settings.yaml")
    parser.add_argument("--provider", help="override data.provider (synthetic, csv, fred, tiingo, yahoo)")
    parser.add_argument("--region", default="us", help="us (default, the published model) or euro (experimental, docs/EURO.md)")
    parser.add_argument("--lang", default="fr", choices=["fr", "en"])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in [
        ("status", cmd_status),
        ("backtest", cmd_backtest),
        ("report", cmd_report),
        ("publish", cmd_publish),
        ("track-record", cmd_track_record),
        ("episodes", cmd_episodes),
        ("states", cmd_states),
        ("holdout", cmd_holdout),
        ("calibration", cmd_calibration),
        ("slowdown", cmd_slowdown),
        ("data", cmd_data),
        ("world", cmd_world),
        ("app", cmd_app),
        ("api", cmd_api),
    ]:
        sp = sub.add_parser(name)
        sp.add_argument("--model", default=None)
        sp.set_defaults(func=func)
        if name == "report":
            sp.add_argument("--format", default="md", choices=["md", "html", "pdf"])
            sp.add_argument("--out")
        if name == "track-record":
            sp.add_argument("--out", help="write the pages (and a new backtest record) to this folder instead: a preview")
        if name == "slowdown":
            sp.add_argument("--holdout", action="store_true", help="growth score candidates on 1999-2009 (no model fitted)")
            sp.add_argument(
                "--tested", action="store_true", help="run the pre-registered v2.2 (the holdout's choice) as the 'after'"
            )
        if name == "world":
            sp.add_argument("--date", help="YYYY-MM-DD (default: latest close)")
            sp.add_argument("--horizon", default="1M", choices=["1D", "1W", "1M", "3M", "YTD", "1Y"])
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
