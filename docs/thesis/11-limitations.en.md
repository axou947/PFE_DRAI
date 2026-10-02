# Limitations

- **Few episodes.** The out-of-sample backtest has {{backtest.current.metrics.n_episodes}} episodes and the earlier holdout fewer still. A median moves a lot with one episode, and days inside an episode are correlated, so the number of independent observations is much smaller than the number of days.
- **The episodes are seen.** The detector, its inputs and the calibration were chosen with these episodes known. The pre-registration limits what was chosen after the fact; it does not make the backtest a blind test. Only the live record can be one.
- **The detector reads what the rule reads.** Part of its speed comes from watching the drawdown and volatility that date the episodes. A delay near zero says "on the day the rule dates the start", not "ahead of the market".
- **False alarms are not negligible.** The current record has {{backtest.current.metrics.false_positives_per_year|2}} false alarms per year against a limit of {{backtest.current.targets.max_false_positives_per_year|1}}: a risk committee should expect about one a year.
- **The regimes are defined by a rule.** The labels the models learn come from a rule with thresholds set by hand, so agreement with the rule is not agreement with an independent truth. Only Slowdown was checked against an outside measure, and the result is weak (Chapter 7).
- **Slowdown is the weakest regime.** What the application displays as Slowdown matches the outside reference no better than chance.
- **Calibration is noisy at the top.** The highest bins of the reliability table rest on a handful of crises, and the calibrated probability is cautious above 30%.
- **Point-in-time is not perfect.** A year-on-year change compares two first releases, and the euro-area series are not available as first releases at all.
- **One region validated.** The US model is the only one that passed its pre-registered rule. The euro version failed it, and the world-markets view is descriptive.
- **Data licences.** Market prices cannot be redistributed, so the repository holds model outputs and not the data behind them. Rebuilding the records needs free API keys (FRED and Tiingo) and the licence terms of each source.
- **No strategy was evaluated.** The project measures the detection of stress and the quality of a probability. It makes no claim about portfolio performance, transaction costs or the use of the signal in an investment process, and it does not forecast crises or give advice.
- **The live record is short.** It is the proof the project depends on, and it will take years of business days to say anything on its own.
