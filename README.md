# ATLAS — Open Data Intelligence & Decision Support Platform

> A resource-efficient, CPU-only data intelligence platform for exploring
> heterogeneous datasets through entity resolution, graph analytics, and
> anomaly detection. Built as a BS Data Science Final Year Project.

**Status: Phase 1 (MVP) — project setup, database, synthetic data
generator, CSV/JSON/XLSX ingestion, Streamlit dashboard.**

---

## 1. Project overview

ATLAS lets a user upload heterogeneous public or synthetic datasets and
turns them into a connected analytical environment: entities and
relationships are extracted, resolved, stored relationally, modeled as a
graph, and made explorable through an interactive dashboard — with
anomaly detection, NLP, and an evidence-grounded AI assistant layered on
in later phases.

It is deliberately **not** a clone of any proprietary intelligence
platform — no proprietary code, UI, or branding is used or referenced.
Everything here is original, and it operates exclusively on **synthetic or
public data**, never on private individuals' real data.

## 2. Problem statement & motivation

Real-world analytical platforms for connecting heterogeneous data (people,
organizations, events, transactions) into a queryable, graph-aware system
are typically proprietary, expensive, and GPU/cluster-hungry. This project
asks: **how much of that value can be delivered with an open, CPU-only
stack that runs on an 8 GB RAM laptop?** ATLAS is both the applied answer
(a working platform) and the research vehicle (Phase 8 measures where the
resource-efficient approach holds up and where it doesn't).

## 3. Features (by phase)

| Phase | Capability |
|---|---|
| **1 (done)** | Project skeleton, relational schema, synthetic data generator, CSV/JSON/XLSX ingestion with dataset summaries, Streamlit MVP |
| 2 | Data quality scoring, cleaning/normalization pipeline |
| 3 | Graph construction (NetworkX), centrality/PageRank/components, Graph Explorer, timeline, map |
| 4 | Entity resolution (fuzzy matching, similarity scoring) |
| 5 | Anomaly detection (Isolation Forest + statistical baselines) |
| 6 | NLP entity extraction from free text |
| 7 | Retrieval-grounded AI assistant (fact / inference / uncertainty) |
| 8 | Research evaluation: precision/recall/F1, performance benchmarks |
| 9 | Deployment & documentation polish |

## 4. Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full pipeline
diagram, layered module breakdown, and the reasoning behind each
technology choice (SQLite→PostgreSQL, NetworkX→Neo4j, Streamlit-first,
CPU-only ML).

## 5. Technology stack

- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy
- **Database:** SQLite (dev) → PostgreSQL (future, same ORM code)
- **Data processing:** Pandas (Polars planned for hot paths)
- **ML:** scikit-learn (Isolation Forest, Phase 5)
- **Graph:** NetworkX (Phase 3), Neo4j-compatible interface for the future
- **Visualization:** Streamlit, Plotly, Pyvis/Folium (later phases)
- **Testing:** Pytest

## 6. Installation

Requires Python 3.11+ (tested on 3.11).

### Windows (PowerShell / VS Code terminal)

```powershell
git clone <your-fork-url> atlas
cd atlas

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install -r requirements.txt

copy .env.example .env
```

### macOS / Linux

```bash
git clone <your-fork-url> atlas
cd atlas

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
```

## 7. Usage

**1. Generate a synthetic demo dataset** (1,000 / 10,000 / 100,000 records):

```bash
python scripts/generate_data.py --size 1000
```

This writes `persons_1000.csv`, `organizations_1000.csv`,
`locations_1000.csv`, `events_1000.csv`, `relationships_1000.csv`,
`transactions_1000.csv`, plus two ground-truth files
(`ground_truth_entity_resolution_1000.csv`,
`ground_truth_anomalies_1000.csv`) to `data/synthetic/`.

**2. Run the FastAPI backend** (optional for Phase 1 — the dashboard talks
directly to the database):

```bash
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/health`.

**3. Run the Streamlit dashboard:**

```bash
streamlit run dashboard/app.py
```

In the dashboard:
- **Load Synthetic Data** → pick a size → *Load into database*.
- **Upload Dataset** → upload any CSV/JSON/XLSX to see its dataset
  summary (rows, columns, missing values, duplicates, dtypes, processing
  time) without touching the database.
- **Overview** / **Datasets** → see what's loaded.

**4. Run the tests:**

```bash
pytest
```

## 8. Dataset

The demonstration dataset is an entirely **synthetic "global events"**
schema: persons, organizations, locations, events, relationships, and
transactions, generated with [Faker](https://faker.readthedocs.io/). The
generator (`scripts/generate_data.py`) deliberately injects two kinds of
known ground truth:

- **Near-duplicate person records** (e.g. name variants, honorifics,
  typos) with a recorded true identity — used to evaluate entity
  resolution precision/recall in Phase 4/8.
- **Extreme-outlier transaction amounts** — used to evaluate anomaly
  detection precision/recall in Phase 5/8.

No real individual or organization is represented anywhere in this
dataset.

## 9. Database design

See [`docs/database.md`](docs/database.md) for the full ER diagram, table
reference, indexing strategy, and the rationale for each design decision
(including the polymorphic `relationships`/`transactions` association).

## 10. Research methodology (planned, Phase 8)

Research question: *Can resource-efficient graph-based entity resolution
and anomaly detection improve exploratory analysis of heterogeneous
datasets on low-resource computing environments?*

Planned experiments (baseline vs. improved method, at 1,000 / 10,000 /
100,000 records):
- Entity resolution: precision, recall, F1 (baseline fuzzy matching vs.
  multi-feature similarity).
- Anomaly detection: precision, recall, F1, false positive rate
  (statistical baseline vs. Isolation Forest).
- Performance: processing time, memory consumption, graph construction
  time, query response time.

## 11. Limitations (current, Phase 1)

- No data cleaning/normalization pipeline yet (Phase 2).
- No graph construction, entity resolution, anomaly detection, NLP, or AI
  assistant yet — those are Phases 3–7.
- Relationship/transaction referential integrity is enforced in the
  repository layer, not at the database schema level (documented
  trade-off, see `docs/database.md`).
- Tested up to 100,000-record synthetic datasets; larger scales would need
  chunked ingestion and a non-SQLite backend.

## 12. Future work

Neo4j, PostgreSQL, a React frontend, local/RAG-based LLM assistance, and
distributed processing are all documented as optional future extensions
(see `docs/architecture.md`), intentionally deferred until the CPU-only
core is complete and evaluated.

## 13. Ethical considerations

ATLAS is built for **academic research, public-data analysis, and
educational demonstration only**. It explicitly does not implement covert
surveillance, unauthorized tracking, private-person profiling, facial
recognition, or credential collection. All demo data is synthetic and
clearly labeled as such. See [`docs/ethics.md`](docs/ethics.md)
(added in a later phase) for the full ethics statement.

## 14. Contributors

Built by a BS Data Science student as a Final Year Project and scholarship
portfolio piece.

## 15. Project structure

```
atlas/
├── app/            # FastAPI backend: ingestion, processing, database, graph, ml, nlp, ai, api
├── dashboard/      # Streamlit UI
├── data/           # raw / processed / synthetic (gitignored except .gitkeep)
├── docs/           # architecture, database, defense prep, research (as phases land)
├── scripts/        # data generation and experiment scripts
├── tests/          # pytest suite
├── requirements.txt
└── .env.example
```
