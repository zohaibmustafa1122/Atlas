"""Anomaly detection for transaction amounts.

Two methods, for the baseline-vs-improved comparison described in the
project brief:

  - "statistical": a robust z-score using the median and median absolute
    deviation (MAD) rather than the mean and standard deviation. This
    matters specifically because the data being scored already contains
    the outliers being searched for -- a handful of extreme values would
    otherwise inflate the mean/std enough to mask themselves. Median/MAD
    barely move when a few values are extreme, which is the whole point
    of a "robust" statistic.
  - "isolation_forest": scikit-learn's IsolationForest, which isolates
    points by randomly partitioning the feature space -- outliers take
    fewer partitions to isolate, which is what its score measures.

IMPORTANT: neither method's output is evidence of wrongdoing. An anomaly
score means "this transaction looks statistically unusual relative to the
rest of this dataset," nothing more. Every result produced here is
labeled "potential anomaly," never "fraud" -- see docs/defense_questions.md.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

DEFAULT_Z_THRESHOLD = 3.0
DEFAULT_CONTAMINATION = 0.01
# Consistency constant that makes MAD comparable to a standard deviation
# under a normal distribution (a standard, published constant).
MAD_SCALE = 1.4826


@dataclass
class AnomalyResult:
    """A single flagged transaction, with the evidence behind the flag."""

    transaction_id: str
    source: str
    destination: str
    amount: float
    timestamp: str | None
    anomaly_score: float
    method: str
    reason: str


@dataclass
class EvaluationResult:
    """Precision/recall/F1 of a set of predicted anomalies against ground truth."""

    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float


def _transactions_to_df(transactions: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(transactions)
    df["amount"] = df["amount"].astype(float)
    return df


def detect_anomalies_statistical(
    transactions: list[dict], z_threshold: float = DEFAULT_Z_THRESHOLD
) -> list[AnomalyResult]:
    """Flag transactions whose amount is a robust-z-score outlier.

    `transactions` is a list of dicts with keys: transaction_id, source,
    destination, amount, timestamp.
    """
    if not transactions:
        return []

    df = _transactions_to_df(transactions)
    amounts = df["amount"]
    median = amounts.median()
    mad = (amounts - median).abs().median()
    scaled_mad = mad * MAD_SCALE if mad > 0 else 1e-9

    results = []
    for row in df.itertuples(index=False):
        z_score = (row.amount - median) / scaled_mad
        if abs(z_score) >= z_threshold:
            results.append(
                AnomalyResult(
                    transaction_id=row.transaction_id,
                    source=row.source,
                    destination=row.destination,
                    amount=float(row.amount),
                    timestamp=getattr(row, "timestamp", None),
                    anomaly_score=round(abs(float(z_score)), 4),
                    method="statistical",
                    reason=(
                        f"Amount {row.amount:,.2f} is {abs(z_score):.1f} robust standard "
                        f"deviations from the dataset median ({median:,.2f})."
                    ),
                )
            )
    return sorted(results, key=lambda r: r.anomaly_score, reverse=True)


def detect_anomalies_isolation_forest(
    transactions: list[dict], contamination: float = DEFAULT_CONTAMINATION, random_state: int = 42
) -> list[AnomalyResult]:
    """Flag transactions using scikit-learn's IsolationForest on log-transformed amount.

    `contamination` is IsolationForest's expected proportion of outliers in
    the data -- it directly controls how many transactions get flagged, so
    it is exposed as a tunable parameter rather than hard-coded.
    """
    if not transactions:
        return []

    df = _transactions_to_df(transactions)
    # log1p tames the heavy right skew typical of transaction amounts, so
    # the forest isn't dominated by scale alone.
    features = np.log1p(df["amount"]).to_numpy().reshape(-1, 1)

    model = IsolationForest(contamination=contamination, random_state=random_state)
    model.fit(features)
    predictions = model.predict(features)  # -1 = outlier, 1 = normal
    raw_scores = model.score_samples(features)  # higher = more normal

    # Rescale to [0, 1] with higher = more anomalous, so anomaly_score means
    # the same thing regardless of which method produced it.
    score_range = (raw_scores.max() - raw_scores.min()) or 1e-9
    anomaly_scores = 1 - (raw_scores - raw_scores.min()) / score_range

    results = []
    for idx, row in enumerate(df.itertuples(index=False)):
        if predictions[idx] == -1:
            results.append(
                AnomalyResult(
                    transaction_id=row.transaction_id,
                    source=row.source,
                    destination=row.destination,
                    amount=float(row.amount),
                    timestamp=getattr(row, "timestamp", None),
                    anomaly_score=round(float(anomaly_scores[idx]), 4),
                    method="isolation_forest",
                    reason=(
                        f"Isolation Forest isolated this transaction (amount={row.amount:,.2f}) "
                        f"in fewer partitions than typical; anomaly score {anomaly_scores[idx]:.2f}."
                    ),
                )
            )
    return sorted(results, key=lambda r: r.anomaly_score, reverse=True)


def evaluate_against_ground_truth(results: list[AnomalyResult], ground_truth_ids: set[str]) -> EvaluationResult:
    """Compare predicted anomalies against known injected outlier transaction ids."""
    predicted_ids = {r.transaction_id for r in results}

    true_positives = len(predicted_ids & ground_truth_ids)
    false_positives = len(predicted_ids - ground_truth_ids)
    false_negatives = len(ground_truth_ids - predicted_ids)

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 0.0
    f1_score = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return EvaluationResult(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1_score=round(f1_score, 4),
    )


def load_ground_truth_anomaly_ids(synthetic_dir: str | Path, size: int) -> set[str] | None:
    """Load the known injected outlier transaction ids from scripts/generate_data.py.

    Returns None if no ground-truth file exists for this size.
    """
    path = Path(synthetic_dir) / f"ground_truth_anomalies_{size}.csv"
    if not path.exists():
        return None
    ground_truth_df = pd.read_csv(path, dtype=str)
    if ground_truth_df.empty:
        return set()
    return set(ground_truth_df["transaction_id"])
