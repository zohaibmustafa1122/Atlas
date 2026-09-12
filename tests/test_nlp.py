"""Tests for NLP text processing and entity extraction (app/nlp/)."""

import pytest

from app.nlp.entity_extraction import (
    extract_entities,
    extract_entities_baseline,
    extract_entities_for_texts,
    extract_entities_spacy,
    is_spacy_available,
)
from app.nlp.text_processing import clean_text, split_sentences

SPACY_AVAILABLE = is_spacy_available()


def test_clean_text_normalizes_whitespace() -> None:
    assert clean_text("Alice   met   Bob.") == "Alice met Bob."


def test_split_sentences_splits_on_terminal_punctuation() -> None:
    sentences = split_sentences("Alice met Bob. They discussed the merger! Then Carol arrived.")
    assert len(sentences) == 3
    assert sentences[0] == "Alice met Bob."


def test_split_sentences_handles_empty_text() -> None:
    assert split_sentences("") == []


def test_baseline_extracts_date_pattern() -> None:
    entities = extract_entities_baseline("The meeting happened on January 5, 2024 in Berlin.")
    dates = [e for e in entities if e.label == "DATE"]
    assert len(dates) == 1
    assert "January 5, 2024" in dates[0].text


def test_baseline_extracts_capitalized_sequences_as_proper_nouns() -> None:
    entities = extract_entities_baseline("Muhammad Ali visited Acme Corp.")
    proper_nouns = {e.text for e in entities if e.label == "PROPER_NOUN"}
    assert "Muhammad Ali" in proper_nouns
    assert "Acme Corp" in proper_nouns


def test_baseline_filters_common_leading_words() -> None:
    entities = extract_entities_baseline("The meeting was long.")
    proper_nouns = {e.text for e in entities if e.label == "PROPER_NOUN"}
    assert "The" not in proper_nouns


def test_baseline_handles_empty_text() -> None:
    assert extract_entities_baseline("") == []


def test_baseline_does_not_double_count_dates_as_proper_nouns() -> None:
    entities = extract_entities_baseline("The event occurred on March 3, 2023.")
    march_mentions = [e for e in entities if "March" in e.text]
    # "March" should only appear once, as part of the DATE entity
    assert len(march_mentions) == 1
    assert march_mentions[0].label == "DATE"


def test_extract_entities_dispatches_to_baseline() -> None:
    entities = extract_entities("Bob Smith works at Acme Corp.", method="baseline")
    assert all(e.method == "baseline" for e in entities)


def test_extract_entities_rejects_unknown_method() -> None:
    with pytest.raises(ValueError):
        extract_entities("text", method="not_a_real_method")


def test_extract_entities_for_texts_with_baseline() -> None:
    texts = [("e1", "Alice Johnson met Bob Williams."), ("e2", "")]
    records = extract_entities_for_texts(texts, method="baseline")
    assert all(r["source_id"] == "e1" for r in records)  # e2 has no text, contributes nothing
    assert len(records) > 0


@pytest.mark.skipif(not SPACY_AVAILABLE, reason="spaCy model not installed")
def test_spacy_classifies_person_org_location() -> None:
    entities = extract_entities_spacy("Muhammad Ali met with representatives from Acme Corp in Berlin.")
    labels = {(e.text, e.label) for e in entities}
    assert any(text == "Muhammad Ali" and label == "PERSON" for text, label in labels)
    assert any(label == "ORG" for _, label in labels)
    assert any(label == "GPE" for _, label in labels)


@pytest.mark.skipif(not SPACY_AVAILABLE, reason="spaCy model not installed")
def test_spacy_extracts_dates() -> None:
    entities = extract_entities_spacy("The summit took place on January 5, 2024.")
    assert any(e.label == "DATE" for e in entities)


@pytest.mark.skipif(not SPACY_AVAILABLE, reason="spaCy model not installed")
def test_extract_entities_for_texts_with_spacy() -> None:
    texts = [("e1", "Alice Johnson works at Acme Corp in Paris.")]
    records = extract_entities_for_texts(texts, method="spacy")
    assert any(r["label"] == "PERSON" for r in records)
