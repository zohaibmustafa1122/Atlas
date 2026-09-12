"""Dataset validation: required-column schema checks and rule-based
invalid-value detection.

Invalid-value detection needs to know what a column is *supposed* to look
like, which a completely generic uploaded CSV doesn't tell us. Rather than
guessing, this module accepts an optional `column_rules` mapping
(column -> "numeric" | "date") describing the expected type of specific
columns; anything not covered by a rule is treated as unconstrained (not
counted as invalid). This is deliberately conservative -- see
docs/defense_questions.md for why a heuristic like this is defensible for
an FYP rather than a limitation to hide.
"""

from dataclasses import dataclass, field

import pandas as pd

ColumnRule = str  # "numeric" | "date"


@dataclass
class ValidationResult:
    """Outcome of validating a dataframe's schema and value types."""

    is_valid: bool
    issues: list[str]
    missing_required_columns: list[str]
    invalid_value_counts: dict[str, int] = field(default_factory=dict)
    invalid_value_pct: float = 0.0


def validate_schema(df: pd.DataFrame, required_columns: list[str] | None = None) -> tuple[bool, list[str], list[str]]:
    """Check that a dataframe is non-empty and has the required columns.

    Returns (is_valid, issues, missing_required_columns).
    """
    issues: list[str] = []
    missing = []

    if df.empty:
        issues.append("Dataset has no rows.")
    if len(df.columns) == 0:
        issues.append("Dataset has no columns.")

    if required_columns:
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            issues.append(f"Missing required columns: {', '.join(missing)}")

    return (len(issues) == 0, issues, missing)


def _count_invalid_numeric(series: pd.Series) -> int:
    non_null = series.dropna()
    coerced = pd.to_numeric(non_null, errors="coerce")
    return int(coerced.isna().sum())


def _count_invalid_date(series: pd.Series) -> int:
    non_null = series.dropna()
    coerced = pd.to_datetime(non_null, errors="coerce")
    return int(coerced.isna().sum())


def detect_invalid_values(df: pd.DataFrame, column_rules: dict[str, ColumnRule] | None = None) -> dict[str, int]:
    """Count values that fail their declared type rule, per column.

    Missing values are never counted as invalid here -- that's what
    missing-value tracking is for. This only flags values that are
    *present* but don't parse as the declared type (e.g. "abc" in a
    numeric column).
    """
    invalid_counts: dict[str, int] = {}
    if not column_rules:
        return invalid_counts

    for column, rule in column_rules.items():
        if column not in df.columns:
            continue
        if rule == "numeric":
            invalid_counts[column] = _count_invalid_numeric(df[column])
        elif rule == "date":
            invalid_counts[column] = _count_invalid_date(df[column])

    return invalid_counts


def validate_dataframe(
    df: pd.DataFrame,
    required_columns: list[str] | None = None,
    column_rules: dict[str, ColumnRule] | None = None,
) -> ValidationResult:
    """Run schema + invalid-value validation and return a combined result."""
    is_valid, issues, missing = validate_schema(df, required_columns)
    invalid_counts = detect_invalid_values(df, column_rules)

    total_checked_cells = sum(df[col].notna().sum() for col in invalid_counts) or 1
    invalid_pct = round(100 * sum(invalid_counts.values()) / total_checked_cells, 2)

    if invalid_counts and sum(invalid_counts.values()) > 0:
        issues.append(f"Found {sum(invalid_counts.values())} value(s) that don't match their expected type.")

    return ValidationResult(
        is_valid=is_valid,
        issues=issues,
        missing_required_columns=missing,
        invalid_value_counts=invalid_counts,
        invalid_value_pct=invalid_pct,
    )
