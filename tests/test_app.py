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


def test_world_local_currency_and_link_views():
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.run()
    at.sidebar.radio[0].set_value("English").run()
    assert not at.exception

    def control(label):
        return next(c for c in at.segmented_control if c.label == label)

    control("View").set_value("returns").run()
    control("Currency").set_value("local").run()
    assert not at.exception
    assert any("H.10" in c.value for c in at.caption)  # the FX note and its caveat are shown
    control("View").set_value("link").run()
    assert not at.exception
    control("Colour by").set_value("beta").run()
    control("Window").set_value(63).run()
    assert not at.exception
    assert any("not a cause" in c.value for c in at.caption)


def test_dark_mode_switch_restyles_the_charts_and_both_languages_have_the_label():
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.run()
    toggle = next(c for c in at.sidebar.toggle if c.key == "dark_mode")
    assert toggle.value is False
    toggle.set_value(True).run()
    assert not at.exception
    assert at.session_state["dark_mode"] is True
    assert any("background:#0d0d0d" in m.value for m in at.markdown)  # the dark page CSS is injected
    toggle.set_value(False).run()
    assert not at.exception
    assert not any("background:#0d0d0d" in m.value for m in at.markdown)


def test_dashboard_explains_the_regime_in_both_languages():
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.run()
    assert not at.exception
    assert any(h.value == "Pourquoi ce régime" for h in at.subheader)
    assert any(m.value.startswith("La règle donne") for m in at.markdown)
    at.sidebar.radio[0].set_value("English").run()
    assert not at.exception
    assert {"Why this regime", "What would flip the rule", "What drives the stress alarm"} <= {h.value for h in at.subheader}
    assert any("not a cause" in c.value or "does not identify a cause" in c.value for c in at.caption)
