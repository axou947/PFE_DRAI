# The Slowdown case: a partly negative result

This chapter is the worked example of a change that passed its pre-registered rule and still left the weakest regime weak. It is reported in full because of that.

## The problem

The rule of Chapter 3 calls a day Slowdown when the growth score is low and neither stress nor overheating applies. On real data the jump model never found those days as a group: until 2023 the state it named Slowdown held only a minority of Slowdown days, and from late 2023 no state was named Slowdown at all, so the application had not shown a Slowdown since then. Nothing checked whether the rule's Slowdown matched a slowdown of the economy.

A diagnosis on simulated data and on the code found that the rule's Slowdown flickered: it crossed its threshold several times a year, with spells of a few days, where a slowdown of the economy lasts months. The growth score is the average of four expanding z-scores (equity momentum, curve slope, industrial production and jobless claims), and a single extreme stretch such as 2020 squeezed every later reading.

## The change and its outside reference

Version v2.2 changes how the growth score is built, not the models: robust scaling (expanding median and interquartile range), a 21-day average, and a threshold of {{config.regimes.rule.growth_threshold|0}} (growth below its own median). The inputs are chosen on a real holdout before the out-of-sample period.

Slowdown is checked against an **outside reference that is never a model input**: the Chicago Fed National Activity Index, 3-month average, below zero (below-trend growth). The decision rule has nine numeric conditions, written before the real run, among them: the growth score matches the reference better than before, a Slowdown state exists in at least half of the refits, no episode is lost, the latency target holds, the false-alarm targets hold, and the Brier score and calibration error do not get worse.

## Step 1: choosing the growth inputs on a real holdout

{{quote:SLOWDOWN.md#Results > Step 1: growth holdout}}

The simulated data had selected the opposite candidate. That is the reason a real holdout is run, and why its choice, the four inputs with the curve slope, is the one in the settings.

## A departure from the protocol

The protocol said that if the winner of step 1 is not the first candidate, its inputs go into the settings before step 2. Step 2 was nevertheless run on the first candidate, straight after step 1. The departure is published as it happened and the run decides nothing:

{{quote:SLOWDOWN.md#Results > An unplanned run of step 2, on the wrong variant}}

This is also why the next run is no longer blind: it differs from one already seen by a single input.

## Step 2 on the selected variant

{{quote:SLOWDOWN.md#Results > Step 2 on the selected variant (run once}}

All nine conditions held and version v2.2 was adopted. The record of version {{meta.model_version}} agrees with this table (Appendix A, consistency check).

## A partly negative result

What passed, and what did not:

- The growth score is a better measure of growth: its balanced accuracy against the reference rose from {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | growth match with the reference (balanced accuracy) | v2.1}} to {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | growth match with the reference (balanced accuracy) | v2.2}}, and the rule's Slowdown is now a persistent regime (Slowdown spells per year and median spell in days: {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | rule: Slowdown spells / yr (median spell, days) | v2.2}}, against {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | rule: Slowdown spells / yr (median spell, days) | v2.1}} before).
- A state named Slowdown now exists in {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | refits with a state named Slowdown, agreement ≥ 50% | v2.2}} of the refits, against {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | refits with a state named Slowdown, agreement ≥ 50% | v2.1}} before. Detection is untouched.
- **What the application displays as Slowdown is still no better than chance.** Its balanced accuracy against the reference is {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | displayed Slowdown vs reference (balanced accuracy) | v2.2}}, where 0.5 is chance; it was {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | displayed Slowdown vs reference (balanced accuracy) | v2.1}}. Condition 3 asked for "higher" and it is higher, but by about one hundredth, which on years of mostly correlated days is not evidence of a better match. The displayed regime finds {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | reference slowdown days found / shown days that are right | v2.2}} (share of the reference's slowdown days found, share of shown days that are right).
- The rule now places {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | rule: days in Slowdown | v2.2}} of days in Slowdown, because its threshold is the median of a history that starts in 2004 and growth since 2009 sits below it often, while the application displays Slowdown on {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | days shown as Slowdown | v2.2}} of days. Part of the gap comes from the reference, which is below its long-run trend on {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | reference: days of below-trend growth | v2.2}} of the days since 2009, and part from the jump model, which also needs the stress and inflation dimensions to agree.

The honest reading is that the growth score became a better measure of growth, and that the displayed Slowdown is not yet a good match for the outside reference. Slowdown remains the weakest of the four regimes. A further change would need its own pre-registration, and the real out-of-sample period is no longer blind.
