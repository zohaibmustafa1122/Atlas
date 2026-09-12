"""JSON ingestion: load a JSON file (array of records) and summarize it.

Reuses the same DatasetSummary shape as csv_loader so the dashboard can
treat every supported file type identically after loading.
"""

import time
from pathlib import Path

import pandas as pd

from app.ingestion.csv_loader import DatasetSummary, summarize_dataframe


def load_json(file_path: str | Path, preview_rows: int = 10) -> tuple[pd.DataFrame, DatasetSummary]:
    """Read a JSON file (list of objects, or {"records": [...]}) into a DataFrame."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"JSON file not found: {file_path}")

    start = time.perf_counter()
    df = pd.read_json(file_path)
    summary = summarize_dataframe(df, preview_rows=preview_rows)
    summary.processing_time_seconds = time.perf_counter() - start
    return df, summary
