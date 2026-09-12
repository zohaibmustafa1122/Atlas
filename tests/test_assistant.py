"""Tests for the AI assistant (app/ai/assistant.py)."""

from collections.abc import Generator
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.assistant import (
    AssistantAnswer,
    answer_question,
    detect_intent,
    find_mentioned_entities,
)
from app.core.config import Settings
from app.database.models import (
    Base,
    Dataset,
    Organization,
    Person,
    RelationshipEdge,
    Transaction,
)
from app.database.repositories import DatasetRepository, EntityRepository


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture
def dataset_with_data(session: Session) -> Dataset:
    dataset_repo = DatasetRepository(session)
    entity_repo = EntityRepository(session)

    dataset = dataset_repo.create(Dataset(name="Assistant Test Dataset", row_count=10, quality_score=88.0, missing_value_pct=1.0, duplicate_row_pct=0.0))

    org = Organization(name="Acme Corp", dataset_id=dataset.dataset_id)
    entity_repo.bulk_add_organizations([org])

    alice = Person(name="Alice Johnson", organization_id=org.organization_id, dataset_id=dataset.dataset_id)
    bob = Person(name="Bob Williams", organization_id=org.organization_id, dataset_id=dataset.dataset_id)
    entity_repo.bulk_add_persons([alice, bob])

    entity_repo.bulk_add_relationships(
        [
            RelationshipEdge(
                source_entity=alice.person_id,
                target_entity=bob.person_id,
                relationship_type="KNOWS",
                confidence=0.9,
                dataset_id=dataset.dataset_id,
            )
        ]
    )
    entity_repo.bulk_add_transactions(
        [
            Transaction(source=alice.person_id, destination=bob.person_id, amount=100.0, timestamp=datetime(2024, 1, 1), dataset_id=dataset.dataset_id),
            Transaction(source=alice.person_id, destination=bob.person_id, amount=100.0, timestamp=datetime(2024, 1, 2), dataset_id=dataset.dataset_id),
            Transaction(source=alice.person_id, destination=bob.person_id, amount=95.0, timestamp=datetime(2024, 1, 3), dataset_id=dataset.dataset_id),
            Transaction(source=alice.person_id, destination=bob.person_id, amount=500_000.0, timestamp=datetime(2024, 1, 4), dataset_id=dataset.dataset_id),
        ]
    )
    session.commit()
    session.alice_id = alice.person_id
    session.bob_id = bob.person_id
    return dataset


NO_LLM_SETTINGS = Settings(anthropic_api_key=None, openai_api_key=None)


def test_detect_intent_overview_default() -> None:
    assert detect_intent("Tell me about this dataset") == "overview"


def test_detect_intent_most_connected() -> None:
    assert detect_intent("Who is most connected to Alice?") == "most_connected"


def test_detect_intent_shortest_path() -> None:
    assert detect_intent("How is Alice connected to Bob?") == "shortest_path"


def test_detect_intent_anomalies() -> None:
    assert detect_intent("Are there any suspicious transactions?") == "anomalies"


def test_detect_intent_duplicates() -> None:
    assert detect_intent("Are there any duplicate person records?") == "duplicates"


def test_detect_intent_quality() -> None:
    assert detect_intent("What is the data quality score?") == "quality"


def test_find_mentioned_entities_matches_person_name(session: Session, dataset_with_data: Dataset) -> None:
    matches = find_mentioned_entities(session, dataset_with_data.dataset_id, "Who is Alice Johnson connected to?")
    assert any(m["name"] == "Alice Johnson" for m in matches)


def test_find_mentioned_entities_returns_empty_for_no_match(session: Session, dataset_with_data: Dataset) -> None:
    matches = find_mentioned_entities(session, dataset_with_data.dataset_id, "What is the overall summary?")
    assert matches == []


def test_answer_question_overview_uses_fallback_without_api_key(session: Session, dataset_with_data: Dataset) -> None:
    result = answer_question(session, dataset_with_data, "Give me an overview", settings=NO_LLM_SETTINGS)
    assert isinstance(result, AssistantAnswer)
    assert result.mode == "fallback"
    assert result.intent == "overview"
    assert len(result.evidence) > 0
    assert "FACT" in result.answer


def test_answer_question_most_connected_with_named_entity(session: Session, dataset_with_data: Dataset) -> None:
    result = answer_question(session, dataset_with_data, "Who is most connected to Alice Johnson?", settings=NO_LLM_SETTINGS)
    assert result.intent == "most_connected"
    assert any("Alice Johnson" in e for e in result.evidence)


def test_answer_question_shortest_path_between_two_entities(session: Session, dataset_with_data: Dataset) -> None:
    result = answer_question(session, dataset_with_data, "How is Alice Johnson connected to Bob Williams?", settings=NO_LLM_SETTINGS)
    assert result.intent == "shortest_path"
    assert any("Alice Johnson" in e and "Bob Williams" in e for e in result.evidence)


def test_answer_question_anomalies_finds_injected_outlier(session: Session, dataset_with_data: Dataset) -> None:
    result = answer_question(session, dataset_with_data, "Are there any unusual transactions?", settings=NO_LLM_SETTINGS)
    assert result.intent == "anomalies"
    assert any("500,000" in e or "potential anomal" in e.lower() for e in result.evidence)
    assert "fraud" not in result.answer.lower()


def test_answer_question_quality(session: Session, dataset_with_data: Dataset) -> None:
    result = answer_question(session, dataset_with_data, "How clean is this data?", settings=NO_LLM_SETTINGS)
    assert result.intent == "quality"
    assert any("88" in e for e in result.evidence)


def test_answer_question_uses_llm_when_call_succeeds(session: Session, dataset_with_data: Dataset, monkeypatch) -> None:
    import app.ai.assistant as assistant_module

    monkeypatch.setattr(assistant_module, "_call_llm", lambda question, evidence, settings: "FACT: canned LLM response.")
    result = answer_question(session, dataset_with_data, "Give me an overview", settings=NO_LLM_SETTINGS)
    assert result.mode == "llm"
    assert result.answer == "FACT: canned LLM response."


def test_call_llm_returns_none_without_api_key() -> None:
    from app.ai.assistant import _call_llm

    assert _call_llm("question", ["evidence"], NO_LLM_SETTINGS) is None
