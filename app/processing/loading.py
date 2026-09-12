"""Load synthetic (or already-cleaned) CSV tables into the ATLAS database.

This is the bridge between ingestion (reading files) and the relational
store: it takes a directory of CSVs following the synthetic-data schema
(see scripts/generate_data.py) and creates one Dataset plus all of its
domain rows in a single transaction.
"""

from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.database.models import (
    DataSource,
    Dataset,
    Event,
    Location,
    Organization,
    Person,
    RelationshipEdge,
    Transaction,
)
from app.database.repositories import DatasetRepository, EntityRepository
from app.ingestion.csv_loader import summarize_dataframe


def _parse_date(value: object) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value == "":
        return None
    return pd.to_datetime(value).date()


def _parse_datetime(value: object) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value == "":
        return None
    return pd.to_datetime(value).to_pydatetime()


def _clean(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value == "":
        return None
    return str(value)


def load_synthetic_dataset(
    session: Session, synthetic_dir: str | Path, size: int, dataset_name: str | None = None
) -> Dataset:
    """Load the six synthetic CSVs for a given `size` into the database.

    Expects files named `<table>_<size>.csv` inside `synthetic_dir`, matching
    what scripts/generate_data.py writes.
    """
    synthetic_dir = Path(synthetic_dir)
    dataset_repo = DatasetRepository(session)
    entity_repo = EntityRepository(session)

    persons_df = pd.read_csv(synthetic_dir / f"persons_{size}.csv", dtype=str, keep_default_na=False)
    organizations_df = pd.read_csv(synthetic_dir / f"organizations_{size}.csv", dtype=str, keep_default_na=False)
    locations_df = pd.read_csv(synthetic_dir / f"locations_{size}.csv", dtype=str, keep_default_na=False)
    events_df = pd.read_csv(synthetic_dir / f"events_{size}.csv", dtype=str, keep_default_na=False)
    relationships_df = pd.read_csv(synthetic_dir / f"relationships_{size}.csv", dtype=str, keep_default_na=False)
    transactions_df = pd.read_csv(synthetic_dir / f"transactions_{size}.csv", dtype=str, keep_default_na=False)

    total_rows = sum(
        len(df)
        for df in (persons_df, organizations_df, locations_df, events_df, relationships_df, transactions_df)
    )
    summary = summarize_dataframe(persons_df)

    dataset = dataset_repo.create(
        Dataset(
            name=dataset_name or f"Synthetic Global Events ({size})",
            description=f"Synthetic ATLAS demo dataset generated at scale={size}.",
            row_count=total_rows,
            column_count=len(persons_df.columns),
            missing_value_pct=summary.missing_value_pct,
            duplicate_row_pct=summary.duplicate_row_pct,
        )
    )
    dataset_repo.add_source(
        DataSource(dataset_id=dataset.dataset_id, original_filename=f"synthetic_{size}", file_type="csv")
    )

    organizations = [
        Organization(
            organization_id=row["organization_id"],
            name=row["name"],
            type=_clean(row.get("type")),
            country=_clean(row.get("country")),
            dataset_id=dataset.dataset_id,
        )
        for row in organizations_df.to_dict(orient="records")
    ]
    entity_repo.bulk_add_organizations(organizations)

    persons = [
        Person(
            person_id=row["person_id"],
            name=row["name"],
            aliases=_clean(row.get("aliases")),
            organization_id=_clean(row.get("organization_id")),
            country=_clean(row.get("country")),
            city=_clean(row.get("city")),
            dataset_id=dataset.dataset_id,
        )
        for row in persons_df.to_dict(orient="records")
    ]
    entity_repo.bulk_add_persons(persons)

    locations = [
        Location(
            location_id=row["location_id"],
            city=_clean(row.get("city")),
            country=_clean(row.get("country")),
            latitude=float(row["latitude"]) if _clean(row.get("latitude")) else None,
            longitude=float(row["longitude"]) if _clean(row.get("longitude")) else None,
            dataset_id=dataset.dataset_id,
        )
        for row in locations_df.to_dict(orient="records")
    ]
    entity_repo.bulk_add_locations(locations)

    events = [
        Event(
            event_id=row["event_id"],
            event_type=row["event_type"],
            date=_parse_date(row.get("date")),
            location_id=_clean(row.get("location_id")),
            description=_clean(row.get("description")),
            dataset_id=dataset.dataset_id,
        )
        for row in events_df.to_dict(orient="records")
    ]
    entity_repo.bulk_add_events(events)

    relationships = [
        RelationshipEdge(
            relationship_id=row["relationship_id"],
            source_entity=row["source_entity"],
            target_entity=row["target_entity"],
            relationship_type=row["relationship_type"],
            start_date=_parse_date(row.get("start_date")),
            end_date=_parse_date(row.get("end_date")),
            confidence=float(row["confidence"]) if _clean(row.get("confidence")) else 1.0,
            dataset_id=dataset.dataset_id,
        )
        for row in relationships_df.to_dict(orient="records")
    ]
    entity_repo.bulk_add_relationships(relationships)

    transactions = [
        Transaction(
            transaction_id=row["transaction_id"],
            source=row["source"],
            destination=row["destination"],
            amount=float(row["amount"]),
            timestamp=_parse_datetime(row.get("timestamp")),
            location_id=_clean(row.get("location_id")),
            dataset_id=dataset.dataset_id,
        )
        for row in transactions_df.to_dict(orient="records")
    ]
    entity_repo.bulk_add_transactions(transactions)

    return dataset
