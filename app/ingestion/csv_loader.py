"""CSV ingestion: load a CSV file and compute the dataset summary shown in
the "Dataset Summary" card of the dashboard.

Kept deliberately independent of the database layer -- this module only
reads a file and describes it. Persisting the result is a separate step
(see dashboard/app.py), which keeps the module easy to unit test.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class DatasetSummary:
    """Everything the "Dataset Summary" UI card needs to display."""

    row_count: int
    column_count: int
    columns: list[str]
    dtypes: dict[str, str]
    missing_value_counts: dict[str, int]
    missing_value_pct: float
    duplicate_row_count: int
    duplicate_row_pct: float
    processing_time_seconds: float
    preview: list[dict] = field(default_factory=list)


def load_csv(file_path: str | Path, preview_rows: int = 10) -> tuple[pd.DataFrame, DatasetSummary]:
    """Read a CSV file and compute its summary statistics.

    Args:
        file_path: path to the CSV file on disk.
        preview_rows: number of rows to include in the returned preview.

    Returns:
        A tuple of (dataframe, summary).

    Raises:
        FileNotFoundError: if file_path does not exist.
        pandas.errors.EmptyDataError: if the file has no columns/data.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    start = time.perf_counter()
    df = pd.read_csv(file_path)
    summary = summarize_dataframe(df, preview_rows=preview_rows)
    summary.processing_time_seconds = time.perf_counter() - start
    return df, summary


def summarize_dataframe(df: pd.DataFrame, preview_rows: int = 10) -> DatasetSummary:
    """Compute a DatasetSummary for an already-loaded DataFrame.

    Split out from load_csv so JSON/Excel loaders (and the dashboard's
    "upload any supported file" flow) can reuse the same summary logic.
    """
    row_count = len(df)
    missing_counts = df.isna().sum().to_dict()
    total_cells = row_count * len(df.columns) if row_count and len(df.columns) else 1
    missing_pct = round(100 * sum(missing_counts.values()) / total_cells, 2)

    duplicate_count = int(df.duplicated().sum())
    duplicate_pct = round(100 * duplicate_count / row_count, 2) if row_count else 0.0

    return DatasetSummary(
        row_count=row_count,
        column_count=len(df.columns),
        columns=list(df.columns),
        dtypes={col: str(dtype) for col, dtype in df.dtypes.items()},
        missing_value_counts={col: int(count) for col, count in missing_counts.items()},
        missing_value_pct=missing_pct,
        duplicate_row_count=duplicate_count,
        duplicate_row_pct=duplicate_pct,
        processing_time_seconds=0.0,
        preview=df.head(preview_rows).to_dict(orient="records"),
    )
