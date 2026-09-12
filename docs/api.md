# ATLAS — API Reference

## 1. Current scope

ATLAS's primary user interface is the Streamlit dashboard
(`dashboard/app.py`), which talks directly to the database and the
`app/` modules in-process -- there is no network hop between the UI and
the analytics code. The FastAPI app (`app/main.py`) exists as the
scaffold for a proper REST API and currently exposes only a health check,
per the Phase 1 scope defined in `docs/architecture.md`.

This is a deliberate sequencing choice, not an oversight: building out a
full REST API before the underlying analytics (graph, entity resolution,
anomaly detection, NLP, AI assistant) existed would have meant designing
endpoints for capabilities that didn't exist yet, and likely redesigning
them once the real shape of the data became clear through the dashboard.

## 2. Existing endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Basic app info (name, status, environment). |
| GET | `/health` | Health check -- returns `{"status": "healthy"}`. Used for container/deployment liveness checks (see `docker-compose.yml`). |

Run it with:
```bash
uvicorn app.main:app --reload
```
Interactive OpenAPI docs are available at `http://localhost:8000/docs`
(FastAPI generates this automatically).

## 3. What a fuller REST API would need

If ATLAS's dashboard were split from its backend (e.g. to support a
future non-Streamlit frontend, or programmatic access), the natural
endpoint surface -- mapped directly onto functionality that already
exists in `app/` -- would be:

| Planned endpoint | Backing module |
|---|---|
| `POST /datasets` (upload a file) | `app/ingestion/`, `app/processing/cleaning.py`, `app/processing/quality.py` |
| `GET /datasets` / `GET /datasets/{id}` | `app/database/repositories.DatasetRepository` |
| `GET /datasets/{id}/graph` (bounded neighborhood) | `app/graph/queries.get_neighborhood` |
| `GET /datasets/{id}/graph/metrics` | `app/graph/analytics.compute_graph_metrics` |
| `POST /datasets/{id}/entity-resolution` | `app/processing/entity_resolution.resolve_entities` |
| `POST /datasets/{id}/anomalies` | `app/ml/anomaly_detection.*` |
| `POST /datasets/{id}/extract-entities` | `app/nlp/entity_extraction.*` |
| `POST /datasets/{id}/ask` (AI assistant) | `app/ai/assistant.answer_question` |

Every one of these would be a thin routing layer over functions that
already exist and are already tested -- the reason this is listed as
future work rather than built now is that there is no second consumer
(mobile app, external integration, etc.) that needs it yet, and adding an
HTTP layer with no real caller would be speculative complexity the
project's own engineering principles argue against.

## 4. Authentication

Not implemented. ATLAS is designed for local, single-user, academic use
(see `docs/ethics.md`). If deployed for multi-user access, the endpoints
above would need standard API authentication (e.g. an API key or OAuth2
bearer token via FastAPI's built-in security utilities) before being
exposed beyond localhost -- this is explicitly out of scope for the
current academic/demonstration deployment target.
