# ATLAS — Database Design

## 1. Design goals

- Normalized relational schema (3NF) as the system of record.
- Every domain entity table carries a stable surrogate primary key
  (`*_id`, UUID string) so records can be referenced from the graph layer,
  from relationships, and from anomaly/analysis records without depending on
  natural keys that may collide (e.g. two different people named "Ali Khan").
- Every table carries `created_at` (and `updated_at` where rows can change)
  so data lineage and processing history can be audited.
- Foreign keys enforce referential integrity between domain tables and
  between domain tables and the metadata tables (`datasets`, `data_sources`,
  `analysis_runs`).

## 2. Entity-Relationship Diagram

```
 datasets                data_sources
 ┌───────────────┐        ┌───────────────┐
 │ dataset_id PK │◄──────┐│ source_id  PK │
 │ name          │       ││ dataset_id FK │───┐
 │ description   │       ││ file_type     │   │
 │ row_count     │       ││ original_name │   │
 │ quality_score │       ││ ingested_at   │   │
 │ created_at    │       │└───────────────┘   │
 └───────┬───────┘       │                    │
         │ dataset_id (FK on every domain row) │
         ▼                                     │
 ┌───────────────┐   ┌───────────────┐   ┌─────▼─────────┐
 │ organizations │   │  locations    │   │   persons      │
 │ organization_id│  │ location_id PK│  │ person_id PK   │
 │ name          │   │ city          │  │ name           │
 │ type          │   │ country       │  │ aliases        │
 │ country       │   │ latitude      │  │ organization_id│──►organizations
 │ dataset_id FK │   │ longitude     │  │ country        │
 └──────┬────────┘   │ dataset_id FK │  │ city           │
        │            └──────┬────────┘  │ dataset_id FK  │
        │                   │           └──────┬─────────┘
        │                   │                  │
        │                   ▼                  │
        │            ┌───────────────┐          │
        │            │    events     │          │
        │            │ event_id   PK │          │
        │            │ event_type    │          │
        │            │ date          │          │
        │            │ location_id FK│──────────┘ (location context)
        │            │ description   │
        │            │ dataset_id FK │
        │            └───────┬───────┘
        │                    │
        ▼                    ▼
 ┌─────────────────────────────────────┐
 │            relationships             │
 │ relationship_id PK                   │
 │ source_entity   (person/org id)      │
 │ target_entity   (person/org id)      │
 │ relationship_type                    │
 │ start_date / end_date                │
 │ confidence                           │
 │ dataset_id FK                        │
 └───────────────────────────────────────┘

 ┌─────────────────────────────────────┐
 │             transactions             │
 │ transaction_id PK                    │
 │ source      (person/org id)          │
 │ destination (person/org id)          │
 │ amount                               │
 │ timestamp                            │
 │ location_id FK                       │
 │ dataset_id FK                        │
 └───────────────────────────────────────┘

 ┌───────────────┐        ┌───────────────┐
 │ analysis_runs │        │   anomalies   │
 │ run_id     PK │◄───────│ anomaly_id PK │
 │ dataset_id FK │        │ run_id     FK │
 │ run_type      │        │ entity_type   │
 │ started_at    │        │ entity_id     │
 │ finished_at   │        │ anomaly_score │
 │ parameters    │        │ reason        │
 └───────────────┘        │ detected_at   │
                           └───────────────┘
```

## 3. Table reference

### `datasets`
One row per uploaded/generated dataset. Tracks summary statistics computed
at ingestion time so the dashboard can show a "Dataset Summary" card without
recomputing it on every page load.

| column | type | notes |
|---|---|---|
| dataset_id | str (UUID) PK | |
| name | str | user-facing label |
| description | str, nullable | |
| row_count | int | |
| column_count | int | |
| missing_value_pct | float | |
| duplicate_row_pct | float | |
| quality_score | float, nullable | 0–100, computed by the data quality engine (Phase 2) |
| created_at | datetime | |

### `data_sources`
One row per physical file ingested into a dataset (a dataset could in
principle be assembled from more than one source file).

| column | type | notes |
|---|---|---|
| source_id | str (UUID) PK | |
| dataset_id | str FK → datasets | |
| original_filename | str | |
| file_type | str | csv / json / xlsx |
| ingested_at | datetime | |

### `persons`
| column | type | notes |
|---|---|---|
| person_id | str (UUID) PK | |
| name | str | |
| aliases | str, nullable | comma-separated known aliases |
| organization_id | str FK → organizations, nullable | |
| country | str, nullable | |
| city | str, nullable | |
| dataset_id | str FK → datasets | |
| created_at | datetime | |

### `organizations`
| column | type | notes |
|---|---|---|
| organization_id | str (UUID) PK | |
| name | str | |
| type | str | company / ngo / government / other |
| country | str, nullable | |
| dataset_id | str FK → datasets | |
| created_at | datetime | |

### `locations`
| column | type | notes |
|---|---|---|
| location_id | str (UUID) PK | |
| city | str, nullable | |
| country | str, nullable | |
| latitude | float, nullable | |
| longitude | float, nullable | |
| dataset_id | str FK → datasets | |
| created_at | datetime | |

### `events`
| column | type | notes |
|---|---|---|
| event_id | str (UUID) PK | |
| event_type | str | |
| date | date | |
| location_id | str FK → locations, nullable | |
| description | str, nullable | |
| dataset_id | str FK → datasets | |
| created_at | datetime | |

### `relationships`
Edges between two entities (person or organization ids, referenced loosely
by id string rather than a strict FK, since either side may be a person or
an organization — see note below).

| column | type | notes |
|---|---|---|
| relationship_id | str (UUID) PK | |
| source_entity | str | person_id or organization_id |
| target_entity | str | person_id or organization_id |
| relationship_type | str | KNOWS / WORKS_FOR / ASSOCIATED_WITH / ... |
| start_date | date, nullable | |
| end_date | date, nullable | |
| confidence | float | 0.0–1.0 |
| dataset_id | str FK → datasets | |
| created_at | datetime | |

> **Design note:** `source_entity`/`target_entity` are not declared as
> database-level foreign keys because they can point at either the `persons`
> or the `organizations` table (a polymorphic association). Referential
> integrity across the two possible tables is enforced in the repository
> layer (`app/database/repositories.py`) and validated by tests, rather than
> at the schema level — a standard, documented trade-off for polymorphic
> associations in a relational schema.

### `transactions`
| column | type | notes |
|---|---|---|
| transaction_id | str (UUID) PK | |
| source | str | person_id or organization_id |
| destination | str | person_id or organization_id |
| amount | float | |
| timestamp | datetime | |
| location_id | str FK → locations, nullable | |
| dataset_id | str FK → datasets | |
| created_at | datetime | |

### `analysis_runs`
Records every graph/ML analysis executed (Phases 3–5), so results are
reproducible and attributable.

| column | type | notes |
|---|---|---|
| run_id | str (UUID) PK | |
| dataset_id | str FK → datasets | |
| run_type | str | e.g. "graph_metrics", "anomaly_detection" |
| parameters | str, nullable | JSON-encoded parameters used |
| started_at | datetime | |
| finished_at | datetime, nullable | |

### `anomalies`
| column | type | notes |
|---|---|---|
| anomaly_id | str (UUID) PK | |
| run_id | str FK → analysis_runs | |
| entity_type | str | person / organization / transaction / event |
| entity_id | str | id of the flagged entity |
| anomaly_score | float | |
| reason | str, nullable | human-readable feature explanation |
| detected_at | datetime | |

## 4. Indexing

- Every primary key is indexed by definition.
- Every foreign key column (`dataset_id`, `organization_id`, `location_id`,
  `run_id`) has a secondary index to keep joins and neighborhood lookups fast
  as datasets grow toward 100,000 rows.
- `persons.name` and `organizations.name` are indexed to support the global
  search feature (Phase 1+ incremental) without a full table scan.

## 5. Why SQLite now, PostgreSQL later

All models are defined once via SQLAlchemy's declarative ORM. The only
engine-specific code lives in `app/core/config.py` (`DATABASE_URL`). SQLite
satisfies Phase 1–4 development entirely locally with zero setup; switching
to PostgreSQL later (for concurrent access, larger datasets, or a real
deployment) requires changing one environment variable and installing a
driver — no model or query code changes.
