"""Excel (.xlsx) ingestion: load the first sheet of a workbook and summarize it.

Reuses the same DatasetSummary shape as csv_loader so the dashboard can
treat every supported file type identically after loading.
"""

import time
from pathlib import Path

import pandas as pd

from app.ingestion.csv_loader import DatasetSummary, summarize_dataframe


def load_excel(file_path: str | Path, sheet_name: str | int = 0, preview_rows: int = 10) -> tuple[pd.DataFrame, DatasetSummary]:
    """Read an Excel file into a DataFrame and compute its summary statistics."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Excel file not found: {file_path}")

    start = time.perf_counter()
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    summary = summarize_dataframe(df, preview_rows=preview_rows)
    summary.processing_time_seconds = time.perf_counter() - start
    return df, summary
