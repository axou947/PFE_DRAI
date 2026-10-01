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
from .models.combined import combine
from .regimes import flip_distances, rule_labels
from .validation import evaluate, find_episodes, onset_target, rule_fingerprint, walk_forward


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

    # ---- models -----------------------------------------------------------
    def _cache_key(self, model: str) -> str:
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
        if get_model(model, self.settings).inputs == "market":
            fingerprint["market"] = float(self.market.fillna(0).values.sum())
            fingerprint["episode_rule"] = rule_fingerprint(self.settings)
        return hashlib.sha256(json.dumps(fingerprint, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def probabilities(self, model: str | None = None) -> pd.DataFrame:
        """Out-of-sample regime probabilities from walk-forward (cached on disk)."""
        model = model or self.settings["models"]["default"]
        memo = self.__dict__.setdefault("_probs", {})
        if model in memo:
            return memo[model]
        components = getattr(get_model(model, self.settings), "components", None)
        if components:  # built from its components' cached probabilities
            memo[model] = combine(*(self.probabilities(name) for name in components))
            return memo[model]
        path = resolve(self.settings["data"]["cache_dir"]) / "models" / f"{model}-{self._cache_key(model)}.pkl"
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
            )
            if self.use_cache:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(pickle.dumps(probs))
        memo[model] = probs
        return probs

    def fitted_model(self, model: str | None = None):
        """A model fitted on all available data (for explanations, not for backtests)."""
        model = model or self.settings["models"]["default"]
        return get_model(model, self.settings).fit(self.features, self.scores, self.labels)

    def regimes(self, model: str | None = None) -> pd.Series:
        return self.probabilities(model).idxmax(axis=1).rename("regime")

    # ---- outputs ------------------------------------------------------------
    def evaluate(self, model: str | None = None) -> dict:
        return evaluate(
            self.probabilities(model), self.prices["equity"], self.episodes, self.settings, truth=self.truth, rule=self.labels
        )

    def alerts(self, model: str | None = None) -> pd.DataFrame:
        early = self.probabilities("gbm") if model != "gbm" else None
        return compute_alerts(
            self.probabilities(model), self.scores.loc[self.probabilities(model).index], self.settings, early=early
        )

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
            data_provider=self.provider.name,
            is_live_data=self.provider.is_live,
        )


__all__ = ["DIMENSIONS", "FEATURES", "Pipeline", "State"]
