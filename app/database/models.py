"""SQLAlchemy ORM models for the ATLAS relational schema.

See docs/database.md for the full ER diagram and rationale behind each
table and design decision (e.g. why relationships/transactions reference
entities polymorphically instead of via a strict foreign key).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def generate_uuid() -> str:
    """Generate a string UUID used as a surrogate primary key."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Dataset(Base):
    """A logical dataset -- one row per upload/generation batch."""

    __tablename__ = "datasets"

    dataset_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_value_pct: Mapped[float] = mapped_column(Float, default=0.0)
    duplicate_row_pct: Mapped[float] = mapped_column(Float, default=0.0)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    sources: Mapped[list["DataSource"]] = relationship(back_populates="dataset")


class DataSource(Base):
    """A physical file ingested as part of a dataset."""

    __tablename__ = "data_sources"

    source_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.dataset_id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(20))
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    dataset: Mapped["Dataset"] = relationship(back_populates="sources")


class Organization(Base):
    """An organization entity (company, NGO, government body, etc.)."""

    __tablename__ = "organizations"

    organization_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.dataset_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Person(Base):
    """A person entity."""

    __tablename__ = "persons"

    person_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=True, index=True
    )
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.dataset_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Location(Base):
    """A physical location (city/country with optional coordinates)."""

    __tablename__ = "locations"

    location_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.dataset_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Event(Base):
    """An event that occurred at a location on a given date."""

    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    date: Mapped[date] = mapped_column(Date)
    location_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("locations.location_id"), nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.dataset_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RelationshipEdge(Base):
    """A relationship (graph edge) between two entities.

    source_entity/target_entity intentionally store a person_id or
    organization_id without a strict FK constraint, since a single column
    cannot reference two different tables in standard SQL. See
    docs/database.md section 3 ("relationships") for the full rationale.
    """

    __tablename__ = "relationships"

    relationship_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    source_entity: Mapped[str] = mapped_column(String(36), index=True)
    target_entity: Mapped[str] = mapped_column(String(36), index=True)
    relationship_type: Mapped[str] = mapped_column(String(100), index=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.dataset_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Transaction(Base):
    """A numerical transaction/transfer between two entities."""

    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    source: Mapped[str] = mapped_column(String(36), index=True)
    destination: Mapped[str] = mapped_column(String(36), index=True)
    amount: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    location_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("locations.location_id"), nullable=True, index=True
    )
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.dataset_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AnalysisRun(Base):
    """A record of a single graph/ML analysis execution (Phases 3-5)."""

    __tablename__ = "analysis_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.dataset_id"), index=True)
    run_type: Mapped[str] = mapped_column(String(100))
    parameters: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Anomaly(Base):
    """A flagged anomaly produced by an analysis run (Phase 5)."""

    __tablename__ = "anomalies"

    anomaly_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("analysis_runs.run_id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    anomaly_score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
