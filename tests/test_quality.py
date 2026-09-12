"""Tests for the Data Quality Engine (app/processing/quality.py)."""

import numpy as np
import pandas as pd

from app.processing.quality import compute_quality_score


def test_perfect_dataframe_scores_100() -> None:
    df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30, 25]})
    breakdown = compute_quality_score(df)
    assert breakdown.overall_score == 100.0
    assert breakdown.completeness == 100.0
    assert breakdown.uniqueness == 100.0
    assert breakdown.validity == 100.0
    assert breakdown.consistency == 100.0


def test_missing_values_reduce_completeness() -> None:
    df = pd.DataFrame({"name": ["Alice", None], "age": [30, 25]})
    breakdown = compute_quality_score(df)
    assert breakdown.completeness < 100.0
    assert breakdown.overall_score < 100.0


def test_duplicate_rows_reduce_uniqueness() -> None:
    df = pd.DataFrame({"name": ["Alice", "Alice"], "age": [30, 30]})
    breakdown = compute_quality_score(df)
    assert breakdown.uniqueness == 50.0


def test_invalid_values_reduce_validity() -> None:
    df = pd.DataFrame({"amount": ["100", "abc", "50", "75"]})
    breakdown = compute_quality_score(df, column_rules={"amount": "numeric"})
    assert breakdown.validity == 75.0


def test_mixed_type_column_reduces_consistency() -> None:
    df = pd.DataFrame({"age": ["30", "twenty-five", "40", "35"], "name": ["a", "b", "c", "d"]})
    breakdown = compute_quality_score(df)
    assert breakdown.consistency < 100.0


def test_empty_dataframe_does_not_crash() -> None:
    df = pd.DataFrame()
    breakdown = compute_quality_score(df)
    assert breakdown.overall_score == 100.0


def test_score_is_weighted_average_within_bounds() -> None:
    df = pd.DataFrame({"a": [1, np.nan, 1], "b": [2, 3, 2]})
    breakdown = compute_quality_score(df)
    assert 0.0 <= breakdown.overall_score <= 100.0
