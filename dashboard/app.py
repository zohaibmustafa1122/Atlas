"""ATLAS -- Streamlit dashboard (Phase 1-7).

Implemented so far, per the project roadmap (docs/architecture.md):
  - Upload a CSV/JSON/XLSX file, see a dataset summary, clean it, and get a
    Data Quality Score with a per-metric breakdown (Phase 2).
  - Generate/load the synthetic demo dataset into the database.
  - See a basic overview of what's stored.
  - Graph Explorer: graph-wide analytics (centrality, PageRank, components,
    community detection), search-and-expand neighborhood visualization, and
    shortest-path finding (Phase 3).
  - Timeline: filterable event browser (Phase 3).
  - Map: geospatial view of locations sized by event count (Phase 3).
  - Entity Resolution: find candidate duplicate persons (fuzzy matching,
    confidence-labeled, never claiming certainty), with a baseline-vs-
    multi-feature precision/recall/F1 comparison against injected ground
    truth when available (Phase 4).
  - Anomalies: statistical vs Isolation Forest outlier detection on
    transaction amounts, labeled "potential anomaly" (never "fraud"), with
    the same baseline-vs-improved evaluation against injected ground truth
    (Phase 5).
  - Text Entity Extraction: baseline regex vs spaCy NER on event
    descriptions, extracting candidate PERSON/ORG/GPE/DATE mentions
    (Phase 6).
  - AI Assistant: retrieval-grounded question answering (intent detection
    -> evidence retrieval from the graph/ML/database modules above -> an
    optional LLM explanation step that must separate FACT from INFERENCE
    from UNCERTAINTY), with a fully working fallback analytical mode when
    no LLM API key is configured (Phase 7).

Phases 8 (research/evaluation) and 9 (deployment/documentation polish)
remain -- see docs/architecture.md for the roadmap.
"""

import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.database.database import get_session, init_db  # noqa: E402
from app.database.models import AnalysisRun, Anomaly, DataSource, Dataset  # noqa: E402
from app.database.repositories import AnalysisRepository, DatasetRepository, EntityRepository  # noqa: E402
from app.graph.analytics import compute_graph_metrics, detect_communities, find_shortest_path  # noqa: E402
from app.graph.builder import build_graph_for_dataset  # noqa: E402
from app.graph.queries import get_neighborhood, list_edge_types  # noqa: E402
from app.graph.visualize import render_graph_html  # noqa: E402
from app.ingestion.csv_loader import load_csv, summarize_dataframe  # noqa: E402
from app.ingestion.excel_loader import load_excel  # noqa: E402
from app.ingestion.json_loader import load_json  # noqa: E402
from app.ml.anomaly_detection import (  # noqa: E402
    detect_anomalies_isolation_forest,
    detect_anomalies_statistical,
    evaluate_against_ground_truth as evaluate_anomalies_against_ground_truth,
    load_ground_truth_anomaly_ids,
)
from app.ai.assistant import answer_question  # noqa: E402
from app.nlp.entity_extraction import extract_entities_for_texts, is_spacy_available  # noqa: E402
from app.processing.cleaning import clean_dataframe  # noqa: E402
from app.processing.entity_resolution import (  # noqa: E402
    evaluate_against_ground_truth as evaluate_entity_resolution_against_ground_truth,
    load_ground_truth_pairs,
    resolve_entities,
)
from app.processing.loading import load_synthetic_dataset  # noqa: E402
from app.processing.quality import compute_quality_score  # noqa: E402
from app.processing.validation import validate_schema  # noqa: E402

st.set_page_config(page_title="ATLAS", layout="wide", initial_sidebar_state="expanded")

settings = get_settings()
init_db()

IMPLEMENTED_PAGES = [
    "Overview",
    "Upload Dataset",
    "Load Synthetic Data",
    "Datasets",
    "Graph Explorer",
    "Timeline",
    "Map",
    "Entity Resolution",
    "Anomalies",
    "Text Entity Extraction",
    "AI Assistant",
]
FUTURE_PAGES: list[str] = []


def render_sidebar() -> str:
    st.sidebar.title("ATLAS")
    st.sidebar.caption("Open Data Intelligence & Decision Support Platform")
    page = st.sidebar.radio("Navigate", IMPLEMENTED_PAGES)
    st.sidebar.markdown("---")
    if FUTURE_PAGES:
        st.sidebar.caption("Coming in later phases:")
        for future_page in FUTURE_PAGES:
            st.sidebar.caption(f"- {future_page}")
        st.sidebar.markdown("---")
    st.sidebar.caption(
        "All data shown is synthetic or user-uploaded for academic demonstration. "
        "ATLAS does not process real private-individual data."
    )
    return page


def render_dataset_summary(summary, preview: list[dict]) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows", f"{summary.row_count:,}")
    col2.metric("Columns", summary.column_count)
    col3.metric("Missing values", f"{summary.missing_value_pct}%")
    col4.metric("Duplicate rows", f"{summary.duplicate_row_pct}%")
    st.caption(f"Processed in {summary.processing_time_seconds:.3f}s")

    with st.expander("Column data types"):
        st.table(pd.DataFrame(summary.dtypes.items(), columns=["column", "dtype"]))

    with st.expander("Missing values per column"):
        st.table(pd.DataFrame(summary.missing_value_counts.items(), columns=["column", "missing_count"]))

    st.subheader("Preview")
    st.dataframe(pd.DataFrame(preview))


def page_overview() -> None:
    st.title("Overview")
    with get_session() as session:
        datasets = DatasetRepository(session).list_all()

    if not datasets:
        st.info("No datasets loaded yet. Use **Upload Dataset** or **Load Synthetic Data** to get started.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Datasets", len(datasets))
    col2.metric("Total rows tracked", f"{sum(d.row_count for d in datasets):,}")
    avg_quality = [d.quality_score for d in datasets if d.quality_score is not None]
    col3.metric("Avg. quality score", f"{sum(avg_quality) / len(avg_quality):.0f}/100" if avg_quality else "N/A")

    st.subheader("Datasets")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "name": d.name,
                    "rows": d.row_count,
                    "columns": d.column_count,
                    "missing_%": d.missing_value_pct,
                    "duplicate_%": d.duplicate_row_pct,
                    "quality_score": d.quality_score,
                    "created_at": d.created_at,
                }
                for d in datasets
            ]
        )
    )


def render_quality_score(df) -> None:
    st.subheader("Data Quality Score")
    breakdown = compute_quality_score(df)
    st.metric("Overall score", f"{breakdown.overall_score:.0f} / 100")
    score_cols = st.columns(4)
    score_cols[0].metric("Completeness", f"{breakdown.completeness:.0f}%")
    score_cols[1].metric("Uniqueness", f"{breakdown.uniqueness:.0f}%")
    score_cols[2].metric("Validity", f"{breakdown.validity:.0f}%")
    score_cols[3].metric("Consistency", f"{breakdown.consistency:.0f}%")
    with st.expander("Why this score?"):
        for line in breakdown.explanation:
            st.write(f"- {line}")
    return breakdown


def page_upload() -> None:
    st.title("Upload Dataset")
    st.caption("Supported formats: CSV, JSON, XLSX. Data is analyzed locally; nothing leaves your machine.")

    uploaded_file = st.file_uploader("Choose a file", type=["csv", "json", "xlsx"])
    if uploaded_file is None:
        return

    suffix = Path(uploaded_file.name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = Path(tmp.name)

    try:
        if suffix == ".csv":
            df, summary = load_csv(tmp_path)
        elif suffix == ".json":
            df, summary = load_json(tmp_path)
        elif suffix == ".xlsx":
            df, summary = load_excel(tmp_path)
        else:
            st.error(f"Unsupported file type: {suffix}")
            return
    finally:
        tmp_path.unlink(missing_ok=True)

    st.success(f"Loaded **{uploaded_file.name}**")
    render_dataset_summary(summary, summary.preview)

    st.markdown("---")
    is_valid, issues, _ = validate_schema(df)
    if issues:
        st.warning("Validation issues:\n" + "\n".join(f"- {issue}" for issue in issues))
    else:
        st.success("Schema validation passed: dataset has rows and columns.")

    cleaned_df, cleaning_report = clean_dataframe(df)
    st.subheader("Cleaning")
    clean_cols = st.columns(3)
    clean_cols[0].metric("Duplicate rows removed", cleaning_report.duplicate_rows_removed)
    clean_cols[1].metric("Whitespace-normalized cells", cleaning_report.whitespace_normalized_cells)
    clean_cols[2].metric("Rows after cleaning", cleaning_report.cleaned_row_count)

    st.markdown("---")
    quality_breakdown = render_quality_score(cleaned_df)

    st.markdown("---")
    if st.button("Save cleaned dataset metadata"):
        with get_session() as session:
            dataset_repo = DatasetRepository(session)
            cleaned_summary = summarize_dataframe(cleaned_df)
            dataset = dataset_repo.create(
                Dataset(
                    name=uploaded_file.name,
                    description="User-uploaded dataset, cleaned and scored by the Data Quality Engine.",
                    row_count=cleaned_summary.row_count,
                    column_count=cleaned_summary.column_count,
                    missing_value_pct=cleaned_summary.missing_value_pct,
                    duplicate_row_pct=cleaned_summary.duplicate_row_pct,
                    quality_score=quality_breakdown.overall_score,
                )
            )
            dataset_repo.add_source(
                DataSource(
                    dataset_id=dataset.dataset_id,
                    original_filename=uploaded_file.name,
                    file_type=suffix.lstrip("."),
                )
            )
        st.success(f"Saved dataset metadata for '{uploaded_file.name}' (id={dataset.dataset_id}).")
        st.caption(
            "Note: only dataset-level metadata and quality metrics are stored at this phase. "
            "Extracting entities/relationships from arbitrary uploaded files is a Phase 4/6 capability."
        )


def page_load_synthetic() -> None:
    st.title("Load Synthetic Data")
    st.caption(
        "Generate a synthetic demo dataset with `python scripts/generate_data.py --size <n>`, "
        "then load it into the database here."
    )

    size = st.selectbox("Dataset size", [1000, 10000, 100000])
    expected_dir = settings.synthetic_data_dir
    persons_file = expected_dir / f"persons_{size}.csv"

    if not persons_file.exists():
        st.warning(
            f"No generated data found for size={size}. Run:\n\n"
            f"```\npython scripts/generate_data.py --size {size}\n```"
        )
        return

    st.success(f"Found synthetic data for size={size} in `{expected_dir}`")

    if st.button("Load into database"):
        with st.spinner("Loading synthetic dataset into the database..."):
            with get_session() as session:
                dataset = load_synthetic_dataset(session, expected_dir, size)
                counts = EntityRepository(session).count_by_dataset(dataset.dataset_id)
        st.success(f"Loaded dataset '{dataset.name}' ({dataset.dataset_id})")
        st.json(counts)


def select_dataset() -> Dataset | None:
    """Shared dataset picker used by the Graph Explorer, Timeline, and Map pages."""
    with get_session() as session:
        datasets = DatasetRepository(session).list_all()

    if not datasets:
        st.info("No datasets loaded yet. Use **Load Synthetic Data** to get started.")
        return None

    options = {f"{d.name} ({d.row_count:,} rows)": d.dataset_id for d in datasets}
    choice = st.selectbox("Dataset", list(options.keys()))
    with get_session() as session:
        return DatasetRepository(session).get(options[choice])


@st.cache_resource(show_spinner="Building graph from database...")
def get_graph_for_dataset(dataset_id: str):
    with get_session() as session:
        return build_graph_for_dataset(session, dataset_id)


def page_graph_explorer() -> None:
    st.title("Graph Explorer")
    st.caption(
        "Entities and relationships modeled as a graph. Large graphs are never rendered in "
        "full -- pick a starting entity and expand outward a bounded number of hops."
    )

    dataset = select_dataset()
    if dataset is None:
        return

    graph = get_graph_for_dataset(dataset.dataset_id)
    if graph.number_of_nodes() == 0:
        st.warning("This dataset has no entities loaded into the graph yet.")
        return

    st.subheader("Graph-wide statistics")
    if st.button("Compute graph metrics"):
        with get_session() as session:
            analysis_repo = AnalysisRepository(session)
            run = analysis_repo.create_run(
                AnalysisRun(dataset_id=dataset.dataset_id, run_type="graph_metrics")
            )
            metrics = compute_graph_metrics(graph)
            analysis_repo.complete_run(run, finished_at=datetime.utcnow())
        st.session_state["graph_metrics"] = metrics

    metrics = st.session_state.get("graph_metrics")
    if metrics:
        cols = st.columns(4)
        cols[0].metric("Nodes", f"{metrics.node_count:,}")
        cols[1].metric("Edges", f"{metrics.edge_count:,}")
        cols[2].metric("Connected components", metrics.connected_components)
        cols[3].metric("Density", metrics.density)

        if metrics.betweenness_approximated:
            st.caption(
                "Betweenness centrality is approximated (sampled) because this graph exceeds "
                "the exact-computation size threshold -- see docs/defense_questions.md."
            )

        top_cols = st.columns(3)
        with top_cols[0]:
            st.write("**Top by degree centrality**")
            st.table(_top_scores_table(graph, metrics.top_degree))
        with top_cols[1]:
            st.write("**Top by PageRank**")
            st.table(_top_scores_table(graph, metrics.top_pagerank))
        with top_cols[2]:
            st.write("**Top by betweenness**")
            st.table(_top_scores_table(graph, metrics.top_betweenness))

        with st.expander("Community detection (greedy modularity)"):
            communities = detect_communities(graph)
            if communities is None:
                st.caption("Skipped: graph is too large for community detection at this resource budget.")
            else:
                st.write(f"Found {len(communities)} communities.")
                for i, community in enumerate(communities[:10]):
                    labels = [graph.nodes[n].get("label", n) for n in community[:15]]
                    st.write(f"Community {i + 1} ({len(community)} members): {', '.join(labels)}")

    st.markdown("---")
    st.subheader("Search & expand")
    query = st.text_input("Search for a person or organization by name")
    node_id = None
    if query:
        with get_session() as session:
            matches = EntityRepository(session).search_entities(dataset.dataset_id, query)
        if matches:
            choice = st.selectbox(
                "Select an entity",
                options=[m["id"] for m in matches],
                format_func=lambda mid: next(f"{m['name']} ({m['type']})" for m in matches if m["id"] == mid),
            )
            node_id = choice
        else:
            st.caption("No matches.")

    if node_id:
        depth = st.slider("Expand degrees", min_value=1, max_value=3, value=1)
        edge_type_options = list_edge_types(graph)
        selected_edge_types = st.multiselect("Filter by relationship type", edge_type_options, default=[])

        neighborhood = get_neighborhood(
            graph, node_id, depth=depth, edge_types=selected_edge_types or None
        )
        st.caption(f"Showing {neighborhood.number_of_nodes()} nodes, {neighborhood.number_of_edges()} edges.")

        html = render_graph_html(neighborhood, highlight_node=node_id)
        components.html(html, height=620, scrolling=False)

        with st.expander("Selected entity metadata"):
            st.json({k: v for k, v in graph.nodes[node_id].items()})

    st.markdown("---")
    st.subheader("Shortest path between two entities")
    path_cols = st.columns(2)
    with path_cols[0]:
        query_a = st.text_input("Entity A", key="path_a_query")
    with path_cols[1]:
        query_b = st.text_input("Entity B", key="path_b_query")

    if query_a and query_b:
        with get_session() as session:
            repo = EntityRepository(session)
            matches_a = repo.search_entities(dataset.dataset_id, query_a, limit=5)
            matches_b = repo.search_entities(dataset.dataset_id, query_b, limit=5)
        if matches_a and matches_b:
            node_a = st.selectbox("Match for A", [m["id"] for m in matches_a], format_func=lambda mid: next(m["name"] for m in matches_a if m["id"] == mid), key="path_a_select")
            node_b = st.selectbox("Match for B", [m["id"] for m in matches_b], format_func=lambda mid: next(m["name"] for m in matches_b if m["id"] == mid), key="path_b_select")
            if st.button("Find shortest path"):
                path = find_shortest_path(graph, node_a, node_b)
                if path is None:
                    st.warning("No path found between these two entities.")
                else:
                    labels = [graph.nodes[n].get("label", n) for n in path]
                    st.success(f"Path length: {len(path) - 1} hop(s)")
                    st.write(" -> ".join(labels))
        else:
            st.caption("No matches for one or both entities.")


def _top_scores_table(graph, scored_nodes: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"entity": graph.nodes[node_id].get("label", node_id), "score": round(score, 4)} for node_id, score in scored_nodes]
    )


def page_timeline() -> None:
    st.title("Timeline")
    dataset = select_dataset()
    if dataset is None:
        return

    with get_session() as session:
        events = EntityRepository(session).list_events(dataset.dataset_id)

    if not events:
        st.info("This dataset has no events.")
        return

    events_df = pd.DataFrame(
        [{"event_id": e.event_id, "event_type": e.event_type, "date": e.date, "description": e.description} for e in events]
    )
    events_df["date"] = pd.to_datetime(events_df["date"])

    col1, col2 = st.columns(2)
    with col1:
        event_types = st.multiselect("Filter by event type", sorted(events_df["event_type"].unique()), default=[])
    with col2:
        min_date, max_date = events_df["date"].min().date(), events_df["date"].max().date()
        date_range = st.slider(
            "Date range", min_value=min_date, max_value=max_date, value=(min_date, max_date)
        )

    filtered = events_df[
        (events_df["date"].dt.date >= date_range[0]) & (events_df["date"].dt.date <= date_range[1])
    ]
    if event_types:
        filtered = filtered[filtered["event_type"].isin(event_types)]

    st.caption(f"Showing {len(filtered)} of {len(events_df)} events.")
    fig = px.scatter(
        filtered.sort_values("date"),
        x="date",
        y="event_type",
        color="event_type",
        hover_data=["description"],
        title="Events over time",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(filtered.sort_values("date"))


def page_map() -> None:
    st.title("Map")
    dataset = select_dataset()
    if dataset is None:
        return

    with get_session() as session:
        repo = EntityRepository(session)
        locations = repo.list_locations(dataset.dataset_id)
        events = repo.list_events(dataset.dataset_id)

    if not locations:
        st.info("This dataset has no locations.")
        return

    event_counts: dict[str, int] = {}
    for event in events:
        if event.location_id:
            event_counts[event.location_id] = event_counts.get(event.location_id, 0) + 1

    locations_df = pd.DataFrame(
        [
            {
                "location_id": loc.location_id,
                "city": loc.city,
                "country": loc.country,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "event_count": event_counts.get(loc.location_id, 0),
            }
            for loc in locations
            if loc.latitude is not None and loc.longitude is not None
        ]
    )

    if locations_df.empty:
        st.info("No locations with coordinates to plot.")
        return

    locations_df["marker_size"] = locations_df["event_count"].clip(lower=1)
    fig = px.scatter_geo(
        locations_df,
        lat="latitude",
        lon="longitude",
        size="marker_size",
        hover_name="city",
        hover_data={"country": True, "event_count": True, "marker_size": False},
        title="Locations (marker size = number of events)",
    )
    # Disable every land/coastline/country/ocean layer: Plotly only needs to
    # fetch world topology (from an external CDN, cdn.plot.ly) to draw those
    # layers. Without this, the map silently renders blank with no error if
    # that fetch fails -- which happens in any network-restricted
    # environment, inconsistent with the rest of ATLAS working fully
    # offline. Markers still position correctly from lat/lon alone, with no
    # external dependency.
    fig.update_geos(
        showland=False,
        showcountries=False,
        showocean=False,
        showlakes=False,
        showrivers=False,
        showcoastlines=False,
        showframe=True,
        framecolor="lightgray",
        bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(locations_df.drop(columns=["marker_size"]).sort_values("event_count", ascending=False))


def page_entity_resolution() -> None:
    st.title("Entity Resolution")
    st.caption(
        "Find person records that may refer to the same real-world identity, despite "
        "different spellings (e.g. \"Muhammad Ali\" vs \"M. Ali\"). Results are always "
        "confidence-labeled -- ATLAS never claims two records definitely ARE the same entity."
    )

    dataset = select_dataset()
    if dataset is None:
        return

    with get_session() as session:
        persons = EntityRepository(session).list_persons(dataset.dataset_id)

    if not persons:
        st.info("This dataset has no person records.")
        return

    st.caption(f"{len(persons):,} person records loaded.")

    col1, col2 = st.columns(2)
    with col1:
        method = st.radio(
            "Method",
            options=["multi_feature", "baseline"],
            format_func=lambda m: "Multi-feature (Levenshtein + token Jaccard + TF-IDF cosine)"
            if m == "multi_feature"
            else "Baseline (Levenshtein ratio only)",
        )
    with col2:
        threshold = st.slider("Minimum similarity threshold", min_value=0.3, max_value=0.95, value=0.70, step=0.05)

    if st.button("Find potential duplicate persons"):
        person_pairs = [(p.person_id, p.name) for p in persons]
        with st.spinner("Blocking and scoring candidate pairs..."):
            candidates = resolve_entities(person_pairs, method=method, threshold=threshold)
        st.session_state["entity_resolution_candidates"] = candidates
        st.session_state["entity_resolution_persons"] = person_pairs

    candidates = st.session_state.get("entity_resolution_candidates")
    if candidates is not None:
        st.subheader(f"Candidate matches ({len(candidates)})")
        if candidates:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "name_a": c.name_a,
                            "name_b": c.name_b,
                            "similarity": c.similarity,
                            "confidence": c.confidence,
                            "reason": c.reason,
                        }
                        for c in candidates
                    ]
                )
            )
        else:
            st.caption("No candidates found at this threshold.")

        size_match = re.search(r"scale=(\d+)", dataset.description or "")
        if size_match:
            ground_truth = load_ground_truth_pairs(settings.synthetic_data_dir, int(size_match.group(1)))
            if ground_truth:
                st.markdown("---")
                st.subheader("Evaluation against known ground truth")
                st.caption(
                    "This dataset was synthetically generated with known duplicate identities "
                    "(see scripts/generate_data.py), so predictions can be scored directly."
                )
                current_eval = evaluate_entity_resolution_against_ground_truth(candidates, ground_truth)
                other_method = "baseline" if method == "multi_feature" else "multi_feature"
                other_candidates = resolve_entities(
                    st.session_state["entity_resolution_persons"], method=other_method, threshold=threshold
                )
                other_eval = evaluate_entity_resolution_against_ground_truth(other_candidates, ground_truth)

                comparison_df = pd.DataFrame(
                    [
                        {"method": method, "precision": current_eval.precision, "recall": current_eval.recall, "f1": current_eval.f1_score},
                        {"method": other_method, "precision": other_eval.precision, "recall": other_eval.recall, "f1": other_eval.f1_score},
                    ]
                )
                st.table(comparison_df)
                st.caption(
                    f"True positives: {current_eval.true_positives}, "
                    f"false positives: {current_eval.false_positives}, "
                    f"false negatives: {current_eval.false_negatives} (for the selected method)."
                )


def page_anomalies() -> None:
    st.title("Anomalies")
    st.caption(
        "Statistically unusual transaction amounts, flagged for human review. A high anomaly "
        "score means \"this transaction looks unusual relative to the rest of this dataset\" -- "
        "it is **not** evidence of fraud or wrongdoing on its own."
    )

    dataset = select_dataset()
    if dataset is None:
        return

    with get_session() as session:
        transactions = EntityRepository(session).list_transactions(dataset.dataset_id)

    if not transactions:
        st.info("This dataset has no transactions.")
        return

    st.caption(f"{len(transactions):,} transactions loaded.")
    transaction_dicts = [
        {
            "transaction_id": t.transaction_id,
            "source": t.source,
            "destination": t.destination,
            "amount": t.amount,
            "timestamp": str(t.timestamp) if t.timestamp else None,
        }
        for t in transactions
    ]

    col1, col2 = st.columns(2)
    with col1:
        method = st.radio(
            "Method",
            options=["isolation_forest", "statistical"],
            format_func=lambda m: "Isolation Forest" if m == "isolation_forest" else "Statistical (robust z-score)",
        )
    with col2:
        if method == "statistical":
            param = st.slider("Z-score threshold", min_value=1.5, max_value=5.0, value=3.0, step=0.5)
        else:
            param = st.slider("Expected outlier proportion (contamination)", min_value=0.001, max_value=0.05, value=0.01, step=0.001)

    if st.button("Detect anomalies"):
        with st.spinner("Scoring transactions..."):
            if method == "statistical":
                results = detect_anomalies_statistical(transaction_dicts, z_threshold=param)
            else:
                results = detect_anomalies_isolation_forest(transaction_dicts, contamination=param)

        with get_session() as session:
            analysis_repo = AnalysisRepository(session)
            run = analysis_repo.create_run(
                AnalysisRun(dataset_id=dataset.dataset_id, run_type=f"anomaly_detection:{method}")
            )
            analysis_repo.add_anomalies(
                [
                    Anomaly(
                        run_id=run.run_id,
                        entity_type="transaction",
                        entity_id=r.transaction_id,
                        anomaly_score=r.anomaly_score,
                        reason=r.reason,
                    )
                    for r in results
                ]
            )
            analysis_repo.complete_run(run, finished_at=datetime.utcnow())

        st.session_state["anomaly_results"] = results
        st.session_state["anomaly_transactions"] = transaction_dicts

    results = st.session_state.get("anomaly_results")
    if results is not None:
        st.subheader(f"Potential anomalies ({len(results)})")
        if results:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "transaction_id": r.transaction_id,
                            "source": r.source,
                            "destination": r.destination,
                            "amount": r.amount,
                            "timestamp": r.timestamp,
                            "anomaly_score": r.anomaly_score,
                            "reason": r.reason,
                        }
                        for r in results
                    ]
                )
            )
        else:
            st.caption("No anomalies found with the current settings.")

        size_match = re.search(r"scale=(\d+)", dataset.description or "")
        if size_match:
            ground_truth = load_ground_truth_anomaly_ids(settings.synthetic_data_dir, int(size_match.group(1)))
            if ground_truth:
                st.markdown("---")
                st.subheader("Evaluation against known ground truth")
                st.caption(
                    "This dataset was synthetically generated with known injected outlier "
                    "transactions (see scripts/generate_data.py), so predictions can be scored directly."
                )
                current_eval = evaluate_anomalies_against_ground_truth(results, ground_truth)
                other_method = "statistical" if method == "isolation_forest" else "isolation_forest"
                other_results = (
                    detect_anomalies_statistical(st.session_state["anomaly_transactions"])
                    if other_method == "statistical"
                    else detect_anomalies_isolation_forest(st.session_state["anomaly_transactions"])
                )
                other_eval = evaluate_anomalies_against_ground_truth(other_results, ground_truth)

                comparison_df = pd.DataFrame(
                    [
                        {"method": method, "precision": current_eval.precision, "recall": current_eval.recall, "f1": current_eval.f1_score},
                        {"method": other_method, "precision": other_eval.precision, "recall": other_eval.recall, "f1": other_eval.f1_score},
                    ]
                )
                st.table(comparison_df)
                st.caption(
                    f"True positives: {current_eval.true_positives}, "
                    f"false positives: {current_eval.false_positives}, "
                    f"false negatives: {current_eval.false_negatives} (for the selected method, at its default parameter)."
                )


def page_text_entity_extraction() -> None:
    st.title("Text Entity Extraction")
    st.caption(
        "Extract candidate people, organizations, locations, and dates from free-text event "
        "descriptions. Extracted mentions are candidates found in text, not verified matches "
        "to the structured Person/Organization records -- linking the two is future work."
    )

    dataset = select_dataset()
    if dataset is None:
        return

    with get_session() as session:
        events = EntityRepository(session).list_events(dataset.dataset_id)

    texts = [(e.event_id, e.description) for e in events if e.description]
    if not texts:
        st.info("This dataset has no event descriptions to extract from.")
        return

    st.caption(f"{len(texts):,} event descriptions available.")
    spacy_ready = is_spacy_available()
    if not spacy_ready:
        st.warning(
            "spaCy model 'en_core_web_sm' is not installed, so only the baseline method is "
            "available. Install it with: `python -m spacy download en_core_web_sm`"
        )

    method_options = ["spacy", "baseline"] if spacy_ready else ["baseline"]
    method = st.radio(
        "Method",
        options=method_options,
        format_func=lambda m: "spaCy NER (PERSON/ORG/GPE/DATE)" if m == "spacy" else "Baseline (regex: capitalized sequences + date patterns)",
    )
    max_texts = st.slider("Max descriptions to process", min_value=10, max_value=min(len(texts), 2000), value=min(len(texts), 200))

    if st.button("Extract entities"):
        with st.spinner(f"Running {method} extraction over {max_texts} descriptions..."):
            records = extract_entities_for_texts(texts, method=method, max_texts=max_texts)
        st.session_state["nlp_records"] = records
        st.session_state["nlp_texts_by_id"] = dict(texts)

    records = st.session_state.get("nlp_records")
    if records is not None:
        st.subheader(f"Extracted mentions ({len(records)})")
        if records:
            results_df = pd.DataFrame(records)
            texts_by_id = st.session_state.get("nlp_texts_by_id", {})
            results_df["description"] = results_df["source_id"].map(
                lambda sid: (texts_by_id.get(sid, "")[:80] + "...") if len(texts_by_id.get(sid, "")) > 80 else texts_by_id.get(sid, "")
            )
            st.dataframe(results_df[["source_id", "entity_text", "label", "description"]])

            st.subheader("Mentions by label")
            label_counts = results_df["label"].value_counts().reset_index()
            label_counts.columns = ["label", "count"]
            fig = px.bar(label_counts, x="label", y="count", title="Extracted entity counts by label")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No entities extracted from the processed descriptions.")


def page_ai_assistant() -> None:
    st.title("AI Assistant")
    st.caption(
        "Ask a question about the selected dataset. Every answer is grounded in evidence "
        "retrieved directly from the database and graph -- the assistant never answers from "
        "general knowledge. If no LLM API key is configured, it still works, using a "
        "deterministic analytical mode built from the same evidence."
    )

    settings_obj = get_settings()
    if settings_obj.anthropic_api_key:
        st.info(f"LLM-assisted mode is available (model: {settings_obj.llm_model}).")
    else:
        st.info(
            "No ANTHROPIC_API_KEY configured -- running in fallback analytical mode "
            "(retrieval-only, no natural-language explanation layer)."
        )

    dataset = select_dataset()
    if dataset is None:
        return

    st.caption("Try: \"Give me an overview\", \"Who is most connected to <name>?\", "
               "\"How is <name> connected to <name>?\", \"Are there any unusual transactions?\", "
               "\"Are there any duplicate person records?\", \"What is the data quality score?\"")

    question = st.text_input("Your question")
    if st.button("Ask") and question:
        with get_session() as session:
            with st.spinner("Retrieving evidence and answering..."):
                result = answer_question(session, dataset, question)
        st.session_state["assistant_result"] = result

    result = st.session_state.get("assistant_result")
    if result is not None:
        mode_label = "LLM-assisted explanation" if result.mode == "llm" else "Fallback analytical mode (no LLM)"
        st.subheader(mode_label)
        st.write(result.answer)

        with st.expander("Evidence used to answer this question"):
            if result.evidence:
                for line in result.evidence:
                    st.write(f"- {line}")
            else:
                st.caption("No evidence was retrieved.")
            st.caption(f"Retrieved via: {', '.join(result.sources)}")
        st.caption(f"Detected intent: `{result.intent}`")


def page_datasets() -> None:
    st.title("Datasets")
    with get_session() as session:
        dataset_repo = DatasetRepository(session)
        entity_repo = EntityRepository(session)
        datasets = dataset_repo.list_all()

        if not datasets:
            st.info("No datasets loaded yet.")
            return

        for dataset in datasets:
            with st.expander(f"{dataset.name} ({dataset.row_count:,} rows)"):
                st.write(f"**Dataset ID:** `{dataset.dataset_id}`")
                st.write(f"**Created:** {dataset.created_at}")
                if dataset.quality_score is not None:
                    st.write(f"**Data Quality Score:** {dataset.quality_score:.0f} / 100")
                counts = entity_repo.count_by_dataset(dataset.dataset_id)
                st.json(counts)


def main() -> None:
    page = render_sidebar()
    if page == "Overview":
        page_overview()
    elif page == "Upload Dataset":
        page_upload()
    elif page == "Load Synthetic Data":
        page_load_synthetic()
    elif page == "Datasets":
        page_datasets()
    elif page == "Graph Explorer":
        page_graph_explorer()
    elif page == "Timeline":
        page_timeline()
    elif page == "Map":
        page_map()
    elif page == "Entity Resolution":
        page_entity_resolution()
    elif page == "Anomalies":
        page_anomalies()
    elif page == "Text Entity Extraction":
        page_text_entity_extraction()
    elif page == "AI Assistant":
        page_ai_assistant()


if __name__ == "__main__":
    main()
