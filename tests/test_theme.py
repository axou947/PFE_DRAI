import json
from pathlib import Path

import plotly.graph_objects as go

from pfe_drai.config import load_settings
from pfe_drai.theme import DARK, LIGHT, css, get_theme, regime_colors, style_figure


def _luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_get_theme_and_css():
    assert get_theme(True) is DARK and get_theme(False) is LIGHT
    assert DARK.page in css(DARK) and "invert" in css(DARK)
    assert "invert" not in css(LIGHT)  # the light theme only styles the app's own components


def test_dark_colors_read_on_the_dark_page():
    # The light palette is the validated one and stays as it is; the dark one must hold its own.
    base = load_settings()["regimes"]["colors"]
    colors = regime_colors(base, DARK)
    assert set(colors) == set(base)
    assert regime_colors(base, LIGHT) == base
    for regime, color in colors.items():
        assert _contrast(color, DARK.page) >= 3, regime
    for dim, color in DARK.dims.items():
        assert _contrast(color, DARK.page) >= 3, dim
    for state, color in DARK.states.items():
        assert _contrast(color, DARK.page) >= 3, state


def test_text_reads_on_both_pages():
    for theme in (LIGHT, DARK):
        assert _contrast(theme.text, theme.page) >= 7
        assert _contrast(theme.muted, theme.page) >= 4.5
        assert _contrast(theme.muted, theme.surface) >= 4.5


def test_style_figure_uses_the_theme():
    fig = style_figure(go.Figure(), DARK, 250)
    assert fig.layout.height == 250
    assert fig.layout.font.color == DARK.text
    assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert fig.layout.xaxis.gridcolor == DARK.grid


def test_every_language_has_the_dark_mode_label():
    for lang in ("en", "fr"):
        labels = json.loads((Path(__file__).resolve().parents[1] / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        assert labels["app.dark_mode"]
