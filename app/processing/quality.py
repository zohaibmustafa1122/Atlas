"""Data Quality Engine.

Computes a single 0-100 "Data Quality Score" for a dataset from four
sub-metrics, each already meaningful on its own:

  - completeness  : 1 - (missing values / total cells)
  - uniqueness    : 1 - (duplicate rows / total rows)
  - validity      : 1 - (values that fail their declared type rule, if any)
  - consistency   : 1 - (fraction of columns that mix numeric-looking and
                    non-numeric-looking values -- a proxy for inconsistent
                    formatting, since there is no ground-truth schema for
                    an arbitrary uploaded file)

The weighted average of these four is the overall score. Weights are a
deliberate, documented judgement call (see docs/defense_questions.md), not
a fitted parameter -- there is no "correct" weighting without a downstream
task to optimize for, so the weights are chosen to reflect that missing
data is usually the most damaging problem for downstream analysis,
followed by duplication, validity, and formatting consistency.
"""

from dataclasses import dataclass, field

import pandas as pd

from app.processing.validation import ColumnRule, detect_invalid_values

WEIGHTS = {
    "completeness": 0.40,
    "uniqueness": 0.25,
    "validity": 0.20,
    "consistency": 0.15,
}


@dataclass
class QualityBreakdown:
    """The overall score plus every sub-metric that produced it."""

    completeness: float
    uniqueness: float
    validity: float
    consistency: float
    overall_score: float
    explanation: list[str] = field(default_factory=list)


def _completeness(df: pd.DataFrame) -> float:
    total_cells = df.shape[0] * df.shape[1]
    if total_cells == 0:
        return 1.0
    missing_cells = int(df.isna().sum().sum())
    return 1.0 - (missing_cells / total_cells)


def _uniqueness(df: pd.DataFrame) -> float:
    if len(df) == 0:
        return 1.0
    duplicate_rows = int(df.duplicated().sum())
    return 1.0 - (duplicate_rows / len(df))


def _validity(df: pd.DataFrame, column_rules: dict[str, ColumnRule] | None) -> float:
    invalid_counts = detect_invalid_values(df, column_rules)
    if not invalid_counts:
        return 1.0
    checked_cells = sum(df[col].notna().sum() for col in invalid_counts) or 1
    invalid_cells = sum(invalid_counts.values())
    return 1.0 - (invalid_cells / checked_cells)


def _is_mixed_type_column(series: pd.Series) -> bool:
    """A column "mixes representations" if some (not all, not none) of its
    non-null values parse as numeric. E.g. a column containing
    "30", "25", "thirty", "N/A" mixes numeric ages with free text.
    """
    if series.dtype != object:
        return False
    non_null = series.dropna()
    if non_null.empty:
        return False
    numeric_ratio = pd.to_numeric(non_null, errors="coerce").notna().mean()
    return 0 < numeric_ratio < 1


def _consistency(df: pd.DataFrame) -> float:
    if len(df.columns) == 0:
        return 1.0
    mixed_columns = sum(1 for col in df.columns if _is_mixed_type_column(df[col]))
    return 1.0 - (mixed_columns / len(df.columns))


def compute_quality_score(
    df: pd.DataFrame, column_rules: dict[str, ColumnRule] | None = None
) -> QualityBreakdown:
    """Compute the full quality breakdown and weighted overall score for df."""
    completeness = _completeness(df)
    uniqueness = _uniqueness(df)
    validity = _validity(df, column_rules)
    consistency = _consistency(df)

    overall = (
        completeness * WEIGHTS["completeness"]
        + uniqueness * WEIGHTS["uniqueness"]
        + validity * WEIGHTS["validity"]
        + consistency * WEIGHTS["consistency"]
    ) * 100

    explanation = [
        f"Completeness: {completeness * 100:.1f}% of cells are populated (weight {WEIGHTS['completeness']:.0%}).",
        f"Uniqueness: {uniqueness * 100:.1f}% of rows are non-duplicate (weight {WEIGHTS['uniqueness']:.0%}).",
        f"Validity: {validity * 100:.1f}% of type-checked values match their expected type (weight {WEIGHTS['validity']:.0%}).",
        f"Consistency: {consistency * 100:.1f}% of columns use a single consistent representation (weight {WEIGHTS['consistency']:.0%}).",
    ]

    return QualityBreakdown(
        completeness=round(completeness * 100, 2),
        uniqueness=round(uniqueness * 100, 2),
        validity=round(validity * 100, 2),
        consistency=round(consistency * 100, 2),
        overall_score=round(overall, 2),
        explanation=explanation,
    )
