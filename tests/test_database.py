"""Tests for the database models and repository layer.

Uses an isolated in-memory SQLite database per test, independent of the
application's configured DATABASE_URL, so tests never touch a real data
file.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Base, Dataset, Organization, Person, RelationshipEdge
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


def test_create_dataset(session: Session) -> None:
    repo = DatasetRepository(session)
    dataset = repo.create(Dataset(name="Test Dataset", row_count=10, column_count=3))
    session.commit()

    fetched = repo.get(dataset.dataset_id)
    assert fetched is not None
    assert fetched.name == "Test Dataset"


def test_bulk_add_persons_and_count(session: Session) -> None:
    dataset_repo = DatasetRepository(session)
    entity_repo = EntityRepository(session)

    dataset = dataset_repo.create(Dataset(name="People Dataset"))
    entity_repo.bulk_add_persons(
        [
            Person(name="Alice", dataset_id=dataset.dataset_id),
            Person(name="Bob", dataset_id=dataset.dataset_id),
        ]
    )
    session.commit()

    counts = entity_repo.count_by_dataset(dataset.dataset_id)
    assert counts["persons"] == 2
    assert counts["organizations"] == 0


def test_valid_entity_ids_includes_persons_and_organizations(session: Session) -> None:
    dataset_repo = DatasetRepository(session)
    entity_repo = EntityRepository(session)

    dataset = dataset_repo.create(Dataset(name="Entity IDs Dataset"))
    person = Person(name="Alice", dataset_id=dataset.dataset_id)
    org = Organization(name="Acme Corp", dataset_id=dataset.dataset_id)
    entity_repo.bulk_add_persons([person])
    entity_repo.bulk_add_organizations([org])
    session.commit()

    valid_ids = entity_repo.valid_entity_ids(dataset.dataset_id)
    assert person.person_id in valid_ids
    assert org.organization_id in valid_ids


def test_relationship_can_reference_person_or_organization(session: Session) -> None:
    dataset_repo = DatasetRepository(session)
    entity_repo = EntityRepository(session)

    dataset = dataset_repo.create(Dataset(name="Relationship Dataset"))
    person = Person(name="Alice", dataset_id=dataset.dataset_id)
    org = Organization(name="Acme Corp", dataset_id=dataset.dataset_id)
    entity_repo.bulk_add_persons([person])
    entity_repo.bulk_add_organizations([org])
    session.commit()

    entity_repo.bulk_add_relationships(
        [
            RelationshipEdge(
                source_entity=person.person_id,
                target_entity=org.organization_id,
                relationship_type="WORKS_FOR",
                dataset_id=dataset.dataset_id,
            )
        ]
    )
    session.commit()

    counts = entity_repo.count_by_dataset(dataset.dataset_id)
    assert counts["relationships"] == 1


def test_get_session_objects_remain_usable_after_commit_and_close() -> None:
    """Regression test for a real bug found in Phase 9: without
    expire_on_commit=False on the sessionmaker, every ORM attribute
    becomes unreadable (DetachedInstanceError) the instant get_session()'s
    commit() runs, because SQLAlchemy's default behavior expires all
    loaded attributes on commit -- forcing a re-fetch that fails once the
    session is closed. Nearly every dashboard page fetches an object
    inside `with get_session()` and reads its attributes after the block
    exits, so this setting is load-bearing, not cosmetic. See
    docs/defense_questions.md (Phase 9 section).
    """
    import app.database.database as db_module

    original_bind = db_module.SessionLocal.kw.get("bind")
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    db_module.SessionLocal.configure(bind=test_engine)
    try:
        with db_module.get_session() as db_session:
            dataset = Dataset(name="Regression Test", row_count=5)
            db_session.add(dataset)
            db_session.flush()
            dataset_id = dataset.dataset_id

        # db_session is now committed and closed -- reading attributes
        # here must not raise DetachedInstanceError.
        assert dataset.name == "Regression Test"
        assert dataset.row_count == 5
        assert dataset.dataset_id == dataset_id
    finally:
        db_module.SessionLocal.configure(bind=original_bind)
