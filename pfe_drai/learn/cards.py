"""Concept cards, glossary and history lessons of the Learn pages (docs/LEARN.md).

One card = one concept written twice, for beginners and for professionals, in French and English.
Both levels share the card's key points (`facts`), its live indicators and its links, so the two tabs
teach the same thing at two depths. The wording is ours, reviewed, never generated on the fly.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from ..config import resolve

LEVELS = ("beginner", "pro")
LANGS = ("fr", "en")
THEMES = ("macro", "micro", "model")
SECTIONS = ("summary", "what", "good", "bad", "next")
PRO_EXTRAS = ("mechanics", "reading")
# Card opened first, from today's regime: the concept that best explains it.
REGIME_CARD = {"expansion": "growth", "overheating": "inflation", "slowdown": "labour_market", "stress": "volatility"}


@dataclass(frozen=True)
class Card:
    id: str
    theme: str
    icon: str
    title: dict
    indicators: tuple[str, ...]
    chart: tuple[str, ...]
    leads_to: tuple[dict, ...]
    facts: dict
    beginner: dict
    pro: dict
    quiz: dict

    def text(self, level: str, lang: str) -> dict:
        return getattr(self, level)[lang]


@lru_cache
def _load_cards(folder: str) -> tuple[Card, ...]:
    cards = []
    for path in sorted(Path(folder).glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        cards.append(
            Card(
                id=raw["id"],
                theme=raw["theme"],
                icon=raw.get("icon", ""),
                title=raw["title"],
                indicators=tuple(raw.get("indicators", [])),
                chart=tuple(raw.get("chart", raw.get("indicators", [])[:2])),
                leads_to=tuple(raw.get("leads_to", [])),
                facts=raw["facts"],
                beginner=raw["beginner"],
                pro=raw["pro"],
                quiz=raw.get("quiz", {}),
            )
        )
    order = {theme: i for i, theme in enumerate(THEMES)}
    return tuple(sorted(cards, key=lambda c: (order.get(c.theme, 9), raw_order(c.id))))


def raw_order(card_id: str) -> int:
    """Teaching order inside a theme (cards not listed go last, alphabetically)."""
    try:
        return ORDER.index(card_id)
    except ValueError:
        return len(ORDER)


ORDER = [
    "inflation",
    "deflation",
    "fed_policy",
    "real_rates",
    "yield_curve",
    "labour_market",
    "wages",
    "growth",
    "recession",
    "stagflation",
    "credit",
    "volatility",
    "qe_qt",
    "dollar",
    "oil",
    "fiscal",
    "pricing_power",
    "consumer",
    "corporate_debt",
    "supply_demand",
    "firm_investment",
    "housing",
    "liquidity",
    "our_regimes",
    "stress_alarm",
    "probabilities",
]


def load_cards(settings: dict) -> list[Card]:
    return list(_load_cards(str(resolve(settings["learn"]["cards"]))))


def cards_by_id(settings: dict) -> dict[str, Card]:
    return {c.id: c for c in load_cards(settings)}


def leads_from(cards: list[Card], card_id: str) -> list[tuple[Card, dict]]:
    """Cards that lead to `card_id`, with the edge (its causes)."""
    return [(c, edge) for c in cards for edge in c.leads_to if edge["card"] == card_id]


def load_glossary(settings: dict) -> list[dict]:
    """[{term: {fr, en}, beginner: {fr, en}, pro: {fr, en}, card?}], sorted later per language."""
    return yaml.safe_load(resolve(settings["learn"]["glossary"]).read_text(encoding="utf-8"))["terms"]


def load_episodes(settings: dict) -> list[dict]:
    """History lessons: [{id, start, end, title, beginner, pro, cards}]."""
    return yaml.safe_load(resolve(settings["learn"]["episodes"]).read_text(encoding="utf-8"))["episodes"]


def quiz(cards: list[Card], level: str, lang: str) -> list[dict]:
    """Every question of a level: [{card, q, options, answer, why}]."""
    out = []
    for card in cards:
        for item in card.quiz.get(level, []):
            out.append({"card": card.id, **item[lang]})
    return out


def search(cards: list[Card], query: str, level: str, lang: str) -> list[Card]:
    """Cards whose title, key points or text at this level mention every word of the query."""
    words = [w for w in query.lower().split() if w]
    if not words:
        return cards
    found = []
    for card in cards:
        blob = " ".join([card.title[lang], *card.facts[lang], *[str(v) for v in card.text(level, lang).values()]]).lower()
        if all(w in blob for w in words):
            found.append(card)
    return found
