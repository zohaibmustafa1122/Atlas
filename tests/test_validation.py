"""Tests for schema/value validation (app/processing/validation.py)."""

import pandas as pd

from app.processing.validation import detect_invalid_values, validate_dataframe, validate_schema


def test_validate_schema_passes_for_valid_dataframe() -> None:
    df = pd.DataFrame({"name": ["Alice"], "age": [30]})
    is_valid, issues, missing = validate_schema(df, required_columns=["name", "age"])
    assert is_valid
    assert issues == []
    assert missing == []


def test_validate_schema_flags_missing_required_columns() -> None:
    df = pd.DataFrame({"name": ["Alice"]})
    is_valid, issues, missing = validate_schema(df, required_columns=["name", "age"])
    assert not is_valid
    assert missing == ["age"]
    assert any("age" in issue for issue in issues)


def test_validate_schema_flags_empty_dataframe() -> None:
    df = pd.DataFrame()
    is_valid, issues, _ = validate_schema(df)
    assert not is_valid
    assert len(issues) >= 1


def test_detect_invalid_values_counts_non_numeric_entries() -> None:
    df = pd.DataFrame({"amount": ["100", "abc", "50", None]})
    invalid = detect_invalid_values(df, column_rules={"amount": "numeric"})
    assert invalid["amount"] == 1  # "abc" only; None is missing, not invalid


def test_detect_invalid_values_counts_bad_dates() -> None:
    df = pd.DataFrame({"date": ["2024-01-01", "not-a-date"]})
    invalid = detect_invalid_values(df, column_rules={"date": "date"})
    assert invalid["date"] == 1


def test_detect_invalid_values_without_rules_returns_empty() -> None:
    df = pd.DataFrame({"amount": ["100", "abc"]})
    assert detect_invalid_values(df, None) == {}


def test_validate_dataframe_combines_schema_and_value_checks() -> None:
    df = pd.DataFrame({"amount": ["100", "abc", "50"]})
    result = validate_dataframe(df, required_columns=["amount"], column_rules={"amount": "numeric"})
    assert result.is_valid  # schema is fine; invalid values don't flip is_valid
    assert result.invalid_value_counts["amount"] == 1
    assert result.invalid_value_pct > 0
