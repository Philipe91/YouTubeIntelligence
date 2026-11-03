"""Termos de títulos. Títulos externos são apenas dados: viram tokens para contagem."""
from __future__ import annotations

import re
import unicodedata

STOPWORDS = frozenset(
    """a o as os um uma uns umas de do da dos das em no na nos nas por para pra com sem e ou que se
    sobre entre como mais menos muito sua seu suas seus ao aos à às é foi era são ser the of in on at to for with
    and or an is was are be by from how why what when who this that it its you your my el la los las
    un una unos unas del en por para con sin y o que como es su sus al lo se fue""".split()
)
_TOKEN = re.compile(r"[^\W\d_]{2,}|\d{3,4}", re.UNICODE)


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokens(text: str) -> list[str]:
    return [token for token in _TOKEN.findall(normalize(text)) if token not in STOPWORDS]


def terms(text: str) -> set[str]:
    """Palavras e pares de palavras consecutivas."""
    words = tokens(text)
    return set(words) | {f"{left} {right}" for left, right in zip(words, words[1:])}
