"""Tests for the CSV ingestion module."""

from pathlib import Path

import pandas as pd
import pytest

from app.ingestion.csv_loader import load_csv, summarize_dataframe


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    df = pd.DataFrame(
        {
            "name": ["Alice", "Bob", "Alice", None],
            "age": [30, 25, 30, 40],
        }
    )
    path = tmp_path / "sample.csv"
    df.to_csv(path, index=False)
    return path


def test_load_csv_reports_correct_row_and_column_counts(sample_csv: Path) -> None:
    _, summary = load_csv(sample_csv)
    assert summary.row_count == 4
    assert summary.column_count == 2
    assert summary.columns == ["name", "age"]


def test_load_csv_detects_missing_values(sample_csv: Path) -> None:
    _, summary = load_csv(sample_csv)
    assert summary.missing_value_counts["name"] == 1
    assert summary.missing_value_pct > 0


def test_load_csv_detects_duplicate_rows(sample_csv: Path) -> None:
    _, summary = load_csv(sample_csv)
    assert summary.duplicate_row_count == 1


def test_load_csv_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_csv("does_not_exist.csv")


def test_summarize_dataframe_with_no_missing_or_duplicates() -> None:
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    summary = summarize_dataframe(df)
    assert summary.missing_value_pct == 0.0
    assert summary.duplicate_row_count == 0
    assert summary.row_count == 3
