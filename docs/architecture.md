# ATLAS — System Architecture

## 1. Overview

ATLAS is a modular data intelligence and decision-support platform. It ingests
heterogeneous datasets (CSV/JSON/Excel), cleans and validates them, resolves
entities, builds a graph of entities and relationships, and exposes analytics,
visualization, and (optionally) LLM-assisted explanation on top of that graph.

The system is designed to run entirely on a CPU-only laptop with 8 GB RAM.
Every architectural decision below is made with that constraint first, and
with "swap in a bigger component later" as a second-order goal.

## 2. High-level pipeline

```
DATA INGESTION
     │
     ▼
DATA VALIDATION  ──► data quality score
     │
     ▼
DATA CLEANING / NORMALIZATION
     │
     ▼
ENTITY EXTRACTION (NLP, Phase 6)
     │
     ▼
ENTITY RESOLUTION (fuzzy matching, Phase 4)
     │
     ▼
RELATIONAL STORAGE (SQLite → PostgreSQL later)
     │
     ▼
GRAPH CONSTRUCTION (NetworkX → Neo4j later)
     │
     ▼
ANALYTICS (centrality, anomaly detection, clustering)
     │
     ▼
VISUALIZATION (Streamlit + Plotly + Pyvis + Folium)
     │
     ▼
OPTIONAL AI ASSISTANT (retrieval-grounded explanation)
```

Every stage produces artifacts that the next stage consumes; no stage is
required to hold the entire dataset in memory at once where avoidable.

## 3. Layered architecture

| Layer | Responsibility | Phase |
|---|---|---|
| `app/ingestion` | Read CSV/JSON/XLSX, detect schema, produce a raw preview | 1 |
| `app/processing` | Cleaning, validation, normalization, entity resolution | 1–4 |
| `app/database` | SQLAlchemy models, session management, repositories | 1 |
| `app/graph` | Build a NetworkX graph from relational data, run graph analytics | 3 |
| `app/ml` | Anomaly detection, clustering, evaluation metrics | 5 |
| `app/nlp` | Entity extraction from free text | 6 |
| `app/ai` | Retrieval-grounded assistant (fact / inference / uncertainty) | 7 |
| `app/api` | FastAPI routes exposing the above to any frontend | 1+ |
| `dashboard` | Streamlit UI: the primary user-facing surface for the MVP | 1 |

Each layer only depends on layers above it in this table (e.g. `graph`
depends on `database`, never the reverse). This keeps the codebase testable
in isolation and keeps any single module from becoming a dumping ground.

## 4. Why these technology choices

- **SQLite → PostgreSQL**: SQLAlchemy's ORM abstracts the engine. SQLite
  needs zero setup for a student laptop; switching to PostgreSQL later is a
  one-line change to `DATABASE_URL` because no code uses SQLite-specific
  syntax.
- **NetworkX → Neo4j**: NetworkX runs in-process, in Python, with no server —
  ideal for graphs of thousands to low tens-of-thousands of nodes on 8 GB RAM.
  The graph builder (`app/graph/builder.py`) produces a graph object from
  relational rows; a future Neo4j backend would implement the same interface
  without touching callers.
- **Streamlit over React**: Streamlit gets a usable, interactive UI running in
  hours, not weeks, letting effort go into the data science instead of
  frontend plumbing. A React frontend remains a possible future extension
  once the API is stable.
- **Pandas (Phase 1) with an eye toward Polars**: Pandas is more ubiquitous
  and better documented for a first pass; Polars can be introduced later for
  specific hot paths (e.g. cleaning 100k-row datasets) without a rewrite,
  since ingestion functions return plain DataFrames/records at their
  boundaries.
- **Isolation Forest over deep learning**: CPU-friendly, well understood,
  works with small-to-medium tabular data, and easy to explain in an FYP
  defense.

## 5. Performance strategy for low-resource hardware

- Ingestion reads files with explicit dtypes where possible and never keeps
  more than one full copy of a DataFrame in memory at a time.
- Large graphs are never rendered in full: the Graph Explorer (Phase 3+)
  samples, filters, or expands neighborhoods on demand instead of drawing
  every node.
- Expensive computations (graph metrics, anomaly scores) are cached per
  dataset/analysis run rather than recomputed on every page interaction.
- The synthetic data generator supports 1,000 / 10,000 / 100,000-record
  datasets specifically so performance can be measured at increasing scale
  rather than assumed.

## 6. Phase roadmap

1. **Phase 1 (this phase)** — project skeleton, database schema, synthetic
   data generator, CSV ingestion, Streamlit MVP.
2. **Phase 2** — data quality engine, cleaning/normalization pipeline for
   uploaded datasets, dataset metadata tracking.
3. **Phase 3** — graph construction from relational data, graph analytics
   (centrality, PageRank, components), Graph Explorer UI.
4. **Phase 4** — entity resolution (fuzzy matching, similarity scoring).
5. **Phase 5** — anomaly detection (Isolation Forest + statistical baselines).
6. **Phase 6** — NLP entity extraction from free text fields.
7. **Phase 7** — AI assistant (retrieval-grounded, fact/inference/uncertainty).
8. **Phase 8** — research/evaluation: precision/recall/F1, performance
   benchmarks across dataset sizes, baseline comparisons.
9. **Phase 9** — deployment and documentation polish.

Each phase must leave the application runnable end-to-end; no phase depends
on an unfinished future phase.
