"""Generic string normalization helpers.

Used by the cleaning pipeline (Phase 2) and, later, by entity resolution
(Phase 4), which needs the same "is this basically the same string"
normalization before fuzzy matching. Kept dependency-free (no pandas) so
it is trivial to unit test and reuse.
"""

import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^\w\s]")


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace to a single space and strip the ends."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize_case(text: str) -> str:
    """Lowercase text (case-insensitive comparison is the common case)."""
    return text.lower()


def strip_punctuation(text: str) -> str:
    """Remove punctuation, keeping word characters and whitespace."""
    return _PUNCTUATION_RE.sub("", text)


def strip_accents(text: str) -> str:
    """Remove diacritics (e.g. 'Muhämmad' -> 'Muhammad')."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_string(text: str | None) -> str:
    """Apply the full normalization pipeline: accents -> case -> punctuation -> whitespace.

    This is the canonical "normalized form" used whenever two strings need
    to be compared for likely equivalence (cleaning duplicate detection now,
    entity resolution in Phase 4).
    """
    if text is None:
        return ""
    text = strip_accents(str(text))
    text = normalize_case(text)
    text = strip_punctuation(text)
    text = normalize_whitespace(text)
    return text
