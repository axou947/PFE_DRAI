import pytest

from pfe_drai.config import load_settings
from pfe_drai.pipeline import Pipeline


@pytest.fixture(scope="session")
def settings():
    # A shorter history keeps the test suite fast.
    return load_settings(
        overrides={
            "data": {"start": "2004-01-01", "end": "2026-06-30"},
            "validation": {"refit_every_days": 252},
            "models": {"gbm": {"max_iter": 30}},
        }
    )


@pytest.fixture(scope="session")
def pipeline(settings):
    return Pipeline(settings, use_cache=False)
