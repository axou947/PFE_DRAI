"""One object that runs the whole chain: data -> features -> models -> validation.

The app, the API, the CLI and the tests all go through Pipeline, so a change of data
source or model in config/settings.yaml reaches every screen at once.
"""

import hashlib
import json
import pickle
from dataclasses import dataclass, field
from functools import cached_property

import pandas as pd

from .alerts import compute_alerts
from .config import load_settings, resolve
from .data import get_provider
from .features import DIMENSIONS, FEATURES, build
from .features.market import market_frame
from .models import get_model
from .models.calibrator import Calibrated
from .models.combined import calibrate, combination, combine, combine_calibrated, detector_score
from .regimes import flip_distances, rule_labels
from .validation import evaluate, find_episodes, onset_target, refit_cuts, rule_fingerprint, stress_signal, walk_forward
from .validation.calibration import calibration_report, json_number, stress_event, to_json


@dataclass
class State:
    """Everything the dashboard and the committee note show for one day."""

    date: pd.Timestamp
    model: str
    regime: str
    probabilities: dict[str, float]
    scores: dict[str, float]
    previous: dict = field(default_factory=dict)  # same fields, one week earlier
    drivers: dict[str, float] = field(default_factory=dict)  # feature z-scores
    flip: dict[str, float] = field(default_factory=dict)
    early_warning: dict[str, float] | None = None
    # How the unsupervised model behind the regime named its states (regimes.name_states).
    states: list[dict] = field(default_factory=list)
    # Stress alarm (detector score above the threshold for `confirm_days` days) and how well
    # P(stress) has been calibrated so far (docs/CALIBRATION.md).
    alarm: dict = field(default_factory=dict)
    calibration: dict = field(default_factory=dict)
    data_provider: str = ""
    is_live_data: bool = False

    def to_dict(self) -> dict:
        return {
            "date": self.date.date().isoformat(),
            "model": self.model,
            "regime": self.regime,
            "probabilities": self.probabilities,
            "scores": self.scores,
            "previous": self.previous,
            "drivers": self.drivers,
            "flip": self.flip,
            "early_warning": self.early_warning,
            "states": self.states,
            "alarm": self.alarm,
            "calibration": self.calibration,
            "data_provider": self.data_provider,
            "is_live_data": self.is_live_data,
        }


class Pipeline:
    def __init__(self, settings: dict | None = None, use_cache: bool = True):
        self.settings = settings or load_settings()
        self.use_cache = use_cache

    # ---- data -------------------------------------------------------------
    @cached_property
    def provider(self):
        return get_provider(self.settings)

    @cached_property
    def raw(self) -> dict[str, pd.Series]:
        cfg = self.settings["data"]
        start = pd.Timestamp(cfg["start"])
        end = pd.Timestamp(cfg["end"]) if cfg.get("end") else pd.Timestamp.today().normalize()
        data = self.provider.fetch(start, end)
        self.provider.check(data)
        return data

    @cached_property
    def _built(self):
        return build(self.raw, self.settings, self.provider.release_dated)

    @property
    def prices(self) -> pd.DataFrame:
        return self._built[0]

    @property
    def features(self) -> pd.DataFrame:
        return self._built[1]

    @property
    def scores(self) -> pd.DataFrame:
        return self._built[2]

    @cached_property
    def labels(self) -> pd.Series:
        return rule_labels(self.scores, self.settings)

    @cached_property
    def truth(self) -> pd.Series | None:
        truth = self.provider.truth()
        return truth.reindex(self.scores.index) if truth is not None else None

    @cached_property
    def episodes(self):
        return find_episodes(self.prices["equity"], self.settings)

    @cached_property
    def market(self) -> pd.DataFrame:
        """Fast market inputs of the onset detector, on the same days as the scores."""
        return market_frame(self.raw, self.settings, self.provider.release_dated).reindex(self.scores.index)

    @cached_property
    def onset(self) -> pd.Series:
        """Target of the onset detector: inside an episode now or within `horizon_days`."""
        cfg = self.settings["models"]["onset"]
        return onset_target(self.scores.index, self.episodes, cfg["horizon_days"], cfg.get("after_start_days"))

    @cached_property
    def event(self) -> pd.Series:
        """What P(stress) is checked against: inside an episode, or one starts within the horizon."""
        return stress_event(self.scores.index, self.episodes, self.settings)

    # ---- models -----------------------------------------------------------
    def _cache_key(self, model: str, warmup: int | None = None) -> str:
        fingerprint = {
            "provider": self.settings["data"],
            "features": self.settings["features"],
            "regimes": self.settings["regimes"],
            "model": self.settings["models"].get(model, {}),
            "validation": {k: v for k, v in self.settings["validation"].items() if k in ("min_train_days", "refit_every_days")},
            "data": [len(self.scores), float(self.scores.values.sum()), str(self.scores.index[-1])],
            "name": model,
            "version": 1,
        }
        if warmup is not None:
            fingerprint["warmup"] = warmup
        if get_model(model, self.settings).inputs == "market":
            fingerprint["market"] = float(self.market.fillna(0).values.sum())
            fingerprint["episode_rule"] = rule_fingerprint(self.settings)
        return hashlib.sha256(json.dumps(fingerprint, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def probabilities(self, model: str | None = None, warmup: int | None = None) -> pd.DataFrame:
        """Out-of-sample regime probabilities from walk-forward (cached on disk).

        `warmup`: start predicting earlier than the backtest (calibrated combination, models/calibrator.py).
        """
        model = model or self.settings["models"]["default"]
        memo = self.__dict__.setdefault("_probs", {})
        if (model, warmup) in memo:
            return memo[(model, warmup)]
        combined = get_model("combined", self.settings)
        components = getattr(get_model(model, self.settings), "components", None)
        if components:  # built from its components' cached probabilities
            if combined.warmup is None:
                memo[(model, warmup)] = combine(*(self.probabilities(name) for name in components))
            else:
                parts = {name: self.probabilities(name, combined.warmup) for name in components}
                memo[(model, warmup)] = combine_calibrated(parts, self.calibrated())
            return memo[(model, warmup)]
        if warmup is None and combined.warmup is not None and model in combined.components:
            # Same fits as the warm-up run from the backtest start on: reuse it instead of refitting.
            memo[(model, warmup)] = self.probabilities(model, combined.warmup).loc[self.backtest_start :]
            return memo[(model, warmup)]
        path = resolve(self.settings["data"]["cache_dir"]) / "models" / f"{model}-{self._cache_key(model, warmup)}.pkl"
        if self.use_cache and path.exists():
            probs = pickle.loads(path.read_bytes())
        else:
            needs_market = get_model(model, self.settings).inputs == "market"
            probs = walk_forward(
                model,
                self.features,
                self.scores,
                self.labels,
                self.settings,
                market=self.market if needs_market else None,
                onset=self.onset if needs_market else None,
                warmup=warmup,
            )
            if self.use_cache:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(pickle.dumps(probs))
        memo[(model, warmup)] = probs
        return probs

    def calibrated(self) -> Calibrated:
        """Calibrated P(stress) of the combined model, with the fit of every refit (docs/CALIBRATION.md).

        Available whatever `stress_combination` is set to, so a backtest can compare both.
        """
        if "_calibrated" not in self.__dict__:
            combined = get_model("combined", self.settings)
            warmup = self.settings["models"]["combined"]["stack"]["warmup_days"]
            parts = {name: self.probabilities(name, warmup) for name in combined.components}
            self.__dict__["_calibrated"] = calibrate(parts, self.event, self.settings, self.backtest_start)
        return self.__dict__["_calibrated"]

    @property
    def backtest_start(self) -> pd.Timestamp:
        return self.scores.index[self.settings["validation"]["min_train_days"]]

    def alarm_score(self, model: str | None = None) -> pd.Series:
        """What the stress alarm reads: the detector score for `combined` (highest stress probability of
        its components, uncalibrated: the alarm is unchanged by calibration), P(stress) for the others."""
        model = model or self.settings["models"]["default"]
        components = getattr(get_model(model, self.settings), "components", None)
        if not components:
            return self.probabilities(model)["stress"]
        return detector_score(*(self.probabilities(name) for name in components)).loc[self.probabilities(model).index]

    def calibration(self, model: str | None = None, date=None) -> dict:
        """Calibration of the model's P(stress) on its out-of-sample days whose outcome was known by `date`."""
        return calibration_report(self.probabilities(model)["stress"], self.episodes, self.settings, until=date)

    def calibrator_fit(self, model: str | None = None, date=None) -> dict | None:
        """The calibrator behind P(stress) on `date` (default: latest), None when P(stress) is not calibrated."""
        model = model or self.settings["models"]["default"]
        if model != "combined" or combination(self.settings) != "calibrated":
            return None
        fits = self.calibrated().fits
        day = self.probabilities(model).index[-1] if date is None else pd.Timestamp(date)
        row = fits[fits["first_day"] <= day].iloc[-1]
        return {
            "first_day": row["first_day"].date().isoformat(),
            "train_days": int(row["train_days"]),
            "event_days": int(row["event_days"]),
            "intercept": json_number(row["intercept"]),
            "weights": {k: json_number(row[k]) for k in fits.columns if k not in _FIT_KEYS},
            "calibrated": bool(row["intercept"] == row["intercept"]),
        }

    def alarm(self, model: str | None = None, date=None) -> dict:
        """Stress alarm on `date`: on once the alarm score has stayed above the threshold for `confirm_days` days."""
        cfg = self.settings["validation"]
        score = self.alarm_score(model)
        score = score if date is None else score.loc[:date]
        signal = stress_signal(score, cfg["stress_probability_threshold"], cfg["confirm_days"])
        on = bool(signal.iloc[-1])
        since = None
        if on:
            off = signal[~signal]
            since = signal.loc[off.index[-1] :].index[1] if len(off) else signal.index[0]
        return {
            "on": on,
            "since": since.date().isoformat() if since is not None else None,
            "score": _round(float(score.iloc[-1])),
            "threshold": cfg["stress_probability_threshold"],
            "confirm_days": cfg["confirm_days"],
        }

    def fitted_model(self, model: str | None = None):
        """A model fitted on all available data (for explanations, not for backtests)."""
        model = model or self.settings["models"]["default"]
        return get_model(model, self.settings).fit(self.features, self.scores, self.labels)

    def unsupervised_model(self, model: str | None) -> str | None:
        """The unsupervised model whose named states give `model` its calm regimes, if any."""
        model = model or self.settings["models"]["default"]
        unsupervised = "jump" if model == "combined" else model
        return unsupervised if unsupervised in ("jump", "kmeans") else None

    def _state_table(self, model: str, cut: int) -> pd.DataFrame:
        memo = self.__dict__.setdefault("_state_tables", {})
        if (model, cut) not in memo:
            fitted = get_model(model, self.settings).fit(self.features.iloc[:cut], self.scores.iloc[:cut], self.labels.iloc[:cut])
            memo[(model, cut)] = fitted.state_table
        return memo[(model, cut)]

    def state_maps(self, model: str | None = None) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
        """How the unsupervised model behind `model` named its states at each walk-forward refit.

        One (first day predicted, state table) per refit: the same fits as the backtest.
        Empty for supervised models, which predict the rule regimes directly. See docs/REGIMES.md.
        """
        unsupervised = self.unsupervised_model(model)
        if unsupervised is None:
            return []
        cuts = refit_cuts(len(self.scores), self.settings, unsupervised)
        return [(self.scores.index[cut], self._state_table(unsupervised, cut)) for cut in cuts]

    def state_map(self, model: str | None = None, date=None) -> pd.DataFrame | None:
        """State table of the walk-forward fit that made the prediction on `date` (default: latest)."""
        unsupervised = self.unsupervised_model(model)
        if unsupervised is None:
            return None
        cuts = refit_cuts(len(self.scores), self.settings, unsupervised)
        pos = len(self.scores) - 1 if date is None else self.scores.index.searchsorted(pd.Timestamp(date), side="right") - 1
        earlier = [cut for cut in cuts if cut <= pos]
        if not earlier:
            return None  # before the out-of-sample period: no prediction, no table
        return self._state_table(unsupervised, earlier[-1])

    def regimes(self, model: str | None = None) -> pd.Series:
        return self.probabilities(model).idxmax(axis=1).rename("regime")

    # ---- outputs ------------------------------------------------------------
    def evaluate(self, model: str | None = None) -> dict:
        return evaluate(
            self.probabilities(model),
            self.prices["equity"],
            self.episodes,
            self.settings,
            truth=self.truth,
            rule=self.labels,
            score=self.alarm_score(model),
        )

    def alerts(self, model: str | None = None) -> pd.DataFrame:
        early = self.probabilities("gbm") if model != "gbm" else None
        probs = self.probabilities(model)
        return compute_alerts(probs, self.scores.loc[probs.index], self.settings, early=early, score=self.alarm_score(model))

    def state(self, model: str | None = None, date=None, week: int = 5) -> State:
        model = model or self.settings["models"]["default"]
        probs = self.probabilities(model)
        date = probs.index[-1] if date is None else probs.index[probs.index.searchsorted(pd.Timestamp(date), side="right") - 1]
        pos = probs.index.get_loc(date)
        prev_date = probs.index[max(0, pos - week)]

        def snap(d):
            p = probs.loc[d]
            return {
                "date": d.date().isoformat(),
                "regime": str(p.idxmax()),
                "probabilities": {k: float(v) for k, v in p.items()},
                "scores": {k: float(v) for k, v in self.scores.loc[d].items()},
                "drivers": {k: float(v) for k, v in self.features.loc[d].items()},
            }

        now, before = snap(date), snap(prev_date)
        early = None
        if model != "gbm":
            gbm = self.probabilities("gbm")
            if date in gbm.index:
                early = {k: float(v) for k, v in gbm.loc[date].items()}
        table = self.state_map(model, date)
        states = (
            [] if table is None else [{k: _round(v) for k, v in row.items()} for row in table.reset_index().to_dict("records")]
        )
        calibration = to_json(self.calibration(model, date))
        calibration["combination"] = combination(self.settings) if model == "combined" else "raw"
        calibration["calibrator"] = self.calibrator_fit(model, date)
        return State(
            date=date,
            model=model,
            regime=now["regime"],
            probabilities=now["probabilities"],
            scores=now["scores"],
            previous=before,
            drivers=now["drivers"],
            flip=flip_distances(self.scores.loc[date], self.settings),
            early_warning=early,
            states=states,
            alarm=self.alarm(model, date),
            calibration=calibration,
            data_provider=self.provider.name,
            is_live_data=self.provider.is_live,
        )


_FIT_KEYS = ("first_day", "intercept", "train_days", "event_days")


def _round(value):
    return round(value, 4) if isinstance(value, float) else value


__all__ = ["DIMENSIONS", "FEATURES", "Pipeline", "State"]
