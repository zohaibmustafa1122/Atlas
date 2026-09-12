"""Lightweight text preprocessing shared by the entity extraction methods.

Kept dependency-free (no spaCy) so the baseline extractor in
entity_extraction.py can run even when spaCy isn't installed.
"""

import re

from app.processing.normalization import normalize_whitespace

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def clean_text(text: str) -> str:
    """Normalize whitespace in free text without altering casing or punctuation
    (NER depends on both: "Ali" vs "ali", "Jan. 5" vs "Jan 5").
    """
    return normalize_whitespace(text)


def split_sentences(text: str) -> list[str]:
    """Naive sentence splitter: break on '.', '!', or '?' followed by whitespace.

    This is a heuristic, not a proper sentence boundary detector (it will
    mis-split on abbreviations like "Dr. Smith"), which is an accepted
    limitation of the lightweight baseline -- see docs/defense_questions.md.
    """
    text = clean_text(text)
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
