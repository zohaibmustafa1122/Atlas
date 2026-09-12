"""Dataset cleaning: whitespace normalization and duplicate removal.

Deliberately conservative for Phase 2 -- it does not guess at missing
values or coerce types (that would silently change the data's meaning).
It only removes noise that is unambiguously noise: leading/trailing
whitespace in string cells, and exact duplicate rows.
"""

from dataclasses import dataclass

import pandas as pd

from app.processing.normalization import normalize_whitespace


@dataclass
class CleaningReport:
    """What the cleaning step actually changed, for display and for logs."""

    original_row_count: int
    cleaned_row_count: int
    duplicate_rows_removed: int
    whitespace_normalized_cells: int


def clean_dataframe(
    df: pd.DataFrame, drop_duplicates: bool = True, strip_whitespace: bool = True
) -> tuple[pd.DataFrame, CleaningReport]:
    """Return a cleaned copy of df plus a report of what changed.

    Args:
        df: input dataframe (not mutated).
        drop_duplicates: if True, drop exact duplicate rows (keeping the first).
        strip_whitespace: if True, normalize whitespace in every string/object column.
    """
    original_row_count = len(df)
    cleaned = df.copy()
    whitespace_normalized_cells = 0

    if strip_whitespace:
        for column in cleaned.select_dtypes(include="object").columns:
            column_values = cleaned[column]
            normalized_values = column_values.map(
                lambda v: normalize_whitespace(v) if isinstance(v, str) else v
            )
            changed = (normalized_values != column_values) & column_values.notna()
            whitespace_normalized_cells += int(changed.sum())
            cleaned[column] = normalized_values

    duplicate_rows_removed = 0
    if drop_duplicates:
        duplicate_mask = cleaned.duplicated()
        duplicate_rows_removed = int(duplicate_mask.sum())
        cleaned = cleaned[~duplicate_mask].reset_index(drop=True)

    report = CleaningReport(
        original_row_count=original_row_count,
        cleaned_row_count=len(cleaned),
        duplicate_rows_removed=duplicate_rows_removed,
        whitespace_normalized_cells=whitespace_normalized_cells,
    )
    return cleaned, report
