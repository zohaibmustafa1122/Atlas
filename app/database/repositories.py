"""Repository layer: encapsulates queries against the ORM models.

Keeping queries here (rather than scattering session.query calls through
the dashboard/API code) is what lets the polymorphic source_entity /
target_entity columns on RelationshipEdge and Transaction be validated in
one place instead of re-implemented everywhere they're used.
"""

from sqlalchemy.orm import Session

from app.database.models import (
    Anomaly,
    AnalysisRun,
    DataSource,
    Dataset,
    Event,
    Location,
    Organization,
    Person,
    RelationshipEdge,
    Transaction,
)


class DatasetRepository:
    """Queries and mutations for the `datasets` / `data_sources` tables."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, dataset: Dataset) -> Dataset:
        self.session.add(dataset)
        self.session.flush()
        return dataset

    def add_source(self, source: DataSource) -> DataSource:
        self.session.add(source)
        self.session.flush()
        return source

    def get(self, dataset_id: str) -> Dataset | None:
        return self.session.get(Dataset, dataset_id)

    def list_all(self) -> list[Dataset]:
        return list(self.session.query(Dataset).order_by(Dataset.created_at.desc()).all())


class EntityRepository:
    """Bulk-insert and lookup helpers for the domain entity tables.

    Bulk methods take plain lists of ORM objects rather than DataFrames so
    this layer stays independent of whichever ingestion library
    (pandas/Polars) produced the rows.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def bulk_add_persons(self, persons: list[Person]) -> None:
        self.session.add_all(persons)
        self.session.flush()

    def bulk_add_organizations(self, organizations: list[Organization]) -> None:
        self.session.add_all(organizations)
        self.session.flush()

    def bulk_add_locations(self, locations: list[Location]) -> None:
        self.session.add_all(locations)
        self.session.flush()

    def bulk_add_events(self, events: list[Event]) -> None:
        self.session.add_all(events)
        self.session.flush()

    def bulk_add_relationships(self, relationships: list[RelationshipEdge]) -> None:
        self.session.add_all(relationships)
        self.session.flush()

    def bulk_add_transactions(self, transactions: list[Transaction]) -> None:
        self.session.add_all(transactions)
        self.session.flush()

    def valid_entity_ids(self, dataset_id: str) -> set[str]:
        """Return the union of person_id and organization_id values for a dataset.

        Used to validate that relationships/transactions reference an
        entity that actually exists in that dataset, since the
        source_entity/target_entity columns are not enforced by a database
        foreign key (see docs/database.md).
        """
        person_ids = {
            row[0]
            for row in self.session.query(Person.person_id).filter(Person.dataset_id == dataset_id).all()
        }
        org_ids = {
            row[0]
            for row in self.session.query(Organization.organization_id)
            .filter(Organization.dataset_id == dataset_id)
            .all()
        }
        return person_ids | org_ids

    def search_entities(self, dataset_id: str, query: str, limit: int = 25) -> list[dict]:
        """Case-insensitive substring search over person and organization names.

        Done as a SQL LIKE query (rather than scanning an in-memory graph)
        so search stays fast at the 100,000-row scale, where iterating every
        node in Python would be noticeably slower.
        """
        pattern = f"%{query}%"
        person_matches = (
            self.session.query(Person)
            .filter(Person.dataset_id == dataset_id, Person.name.ilike(pattern))
            .limit(limit)
            .all()
        )
        org_matches = (
            self.session.query(Organization)
            .filter(Organization.dataset_id == dataset_id, Organization.name.ilike(pattern))
            .limit(limit)
            .all()
        )
        results = [
            {"id": p.person_id, "name": p.name, "type": "Person"} for p in person_matches
        ] + [{"id": o.organization_id, "name": o.name, "type": "Organization"} for o in org_matches]
        return results[:limit]

    def list_persons(self, dataset_id: str) -> list[Person]:
        return list(self.session.query(Person).filter(Person.dataset_id == dataset_id).all())

    def list_transactions(self, dataset_id: str) -> list[Transaction]:
        return list(self.session.query(Transaction).filter(Transaction.dataset_id == dataset_id).all())

    def list_events(self, dataset_id: str) -> list[Event]:
        return list(self.session.query(Event).filter(Event.dataset_id == dataset_id).all())

    def list_locations(self, dataset_id: str) -> list[Location]:
        return list(self.session.query(Location).filter(Location.dataset_id == dataset_id).all())

    def get_person(self, person_id: str) -> Person | None:
        return self.session.get(Person, person_id)

    def get_organization(self, organization_id: str) -> Organization | None:
        return self.session.get(Organization, organization_id)

    def count_by_dataset(self, dataset_id: str) -> dict[str, int]:
        """Return entity counts for a dataset, for dashboard summary cards."""
        return {
            "persons": self.session.query(Person).filter(Person.dataset_id == dataset_id).count(),
            "organizations": self.session.query(Organization)
            .filter(Organization.dataset_id == dataset_id)
            .count(),
            "locations": self.session.query(Location).filter(Location.dataset_id == dataset_id).count(),
            "events": self.session.query(Event).filter(Event.dataset_id == dataset_id).count(),
            "relationships": self.session.query(RelationshipEdge)
            .filter(RelationshipEdge.dataset_id == dataset_id)
            .count(),
            "transactions": self.session.query(Transaction)
            .filter(Transaction.dataset_id == dataset_id)
            .count(),
        }


class AnalysisRepository:
    """Queries and mutations for `analysis_runs` / `anomalies` (Phases 3-5)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(self, run: AnalysisRun) -> AnalysisRun:
        self.session.add(run)
        self.session.flush()
        return run

    def complete_run(self, run: AnalysisRun, finished_at) -> AnalysisRun:
        run.finished_at = finished_at
        self.session.flush()
        return run

    def runs_for_dataset(self, dataset_id: str) -> list[AnalysisRun]:
        return list(
            self.session.query(AnalysisRun)
            .filter(AnalysisRun.dataset_id == dataset_id)
            .order_by(AnalysisRun.started_at.desc())
            .all()
        )

    def add_anomalies(self, anomalies: list[Anomaly]) -> None:
        self.session.add_all(anomalies)
        self.session.flush()

    def anomalies_for_run(self, run_id: str) -> list[Anomaly]:
        return list(self.session.query(Anomaly).filter(Anomaly.run_id == run_id).all())
