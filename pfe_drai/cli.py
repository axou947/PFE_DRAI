"""Command line: python -m pfe_drai <command>.

status     current regime and probabilities
backtest   walk-forward metrics for every model
report     committee note (md, html or pdf)
publish    write today's track record entry (real data only)
episodes   list the stress episodes dated by the frozen rule
app        start the Streamlit dashboard
api        start the FastAPI server
"""

import argparse
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
    from .models import available_models

    p = _pipeline(args)
    models = [args.model] if args.model else available_models()
    print(f"{'model':<8} {'episodes':>9} {'detected':>9} {'median lat.':>12} {'FP/yr':>7} {'Brier':>7} {'acc.':>6}")
    for m in models:
        r = p.evaluate(m)
        acc = r.get("accuracy_truth", float("nan"))
        print(
            f"{m:<8} {r['n_episodes']:>9} {r['detected']:>9} {r['median_latency']:>12.1f} "
            f"{r['false_positives_per_year']:>7.2f} {r['brier_stress']:>7.3f} {acc:>6.2f}"
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


def cmd_app(args):
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ROOT / "app" / "streamlit_app.py")], check=False)


def cmd_api(args):
    subprocess.run([sys.executable, "-m", "uvicorn", "api.main:app", "--reload"], cwd=ROOT, check=False)


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
