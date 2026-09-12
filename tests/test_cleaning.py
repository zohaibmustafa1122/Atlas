"""Tests for the cleaning pipeline (app/processing/cleaning.py)."""

import pandas as pd

from app.processing.cleaning import clean_dataframe
from app.processing.normalization import normalize_string, normalize_whitespace, strip_punctuation


def test_clean_dataframe_removes_exact_duplicates() -> None:
    df = pd.DataFrame({"name": ["Alice", "Bob", "Alice"], "age": [30, 25, 30]})
    cleaned, report = clean_dataframe(df)
    assert len(cleaned) == 2
    assert report.duplicate_rows_removed == 1
    assert report.original_row_count == 3
    assert report.cleaned_row_count == 2


def test_clean_dataframe_normalizes_whitespace() -> None:
    df = pd.DataFrame({"name": ["  Alice  ", "Bob   Smith"]})
    cleaned, report = clean_dataframe(df)
    assert cleaned.loc[0, "name"] == "Alice"
    assert cleaned.loc[1, "name"] == "Bob Smith"
    assert report.whitespace_normalized_cells == 2


def test_clean_dataframe_can_skip_duplicate_removal() -> None:
    df = pd.DataFrame({"name": ["Alice", "Alice"]})
    cleaned, report = clean_dataframe(df, drop_duplicates=False)
    assert len(cleaned) == 2
    assert report.duplicate_rows_removed == 0


def test_normalize_whitespace_collapses_runs() -> None:
    assert normalize_whitespace("Alice    Smith  ") == "Alice Smith"


def test_strip_punctuation_removes_symbols() -> None:
    assert strip_punctuation("M. Ali!") == "M Ali"


def test_normalize_string_full_pipeline() -> None:
    assert normalize_string("  Mr. Muhammad Ali!  ") == "mr muhammad ali"


def test_normalize_string_handles_none() -> None:
    assert normalize_string(None) == ""
