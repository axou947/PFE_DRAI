# The euro area: a pre-registered failure

## The question

Does the method transfer to another region? The euro-area version (`--region euro`, an overlay of the settings) keeps the pipeline, the features, the models, the calibration and the episode rule of the US model unchanged and only replaces the inputs: the euro-area equity ETF (EZU, priced in dollars) from Tiingo, the ECB's government yield curves, the harmonised consumer price index from the ECB and industrial production and unemployment from Eurostat. The US model, its daily publication and its settings fingerprint are not touched by this work.

The pre-registration fixed the data, the regime thresholds, the selection procedure and **seven numeric conditions** before any real euro run. If all held, the euro view could be published daily. If one failed, the result would be published and the euro view would stay labelled experimental.

## Weaknesses stated up front

The data were weaker than the US ones, and the pre-registration said so before the run:

- neither the ECB nor Eurostat exposes first releases, so the euro series are dated by a conservative release lag but industrial production and unemployment are revised, and the backtest sees the revised values (the US model reads first releases);
- the ETF is priced in dollars, so its price mixes euro-zone equities and the euro-dollar rate and can date an episode that the euro-area market did not have;
- the euro "VIX" is realised and not implied volatility, there is no daily breakeven inflation (the inflation dimension is thinner) and credit is a sovereign proxy, not corporate credit;
- the history is short, so the backtest has fewer episodes and the 2010 to 2012 sovereign crisis is only partly inside it.

## Results

{{quote:EURO.md#Results > Step 2: the real backtest}}

{{quote:EURO.md#Results > Decision rule applied}}

## Reading the failure

Six of the seven conditions held. The euro alarm detects stress quickly: {{cell:EURO.md#Results > Step 2: the real backtest | combined (the model) | detected}} of {{cell:EURO.md#Results > Step 2: the real backtest | combined (the model) | episodes}} episodes detected, a median delay of {{cell:EURO.md#Results > Step 2: the real backtest | combined (the model) | median latency}} business days and {{cell:EURO.md#Results > Step 2: the real backtest | combined (the model) | FP/yr}} false alarms a year, all inside the targets. Condition 6 failed: the calibrated probability is better calibrated than the raw score but no better than always predicting the observed frequency, so the euro probability should not be read as a probability. The calibrator's weight on the alarm score stayed near zero, which suggests that the score carried little information about the stress event beyond what the base rate already says.

{{quote:EURO.md#Results > What this does and does not show}}

Under the pre-registered rule, the results stay published, the euro view stays experimental and no euro daily record is produced. The {{cell:EURO.md#Results > Step 2: the real backtest | combined (the model) | episodes}} euro episodes are now seen: any retuning, for instance a euro-denominated series, needs its own pre-registration with a stated reason written beforehand. The two explanations offered in the quote (the dollar-priced ETF and the alarm persisting after episodes end) are hypotheses and have not been tested.

This failure is a result of the method as much as of the data: it is the rule written beforehand that prevented the euro model from being presented as validated.
