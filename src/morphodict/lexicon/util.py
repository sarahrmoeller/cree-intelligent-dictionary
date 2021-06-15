import unicodedata
from unicodedata import normalize

EXTRA_REPLACEMENTS = {"ł": "l", "Ł": "L", "ø": "o", "Ø": "O"}


def strip_accents_for_search_lookups(s: str) -> str:
    """Remove accents from characters for approximate search"""
    return "".join(
        EXTRA_REPLACEMENTS.get(c, c)
        for c in normalize("NFD", s)
        if unicodedata.combining(c) == 0
    )
