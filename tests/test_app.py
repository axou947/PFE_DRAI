import datetime as dt
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def test_world_date_outside_the_data_is_clamped():
    # A map date kept from an earlier run (e.g. today, before the source's last close) must not crash the app.
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.session_state["world_date"] = dt.date(2099, 1, 1)
    at.run()
    assert not at.exception
    assert at.session_state["world_date"] < dt.date(2099, 1, 1)
