"""ATLAS -- Streamlit dashboard (Phase 1-3).

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

Later phases add: entity resolution, anomaly detection, NLP, and the AI
assistant. Their nav entries are shown below as placeholders so the
intended final navigation structure is visible from early on.
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.database.database import get_session, init_db  # noqa: E402
from app.database.models import AnalysisRun, DataSource, Dataset  # noqa: E402
from app.database.repositories import AnalysisRepository, DatasetRepository, EntityRepository  # noqa: E402
from app.graph.analytics import compute_graph_metrics, detect_communities, find_shortest_path  # noqa: E402
from app.graph.builder import build_graph_for_dataset  # noqa: E402
from app.graph.queries import get_neighborhood, list_edge_types  # noqa: E402
from app.graph.visualize import render_graph_html  # noqa: E402
from app.ingestion.csv_loader import load_csv, summarize_dataframe  # noqa: E402
from app.ingestion.excel_loader import load_excel  # noqa: E402
from app.ingestion.json_loader import load_json  # noqa: E402
from app.processing.cleaning import clean_dataframe  # noqa: E402
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
]
FUTURE_PAGES = [
    "Entity Explorer (Phase 4)",
    "Anomalies (Phase 5)",
    "AI Assistant (Phase 7)",
]


def render_sidebar() -> str:
    st.sidebar.title("ATLAS")
    st.sidebar.caption("Open Data Intelligence & Decision Support Platform")
    page = st.sidebar.radio("Navigate", IMPLEMENTED_PAGES)
    st.sidebar.markdown("---")
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
            analysis_repo.complete_run(run, finished_at=run.started_at)
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
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(locations_df.drop(columns=["marker_size"]).sort_values("event_count", ascending=False))


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


if __name__ == "__main__":
    main()
