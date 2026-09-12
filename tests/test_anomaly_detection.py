"""Tests for anomaly detection (app/ml/anomaly_detection.py)."""

from app.ml.anomaly_detection import (
    EvaluationResult,
    detect_anomalies_isolation_forest,
    detect_anomalies_statistical,
    evaluate_against_ground_truth,
)


def _make_transactions(amounts: list[float]) -> list[dict]:
    return [
        {
            "transaction_id": str(i),
            "source": "p1",
            "destination": "p2",
            "amount": amount,
            "timestamp": "2024-01-01T00:00:00",
        }
        for i, amount in enumerate(amounts)
    ]


def test_statistical_flags_extreme_outlier() -> None:
    amounts = [100.0, 105.0, 98.0, 102.0, 101.0, 99.0, 103.0, 97.0, 104.0, 50_000.0]
    transactions = _make_transactions(amounts)
    results = detect_anomalies_statistical(transactions, z_threshold=3.0)
    flagged_ids = {r.transaction_id for r in results}
    assert "9" in flagged_ids  # the 50,000 outlier
    assert "0" not in flagged_ids


def test_statistical_returns_empty_for_uniform_data() -> None:
    transactions = _make_transactions([100.0] * 10)
    results = detect_anomalies_statistical(transactions, z_threshold=3.0)
    assert results == []


def test_statistical_handles_empty_input() -> None:
    assert detect_anomalies_statistical([]) == []


def test_statistical_results_sorted_by_score_descending() -> None:
    amounts = [100.0] * 9 + [10_000.0, 20_000.0]
    transactions = _make_transactions(amounts)
    results = detect_anomalies_statistical(transactions, z_threshold=2.0)
    scores = [r.anomaly_score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_statistical_never_uses_fraud_language() -> None:
    amounts = [100.0] * 9 + [50_000.0]
    transactions = _make_transactions(amounts)
    results = detect_anomalies_statistical(transactions, z_threshold=2.0)
    for result in results:
        assert "fraud" not in result.reason.lower()


def test_isolation_forest_flags_extreme_outlier() -> None:
    amounts = [100.0 + i for i in range(50)] + [1_000_000.0]
    transactions = _make_transactions(amounts)
    results = detect_anomalies_isolation_forest(transactions, contamination=0.02)
    flagged_ids = {r.transaction_id for r in results}
    assert str(len(amounts) - 1) in flagged_ids


def test_isolation_forest_handles_empty_input() -> None:
    assert detect_anomalies_isolation_forest([]) == []


def test_isolation_forest_scores_are_bounded() -> None:
    amounts = [100.0 + i for i in range(50)] + [1_000_000.0]
    transactions = _make_transactions(amounts)
    results = detect_anomalies_isolation_forest(transactions, contamination=0.05)
    for result in results:
        assert 0.0 <= result.anomaly_score <= 1.0


def test_evaluate_against_ground_truth_perfect_prediction() -> None:
    from app.ml.anomaly_detection import AnomalyResult

    results = [
        AnomalyResult(
            transaction_id="9",
            source="p1",
            destination="p2",
            amount=50_000.0,
            timestamp=None,
            anomaly_score=5.0,
            method="statistical",
            reason="",
        )
    ]
    evaluation = evaluate_against_ground_truth(results, {"9"})
    assert evaluation.precision == 1.0
    assert evaluation.recall == 1.0
    assert evaluation.f1_score == 1.0


def test_evaluate_against_ground_truth_with_errors() -> None:
    from app.ml.anomaly_detection import AnomalyResult

    results = [
        AnomalyResult("9", "p1", "p2", 50_000.0, None, 5.0, "statistical", ""),
        AnomalyResult("3", "p1", "p2", 200.0, None, 1.0, "statistical", ""),
    ]
    ground_truth = {"9", "7"}
    evaluation = evaluate_against_ground_truth(results, ground_truth)
    assert evaluation.true_positives == 1
    assert evaluation.false_positives == 1
    assert evaluation.false_negatives == 1
    assert isinstance(evaluation, EvaluationResult)


def test_evaluate_against_ground_truth_empty_predictions() -> None:
    evaluation = evaluate_against_ground_truth([], {"9"})
    assert evaluation.precision == 0.0
    assert evaluation.recall == 0.0
