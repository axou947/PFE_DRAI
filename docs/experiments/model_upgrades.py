"""Seven candidate upgrades of the v2.2 model, on simulated histories (docs/MODEL_UPGRADES.md).

    python docs/experiments/model_upgrades.py 1 2 3 4 5 6 7 8              # development seeds
    python docs/experiments/model_upgrades.py 9 10 11 12 42 baseline hmm   # some seeds, some candidates

Simulated data only: nothing here reads or scores real data, and no candidate changes the package.
Each candidate is applied by patching the package inside this process, so the published model and its
settings fingerprint never move. One row per seed and candidate, then sums and means per candidate.
One process per seed with OMP_NUM_THREADS=1 runs in parallel.

Candidates (the inflation score is left alone: docs/INFLATION.md):
- baseline       v2.2 as published.
- onset_downside onset detector + downside-risk inputs (EWMA downside deviation, EWMA return, Sortino
                 ratio, worst day of 10): the features of Shu & Mulvey's jump-model papers.
- onset_flight   onset detector + flight to quality (10-year yield change over 5 and 21 days, 63-day
                 correlation of equity returns with yield changes).
- hysteresis     alarm on after 3 days above 0.5 (unchanged), off only once the score falls below 0.3.
- jump_downside  jump model clusters the 3 scores plus 2 z-scored downside inputs (Shu & Mulvey).
- hmm            Gaussian hidden Markov model (4 states, full covariance) instead of the jump model,
                 filtered (causal) probabilities, states named as the jump model's.
- growth_fast    faster growth inputs: production over 6 months (annualised) instead of 12, jobless
                 claims as the rise of their 4-week average over its 52-week low instead of a 3-month change.
- calm_blend     the calm regimes shown = average of the jump model's and gbm's calm shares.
"""

import importlib
import sys
from contextlib import ExitStack
from unittest import mock

import numpy as np
import pandas as pd

import pfe_drai.features.market as market_mod
import pfe_drai.models.base as base_mod
import pfe_drai.pipeline as pipeline_mod
import pfe_drai.validation.metrics as metrics_mod
from pfe_drai.config import load_settings
from pfe_drai.models.base import softmax
from pfe_drai.models.combined import combine
from pfe_drai.models.jump import JumpModel, _viterbi, forward_values
from pfe_drai.pipeline import Pipeline
from pfe_drai.regimes import name_states
from pfe_drai.validation.slowdown import slowdown_report

# pfe_drai.features re-exports a function named `build`, which hides the module of the same name.
build_mod = importlib.import_module("pfe_drai.features.build")

# ---- extra inputs ---------------------------------------------------------------------------------


def downside_inputs(equity: pd.Series) -> pd.DataFrame:
    """Shu & Mulvey (2024) style features, past data only: EWMA downside deviation, return, Sortino."""
    r = np.log(equity).diff()
    f = pd.DataFrame(index=equity.index)
    for hl in (5, 21):
        f[f"down_dev_{hl}"] = np.sqrt((r.clip(upper=0) ** 2).ewm(halflife=hl).mean() * 252)
    f["ewm_ret_10"] = r.ewm(halflife=10).mean() * 252
    dd10 = np.sqrt((r.clip(upper=0) ** 2).ewm(halflife=10).mean() * 252)
    f["sortino_10"] = (f["ewm_ret_10"] / dd10.replace(0, np.nan)).clip(-20, 20)
    f["worst_day_10"] = r.rolling(10).min()
    return f


def flight_inputs(equity: pd.Series, us10y: pd.Series) -> pd.DataFrame:
    """Flight to quality: Treasury yields falling while stocks fall."""
    f = pd.DataFrame(index=equity.index)
    f["y10_change_5d"] = us10y.diff(5)
    f["y10_change_21d"] = us10y.diff(21)
    f["stock_yield_corr_63"] = np.log(equity).diff().rolling(63).corr(us10y.diff())
    return f


DOWNSIDE = ["down_dev_5", "down_dev_21", "ewm_ret_10", "sortino_10", "worst_day_10"]
FLIGHT = ["y10_change_5d", "y10_change_21d", "stock_yield_corr_63"]


def patched_market_frame(original, extra: str):
    def market_frame(raw, settings, release_dated=frozenset()):
        f = original(raw, settings, release_dated)
        names = [n for n in ("equity", "us10y") if n in raw]
        prices = build_mod.align({n: raw[n] for n in names}, {}, release_dated).reindex(f.index)
        if extra == "downside":
            return f.join(downside_inputs(prices["equity"]))
        return f.join(flight_inputs(prices["equity"], prices["us10y"]))

    return market_frame


# ---- alarm with hysteresis ------------------------------------------------------------------------


def hysteresis_signal(off: float):
    def stress_signal(p_stress: pd.Series, threshold: float, confirm_days: int) -> pd.Series:
        on_rule = (p_stress > threshold).rolling(confirm_days).sum() >= confirm_days
        values, state = np.zeros(len(p_stress), dtype=bool), False
        for i, (start, p) in enumerate(zip(on_rule.to_numpy(), p_stress.to_numpy(), strict=True)):
            state = True if start else (state and p >= off)
            values[i] = state
        return pd.Series(values, index=p_stress.index)

    return stress_signal


# ---- jump model on more inputs / HMM ---------------------------------------------------------------

EXTRA_FOR_JUMP: dict[str, pd.DataFrame] = {}


class JumpDownside(JumpModel):
    """Jump model on the 3 scores plus 2 expanding z-scored downside inputs; named on the 3 scores."""

    def _x(self, scores):
        extra = EXTRA_FOR_JUMP["frame"].reindex(scores.index).fillna(0.0)
        return np.column_stack([scores.values, extra.values])

    def fit(self, features, scores, labels):
        from sklearn.cluster import KMeans

        cfg = self.settings["models"]["jump"]
        x = self._x(scores)
        k = len(self.regimes)
        self.centroids = KMeans(n_clusters=k, n_init=5, random_state=0).fit(x).cluster_centers_
        for _ in range(cfg["n_iter"]):
            states = _viterbi(self._loss(x), cfg["penalty"])
            new = np.array([x[states == j].mean(axis=0) if (states == j).any() else self.centroids[j] for j in range(k)])
            if np.allclose(new, self.centroids):
                break
            self.centroids = new
        states = _viterbi(self._loss(x), cfg["penalty"])
        self.state_table = name_states(states, self.centroids[:, :3], scores, labels, self.settings)
        self.state_names = list(self.state_table["name"])
        return self

    def predict_proba(self, features, scores):
        cfg = self.settings["models"]["jump"]
        values = forward_values(self._loss(self._x(scores)), cfg["penalty"])
        probs = softmax(-values / cfg["temperature"])
        return self._frame(probs, scores.index, self.state_names)


class HMMModel(JumpModel):
    """Gaussian HMM (4 states, full covariance), filtered probabilities: day t uses data up to t only."""

    def fit(self, features, scores, labels):
        from hmmlearn.hmm import GaussianHMM

        x = scores.values
        self.hmm = GaussianHMM(n_components=len(self.regimes), covariance_type="full", n_iter=50, random_state=0)
        self.hmm.fit(x)
        states = self.hmm.predict(x)
        self.state_table = name_states(states, self.hmm.means_, scores, labels, self.settings)
        self.state_names = list(self.state_table["name"])
        return self

    def predict_proba(self, features, scores):
        log_b = self.hmm._compute_log_likelihood(scores.values)
        a = self.hmm.transmat_
        alpha = np.empty_like(log_b)
        prev = self.hmm.startprob_
        for t in range(len(log_b)):
            prior = prev if t == 0 else prev @ a
            b = np.exp(log_b[t] - log_b[t].max())
            post = prior * b
            post = post / post.sum() if post.sum() > 0 else np.full(len(post), 1 / len(post))
            alpha[t] = post
            prev = post
        return self._frame(alpha, scores.index, self.state_names)


# ---- faster growth inputs --------------------------------------------------------------------------


def growth_fast(prices: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=prices.index)
    f["equity_momentum"] = np.log(prices["equity"]).diff(126)
    f["curve_slope"] = prices["us10y"] - prices["us2y"]
    f["industrial_production"] = 2 * np.log(prices["indpro"]).diff(126)
    claims = prices["claims"].rolling(20).mean()
    f["jobless_claims"] = -(claims / claims.rolling(252, min_periods=126).min() - 1)
    return f


# ---- calm regimes from jump and gbm ----------------------------------------------------------------


def calm_blend(parts, calibrated):
    jump, gbm = parts["jump"], parts["gbm"].reindex(columns=parts["jump"].columns, fill_value=0.0)
    idx = jump.index.intersection(gbm.index)
    mix = 0.5 * jump.loc[idx] + 0.5 * gbm.loc[idx]
    return combine(mix, stress=calibrated.stress)


# ---- run ---------------------------------------------------------------------------------------------

CANDIDATES = ["baseline", "onset_downside", "onset_flight", "hysteresis", "jump_downside", "hmm", "growth_fast", "calm_blend"]


def patches(name: str, stack: ExitStack) -> dict:
    """Patch the package for `name`; return settings overrides."""
    if name in ("onset_downside", "onset_flight"):
        extra = name.split("_")[1]
        stack.enter_context(mock.patch.object(pipeline_mod, "market_frame", patched_market_frame(market_mod.market_frame, extra)))
        cols = DOWNSIDE if extra == "downside" else FLIGHT
        stack.enter_context(mock.patch.dict(market_mod.INPUT_SETS, {f"market_{extra}": market_mod.MARKET + cols}))
        return {"models": {"onset": {"inputs": f"market_{extra}"}}}
    if name == "hysteresis":
        stack.enter_context(mock.patch.object(metrics_mod, "stress_signal", hysteresis_signal(0.3)))
        stack.enter_context(mock.patch.object(pipeline_mod, "stress_signal", hysteresis_signal(0.3)))
    if name == "jump_downside":
        stack.enter_context(mock.patch.dict(base_mod._REGISTRY, {"jump": JumpDownside}))
    if name == "hmm":
        stack.enter_context(mock.patch.dict(base_mod._REGISTRY, {"jump": HMMModel}))
    if name == "growth_fast":
        stack.enter_context(mock.patch.object(build_mod, "growth_features", growth_fast))
    if name == "calm_blend":
        stack.enter_context(mock.patch.object(pipeline_mod, "combine_calibrated", calm_blend))
    return {}


def run(seed: int, names: list[str]) -> list[dict]:
    rows = []
    for name in names:
        with ExitStack() as stack:
            overrides = {"data": {"seed": seed}, **patches(name, stack)}
            p = Pipeline(load_settings(overrides=overrides), use_cache=False)
            if name == "jump_downside":
                eq = p.prices["equity"]
                d = downside_inputs(eq)[["down_dev_21", "ewm_ret_10"]]
                d["down_dev_21"] = np.log(d["down_dev_21"].clip(lower=1e-4))
                EXTRA_FOR_JUMP["frame"] = build_mod.expanding_zscore(d, 252, 4.0)
            r = p.evaluate("combined")
            report = slowdown_report(p, "combined")["summary"]
            shown = p.probabilities("combined").idxmax(axis=1)
            truth = p.truth.reindex(shown.index)
            per_regime = {
                f"recall_{g}": float((shown[truth == g] == g).mean()) for g in ("expansion", "overheating", "slowdown", "stress")
            }
            rows.append(
                {
                    "seed": seed,
                    "candidate": name,
                    "detected": r["detected"],
                    "episodes": r["n_episodes"],
                    "lat_all": r["median_latency_all"],
                    "fp_yr": r["false_positives_per_year"],
                    "alarm": r["false_alarm_share"],
                    "brier": r["brier"],
                    "ece": r["ece"],
                    "log_loss": r["log_loss"],
                    "switch_yr": r["switches_per_year"],
                    "acc_truth": r["accuracy_truth"],
                    "growth_ba": report["growth_ba"],
                    "shown_ba": report["shown_ba"],
                    "state_share": report["state_share"],
                    **per_regime,
                }
            )
            print(pd.DataFrame(rows[-1:]).round(3).to_string(index=False, header=len(rows) == 1), flush=True)
    return rows


if __name__ == "__main__":
    args = sys.argv[1:] or ["42"]
    names = [a for a in args if a in CANDIDATES] or CANDIDATES
    seeds = [int(a) for a in args if a not in CANDIDATES]
    frame = pd.DataFrame([row for seed in seeds for row in run(seed, names)])
    pd.set_option("display.width", 300)
    pd.set_option("display.max_columns", 40)
    print(frame.round(3).to_string(index=False))
    sums = frame.groupby("candidate", sort=False)[["detected", "episodes"]].sum()
    means = frame.groupby("candidate", sort=False).mean(numeric_only=True).drop(columns=["seed", "detected", "episodes"])
    print(sums.join(means).round(3).to_string())
