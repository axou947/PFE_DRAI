"""Light and dark looks of the dashboard: palette, page CSS and the Plotly layout.

Streamlit fixes its own theme when the page loads, so the dark mode is a CSS layer over the light theme of
.streamlit/config.toml. Everything the app draws itself (charts, cards, chips) reads this palette.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    page: str  # page background
    surface: str  # sidebar, cards, inputs
    text: str
    muted: str
    grid: str
    border: str
    accent: str
    plotly: str  # Plotly template
    dims: dict  # stress / growth / inflation line colours
    regimes: dict  # overrides of the regime colours of settings.yaml that do not read on this background
    states: dict  # market stress states of the World map and their legend
    map_bg: str
    map_land: str
    map_border: str
    map_text: str
    map_neutral: str  # middle of the map scales


LIGHT = Theme(
    name="light",
    page="#fcfcfb",
    surface="#f3f2ef",
    text="#0b0b0b",
    muted="#52514e",
    grid="#e8e7e3",
    border="#d6d5d0",
    accent="#2a78d6",
    plotly="plotly_white",
    dims={"stress": "#2a78d6", "growth": "#eb6834", "inflation": "#1baf7a"},  # validated all-pairs trio
    regimes={},
    states={"calm": "#1baf7a", "elevated": "#eda100", "stress": "#d6453d", None: "#4a5363"},
    map_bg="#0d1117",
    map_land="#1c2330",
    map_border="#2d3646",
    map_text="#e6edf3",
    map_neutral="#2b3442",
)

DARK = Theme(
    name="dark",
    page="#0d0d0d",
    surface="#1a1a19",
    text="#f2f1ec",
    muted="#b4b3aa",
    grid="#2c2c2a",
    border="#383835",
    accent="#3987e5",
    plotly="plotly_dark",
    dims={"stress": "#3987e5", "growth": "#f0814f", "inflation": "#2ec98f"},
    regimes={"stress": "#9a8cf2"},  # the light theme's #4a3aa7 vanishes on a dark page
    states={"calm": "#2ec98f", "elevated": "#f2b51a", "stress": "#e66767", None: "#6b7689"},
    map_bg="#0d0d0d",
    map_land="#1c2330",
    map_border="#2d3646",
    map_text="#e6edf3",
    map_neutral="#2b3442",
)

THEMES = {"light": LIGHT, "dark": DARK}


def get_theme(dark: bool) -> Theme:
    return DARK if dark else LIGHT


def regime_colors(base: dict, theme: Theme) -> dict:
    """The regime colours of the settings, with this theme's replacements."""
    return {**base, **{r: c for r, c in theme.regimes.items() if r in base}}


def css(theme: Theme) -> str:
    """Page CSS: the app's own components in both themes, plus Streamlit's widgets in the dark one."""
    own = f"""
    .regime-card{{border-left:6px solid var(--c);background:{theme.surface};border-radius:6px;padding:14px 18px}}
    .regime-card .label{{color:{theme.muted};font-size:0.85rem;margin:0}}
    .regime-card .name{{font-size:1.7rem;font-weight:700;margin:2px 0}}
    .regime-card .desc{{color:{theme.muted};margin:0}}
    .chip{{display:inline-block;padding:1px 8px;border-radius:10px;border:1px solid {theme.border};font-size:0.8rem;margin-right:6px}}
    """
    if theme is not DARK:
        return f"<style>{own}</style>"
    t = theme
    dark = f"""
    :root{{color-scheme:dark}}
    .stApp,[data-testid="stAppViewContainer"],[data-testid="stHeader"],[data-testid="stBottom"]>div{{background:{t.page};color:{t.text}}}
    [data-testid="stSidebar"],[data-testid="stSidebar"]>div{{background:{t.surface}}}
    .stApp,.stApp p,.stApp li,.stApp label,.stApp span,.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp h5,.stApp h6,
    .stApp [data-testid="stMarkdownContainer"],.stApp [data-testid="stWidgetLabel"] p{{color:{t.text}}}
    .stApp [data-testid="stCaptionContainer"],.stApp [data-testid="stCaptionContainer"] p,
    .stApp [data-testid="stMetricLabel"] *{{color:{t.muted}}}
    .stApp a{{color:{t.accent}}}
    .stApp hr{{border-color:{t.border}}}
    .stApp code{{background:{t.surface};color:{t.text}}}
    [data-testid="stMetricValue"]{{color:{t.text}}}
    [data-baseweb="tab-list"]{{background:transparent}}
    [data-baseweb="tab"]{{background:transparent}}
    [data-baseweb="tab"] p{{color:{t.muted}}}
    [data-baseweb="tab"][aria-selected="true"] p{{color:{t.text}}}
    [data-baseweb="tab-border"]{{background:{t.border}}}
    [data-baseweb="select"]>div,[data-baseweb="input"],[data-baseweb="base-input"],[data-baseweb="textarea"],
    [data-testid="stDateInputField"],[data-testid="stNumberInputContainer"]{{background:{t.page};border-color:{t.border};color:{t.text}}}
    [data-baseweb="input"] input,[data-baseweb="base-input"] input,[data-baseweb="select"] input,textarea{{color:{t.text};
    -webkit-text-fill-color:{t.text};background:transparent}}
    [data-testid="stSelectbox"] div:has(> input),[data-testid="stMultiSelect"] div:has(input),[data-testid="stDateInput"] div:has(> input),
    [data-testid="stNumberInput"] div:has(> input),[data-testid="stTextInput"] div:has(> input){{background:{t.page};border-color:{t.border};color:{t.text}}}
    [data-testid="stSelectbox"] div,[data-testid="stSelectbox"] input,[data-testid="stDateInput"] input,[data-testid="stNumberInput"] input,
    [data-testid="stTextInput"] input{{color:{t.text};-webkit-text-fill-color:{t.text}}}
    [role="listbox"],[role="listbox"] *,[data-testid="stSelectboxVirtualDropdown"],[data-testid="stSelectboxVirtualDropdown"] *{{background:{t.surface};color:{t.text}}}
    [data-testid="stSelectbox"] svg,[data-testid="stDateInput"] svg,[data-testid="stSelectbox"] button,[data-baseweb="select"] svg,[data-baseweb="popover"] svg{{fill:{t.muted}}}
    [data-baseweb="popover"],[data-baseweb="popover"]>div,[data-baseweb="menu"],[data-baseweb="calendar"],
    [data-baseweb="calendar"] *{{background:{t.surface};color:{t.text}}}
    [data-baseweb="menu"] li:hover,[role="option"]:hover,[aria-selected="true"][role="option"]{{background:{t.border}}}
    [data-testid="stExpander"],[data-testid="stExpander"] details{{background:transparent;border-color:{t.border}}}
    [data-testid="stExpander"] summary:hover{{background:{t.surface}}}
    [data-testid="stAlert"]{{background:{t.surface};border:1px solid {t.border}}}
    [data-testid="stAlert"] *{{color:{t.text}}}
    .stButton button,.stDownloadButton button,[data-testid^="stBaseButton-secondary"]{{background:{t.surface};color:{t.text};border-color:{t.border}}}
    .stButton button:hover,.stDownloadButton button:hover{{border-color:{t.accent};color:{t.accent}}}
    button[data-variant="segmented_control"],button[data-variant="pills"]{{background:{t.page};color:{t.text};border-color:{t.border}}}
    button[data-variant="segmented_control"][aria-checked="true"],button[data-variant="pills"][aria-checked="true"]{{background:rgba(57,135,229,.22);color:{t.accent};border-color:{t.accent}}}
    [data-testid="stRadio"] [data-baseweb="radio"]>div:first-child{{background:{t.page};border-color:{t.muted}}}
    [data-testid="stCheckbox"] [data-baseweb="checkbox"]>div:first-child{{border-color:{t.muted}}}
    [data-testid="stSlider"] [data-testid="stTickBarMin"],[data-testid="stSlider"] [data-testid="stTickBarMax"]{{color:{t.muted}}}
    [data-testid="stSlider"] [data-baseweb="slider"]>div>div:first-child{{background:{t.border}}}
    [data-testid="stTooltipContent"],[data-baseweb="tooltip"] *{{background:{t.surface};color:{t.text}}}
    /* The tables are canvases that keep Streamlit's light theme: invert them, keeping the hues. */
    [data-testid="stDataFrame"]{{filter:invert(1) hue-rotate(180deg)}}
    iframe{{color-scheme:dark}}
    {own}
    """
    return f"<style>{dark}</style>"


def style_figure(fig, theme: Theme, height: int = 320, **kw):
    """Layout shared by the charts: this theme's template, a transparent page-coloured canvas, readable text and grid."""
    fig.update_layout(
        template=theme.plotly,
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(color=theme.text, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=-0.15, font=dict(color=theme.text)),
        hoverlabel=dict(font_size=13),
        **kw,
    )
    fig.update_xaxes(gridcolor=theme.grid, zeroline=False, linecolor=theme.grid, tickfont=dict(color=theme.muted))
    fig.update_yaxes(gridcolor=theme.grid, zeroline=False, linecolor=theme.grid, tickfont=dict(color=theme.muted))
    return fig
