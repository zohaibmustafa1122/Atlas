"""Named entity extraction from free text (Phase 6).

Two methods, continuing the baseline-vs-improved pattern from Phases 4-5:

  - "baseline": pure regex/heuristics -- capitalized word sequences as
    generic proper-noun candidates, plus a date pattern. No dependency on
    spaCy, so it always works, but it can't tell a person from an
    organization from a place, and it will misfire on sentence-initial
    capitalization.
  - "spacy": spaCy's small English pipeline (en_core_web_sm, ~12 MB,
    CPU-only), which classifies entities into PERSON / ORG / GPE / DATE /
    etc. using a trained statistical model. This is the "lightweight
    model" the project brief asks for -- explicitly not a large
    transformer.

Extracted entities are NOT automatically linked to the structured
Person/Organization tables. A name found in free text is a *candidate*
mention, not a verified match to an existing entity -- linking the two
would need entity resolution (Phase 4) applied to extraction output, which
is future work, not this phase's job.
"""

import re
from dataclasses import dataclass

from app.nlp.text_processing import clean_text

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
_DATE_RE = re.compile(
    rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s*\d{{4}}\b"
    rf"|\b\d{{1,2}}\s+(?:{_MONTHS})\.?,?\s*\d{{4}}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b",
)
_CAPITALIZED_SEQUENCE_RE = re.compile(r"\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b")
# Common sentence-starting words that are capitalized only because they
# begin a sentence, not because they are proper nouns -- filtering them out
# reduces (but does not eliminate) the baseline's false positive rate.
_COMMON_LEADING_WORDS = {
    "the", "a", "an", "this", "that", "these", "those", "it", "he", "she",
    "they", "we", "i", "in", "on", "at", "after", "before", "during",
}

INTERESTING_SPACY_LABELS = {"PERSON", "ORG", "GPE", "LOC", "DATE", "NORP", "FAC"}

_spacy_model = None
_spacy_load_attempted = False


@dataclass
class ExtractedEntity:
    """A candidate entity mention found in free text."""

    text: str
    label: str
    start_char: int
    end_char: int
    method: str


def _load_spacy_model():
    """Load and cache the spaCy model, tolerating it not being installed."""
    global _spacy_model, _spacy_load_attempted
    if _spacy_load_attempted:
        return _spacy_model
    _spacy_load_attempted = True
    try:
        import spacy

        _spacy_model = spacy.load("en_core_web_sm")
    except (ImportError, OSError):
        _spacy_model = None
    return _spacy_model


def is_spacy_available() -> bool:
    """Whether the spaCy method can actually be used in this environment."""
    return _load_spacy_model() is not None


def extract_entities_baseline(text: str) -> list[ExtractedEntity]:
    """Regex-only extraction: date patterns, plus generic capitalized-sequence
    proper-noun candidates (no category distinction between person/org/place).
    """
    cleaned = clean_text(text)
    if not cleaned:
        return []

    entities: list[ExtractedEntity] = []
    date_spans: list[tuple[int, int]] = []
    for match in _DATE_RE.finditer(cleaned):
        entities.append(
            ExtractedEntity(text=match.group(), label="DATE", start_char=match.start(), end_char=match.end(), method="baseline")
        )
        date_spans.append((match.start(), match.end()))

    for match in _CAPITALIZED_SEQUENCE_RE.finditer(cleaned):
        start, end = match.start(), match.end()
        if any(start < d_end and end > d_start for d_start, d_end in date_spans):
            continue  # already captured as part of a date
        word = match.group()
        if len(word) < 2 or word.lower() in _COMMON_LEADING_WORDS:
            continue
        entities.append(
            ExtractedEntity(text=word, label="PROPER_NOUN", start_char=start, end_char=end, method="baseline")
        )

    return entities


def extract_entities_spacy(text: str) -> list[ExtractedEntity]:
    """NER via spaCy's small English pipeline. Raises if the model isn't installed."""
    model = _load_spacy_model()
    if model is None:
        raise RuntimeError(
            "spaCy model 'en_core_web_sm' is not available. Install it with: "
            "python -m spacy download en_core_web_sm"
        )

    cleaned = clean_text(text)
    if not cleaned:
        return []

    doc = model(cleaned)
    return [
        ExtractedEntity(text=ent.text, label=ent.label_, start_char=ent.start_char, end_char=ent.end_char, method="spacy")
        for ent in doc.ents
        if ent.label_ in INTERESTING_SPACY_LABELS
    ]


def extract_entities(text: str, method: str = "spacy") -> list[ExtractedEntity]:
    """Dispatch to the requested extraction method."""
    if method == "baseline":
        return extract_entities_baseline(text)
    if method == "spacy":
        return extract_entities_spacy(text)
    raise ValueError(f"Unknown method: {method}")


def extract_entities_for_texts(
    texts: list[tuple[str, str]], method: str = "spacy", max_texts: int | None = None
) -> list[dict]:
    """Run extraction over a batch of (id, text) pairs.

    Returns a flat list of {source_id, entity_text, label, method} dicts,
    one per extracted mention -- convenient for building a results
    DataFrame directly.
    """
    if method == "spacy" and not is_spacy_available():
        raise RuntimeError(
            "spaCy model 'en_core_web_sm' is not available. Install it with: "
            "python -m spacy download en_core_web_sm"
        )

    records: list[dict] = []
    items = texts if max_texts is None else texts[:max_texts]
    for source_id, text in items:
        if not text:
            continue
        for entity in extract_entities(text, method=method):
            records.append(
                {
                    "source_id": source_id,
                    "entity_text": entity.text,
                    "label": entity.label,
                    "method": entity.method,
                }
            )
    return records
