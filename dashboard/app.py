"""ATLAS -- Streamlit dashboard (Phase 1 MVP).

Phase 1 scope, per the project roadmap (docs/architecture.md):
  - Upload a CSV/JSON/XLSX file and see a dataset summary.
  - Generate/load the synthetic demo dataset into the database.
  - See a basic overview of what's stored.

Later phases add: data quality scoring, entity resolution, graph
exploration, timeline, map, anomaly detection, and the AI assistant. Their
nav entries are shown below as placeholders so the intended final
navigation structure is visible from Phase 1 onward.
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.database.database import get_session, init_db  # noqa: E402
from app.database.repositories import DatasetRepository, EntityRepository  # noqa: E402
from app.ingestion.csv_loader import load_csv, summarize_dataframe  # noqa: E402
from app.ingestion.excel_loader import load_excel  # noqa: E402
from app.ingestion.json_loader import load_json  # noqa: E402
from app.processing.loading import load_synthetic_dataset  # noqa: E402

st.set_page_config(page_title="ATLAS", layout="wide", initial_sidebar_state="expanded")

settings = get_settings()
init_db()

IMPLEMENTED_PAGES = ["Overview", "Upload Dataset", "Load Synthetic Data", "Datasets"]
FUTURE_PAGES = [
    "Data Quality (Phase 2)",
    "Entity Explorer (Phase 4)",
    "Graph Explorer (Phase 3)",
    "Timeline (Phase 3)",
    "Map (Phase 3)",
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
                    "created_at": d.created_at,
                }
                for d in datasets
            ]
        )
    )


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


if __name__ == "__main__":
    main()
