# ATLAS — Open Data Intelligence & Decision Support Platform

> A resource-efficient, CPU-only data intelligence platform for exploring
> heterogeneous datasets through entity resolution, graph analytics, and
> anomaly detection. Built as a BS Data Science Final Year Project.

**Status: Phase 5 — project setup, database, synthetic data generator,
CSV/JSON/XLSX ingestion, cleaning/validation, Data Quality Engine, graph
construction & analytics, Graph Explorer, Timeline, Map, entity
resolution, anomaly detection, Streamlit dashboard.**

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
| **2 (done)** | Data Quality Engine (completeness/uniqueness/validity/consistency), cleaning (whitespace, exact duplicates), schema validation |
| **3 (done)** | Graph construction (NetworkX), degree/PageRank/betweenness centrality, connected components, community detection, shortest path, Graph Explorer (search + bounded expand + Pyvis viz), Timeline, Map |
| **4 (done)** | Entity resolution: blocking, baseline (Levenshtein) vs multi-feature (Levenshtein + token Jaccard + TF-IDF cosine) fuzzy matching, confidence-labeled results, precision/recall/F1 against injected ground truth |
| **5 (done)** | Anomaly detection: statistical (robust z-score via median/MAD) vs Isolation Forest on transaction amounts, "potential anomaly" language (never "fraud"), precision/recall/F1 against injected ground truth, persisted to `analysis_runs`/`anomalies` |
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
- **ML:** scikit-learn (TF-IDF/cosine similarity for entity resolution; Isolation Forest for anomaly detection)
- **Graph:** NetworkX, Neo4j-compatible interface for the future
- **Visualization:** Streamlit, Plotly, Pyvis
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
  time), a schema validation check, a cleaning report (duplicates removed,
  whitespace normalized), and a **Data Quality Score** (0-100, with a
  completeness/uniqueness/validity/consistency breakdown). Optionally save
  the cleaned dataset's metadata and quality score to the database.
- **Overview** / **Datasets** → see what's loaded.
- **Graph Explorer** → pick a dataset, compute graph-wide metrics (degree/PageRank/betweenness
  centrality, connected components, density, community detection), search for a person or
  organization, expand its neighborhood a bounded number of hops with an interactive Pyvis
  visualization, and find the shortest path between two entities.
- **Timeline** → filter events by type and date range, see them on a scatter chart and in a table.
- **Map** → see dataset locations on a world map, sized by number of events at each location.
- **Entity Resolution** → find candidate duplicate persons (e.g. "Muhammad Ali" vs "M. Ali"),
  choose baseline (Levenshtein-only) or multi-feature (Levenshtein + token Jaccard + TF-IDF
  cosine) scoring, adjust the similarity threshold, and see confidence-labeled results.
  For the synthetic dataset (which has known injected duplicates), also see a live
  precision/recall/F1 comparison between the two methods.
- **Anomalies** → detect statistically unusual transaction amounts with a statistical
  (robust z-score) or Isolation Forest method, tune the sensitivity, and see confidence
  scores and reasons (always "potential anomaly," never "fraud"). For the synthetic
  dataset, see a live precision/recall/F1 comparison between the two methods.

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

## 11. Limitations (current, Phase 5)

- The Data Quality Engine's "validity" and "consistency" checks are
  heuristics (see `docs/defense_questions.md`), not schema-verified —
  there is no ground-truth schema for an arbitrary uploaded file.
- Cleaning is deliberately conservative: only exact duplicate rows and
  stray whitespace are touched. No imputation, typo correction, or
  type coercion happens automatically.
- Graph edges only reflect links backed by an actual foreign key or
  relationship/transaction row (`WORKS_FOR`, `OCCURRED_AT`, relationship
  types, `TRANSFERRED_TO`) — no `LOCATED_IN` edges for persons, since that
  would require string-matching free-text city/country fields with no
  guarantee of correctness (a Phase 4 entity-resolution concern).
- Betweenness centrality is exact below ~3,000 nodes and sampled
  (approximated) above that; community detection is skipped above the
  same threshold rather than approximated, since there's no similarly
  well-understood sampling method for modularity maximization.
- Entity resolution uses blocking (first-character + last-token keys) to
  stay fast at 100,000-record scale, which trades a small amount of recall
  for tractability — a documented, standard trade-off (see
  `docs/defense_questions.md`), not an oversight.
- The similarity threshold matters a lot: at a permissive threshold both
  methods produce many false positives; the multi-feature method's
  advantage over the baseline is clearest at a stricter threshold (see
  `docs/defense_questions.md` for measured precision/recall/F1 at both).
- Anomaly detection only looks at transaction amount; it does not yet use
  graph structure (e.g. sender/receiver degree) or timing features, so it
  can only catch univariate amount outliers, not multivariate anomalies
  like "unremarkable amount, unusual pair of entities." A measured
  finding worth knowing: on the synthetic dataset, the simple statistical
  baseline actually outperforms Isolation Forest (F1 1.0 vs 0.75), because
  the injected anomalies are pure single-feature extremes — see
  `docs/defense_questions.md` for why that isn't a bug.
- No NLP or AI assistant yet — those are Phases 6–7.
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
