"""Command line: python -m pfe_drai <command>.

status     current regime and probabilities
backtest   walk-forward metrics for every model
report     committee note (md, html or pdf)
publish    write today's track record entry (real data only)
episodes   list the stress episodes dated by the frozen rule
states     how the model's states map to the regimes, at every walk-forward refit
holdout    pre-registered holdout of the onset detector, before the out-of-sample period
data       history covered by each series and where the backtest starts
app        start the Streamlit dashboard
api        start the FastAPI server
"""

import argparse
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
    return Pipeline(load_settings(args.config, overrides))


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
    from .models.combined import combine
    from .validation import evaluate

    p = _pipeline(args)
    models = [args.model] if args.model else available_models()
    results = {m: p.evaluate(m) for m in models}
    sources = p.settings["models"].get("combined", {}).get("stress_sources", ["gbm"])
    if "combined" in models and list(sources) != ["gbm"]:
        # v1 (jump + gbm, docs/DETECTION.md) in the same run, to compare with the configured version.
        v1 = combine(p.probabilities("jump"), p.probabilities("gbm"))
        results["v1"] = evaluate(v1, p.prices["equity"], p.episodes, p.settings, truth=p.truth, rule=p.labels)
    print(
        f"{'model':<8} {'episodes':>9} {'detected':>9} {'median lat.':>12} {'all eps.':>9} "
        f"{'FP/yr':>7} {'alarm':>6} {'switch/yr':>10} {'Brier':>7} {'acc.':>6}"
    )
    for m, r in results.items():
        acc = r.get("accuracy_truth", float("nan"))
        print(
            f"{m:<8} {r['n_episodes']:>9} {r['detected']:>9} {r['median_latency']:>12.1f} {r['median_latency_all']:>9.1f} "
            f"{r['false_positives_per_year']:>7.2f} {r['false_alarm_share']:>6.1%} {r['switches_per_year']:>10.1f} "
            f"{r['brier_stress']:>7.3f} {acc:>6.2f}"
        )
    window = p.settings["validation"]["episodes"]["detection_window_days"]
    print(f"all eps. = median latency over every episode, a missed one counting as {window} days")
    print("alarm = share of calm days (outside episodes) with the stress signal on")
    print(f"combined = jump + stress sources {list(sources)} (models.combined.stress_sources); v1 = jump + gbm")
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

    path = publish(_pipeline(args), args.model)
    print(path or "Already published for the latest market day: nothing to do.")


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


def cmd_data(args):
    p = _pipeline(args)
    print(f"{'series':<12} {'first':<12} {'last':<12} dated by")
    for name, series in p.raw.items():
        dated = "release day (ALFRED)" if name in p.provider.release_dated else "reference period"
        print(f"{name:<12} {series.index.min().date()!s:<12} {series.index.max().date()!s:<12} {dated}")
    index, min_train = p.features.index, p.settings["validation"]["min_train_days"]
    print(f"\nFeatures from {index[0].date()} ({p.provider.name}).")
    if len(index) > min_train:
        print(f"Out-of-sample from {index[min_train].date()} (validation.min_train_days: {min_train}).")


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
    parser.add_argument("--lang", default="fr", choices=["fr", "en"])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in [
        ("status", cmd_status),
        ("backtest", cmd_backtest),
        ("report", cmd_report),
        ("publish", cmd_publish),
        ("episodes", cmd_episodes),
        ("states", cmd_states),
        ("holdout", cmd_holdout),
        ("data", cmd_data),
        ("app", cmd_app),
        ("api", cmd_api),
    ]:
        sp = sub.add_parser(name)
        sp.add_argument("--model", default=None)
        sp.set_defaults(func=func)
        if name == "report":
            sp.add_argument("--format", default="md", choices=["md", "html", "pdf"])
            sp.add_argument("--out")
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
