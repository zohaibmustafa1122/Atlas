"""Tests for entity resolution (app/processing/entity_resolution.py)."""

from app.processing.entity_resolution import (
    EvaluationResult,
    _generate_candidate_pairs,
    confidence_label,
    evaluate_against_ground_truth,
    resolve_entities,
)
from app.processing.normalization import normalize_string


def test_resolve_entities_finds_obvious_duplicate_with_baseline() -> None:
    persons = [("1", "Muhammad Ali"), ("2", "Muhammad Ali"), ("3", "John Smith")]
    candidates = resolve_entities(persons, method="baseline", threshold=0.5)
    pairs = {frozenset({c.id_a, c.id_b}) for c in candidates}
    assert frozenset({"1", "2"}) in pairs
    assert frozenset({"1", "3"}) not in pairs


def test_resolve_entities_finds_initial_variant_with_multi_feature() -> None:
    # "M. Ali" is only a moderate-confidence candidate for "Muhammad Ali" --
    # an initial is genuinely ambiguous (could be Mohammed, Michael, ...),
    # so a lower threshold is needed to surface it. This is expected
    # behavior, not a bug: see docs/defense_questions.md.
    persons = [("1", "Muhammad Ali"), ("2", "M. Ali"), ("3", "Completely Different Name")]
    candidates = resolve_entities(persons, method="multi_feature", threshold=0.4)
    pairs = {frozenset({c.id_a, c.id_b}) for c in candidates}
    assert frozenset({"1", "2"}) in pairs
    assert frozenset({"1", "3"}) not in pairs
    assert frozenset({"2", "3"}) not in pairs


def test_resolve_entities_does_not_match_unrelated_names() -> None:
    persons = [("1", "Alice Johnson"), ("2", "Bob Williams")]
    candidates = resolve_entities(persons, method="multi_feature", threshold=0.55)
    assert candidates == []


def test_resolve_entities_returns_sorted_by_similarity_descending() -> None:
    persons = [("1", "Muhammad Ali"), ("2", "Muhammad Ali"), ("3", "Muhammad Al")]
    candidates = resolve_entities(persons, method="multi_feature", threshold=0.3)
    scores = [c.similarity for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_resolve_entities_rejects_unknown_method() -> None:
    import pytest

    with pytest.raises(ValueError):
        resolve_entities([("1", "Alice")], method="not_a_real_method")


def test_resolve_entities_never_claims_certainty() -> None:
    persons = [("1", "Muhammad Ali"), ("2", "Muhammad Ali")]
    candidates = resolve_entities(persons, method="baseline", threshold=0.5)
    assert len(candidates) == 1
    assert "match" in candidates[0].confidence.lower()
    assert "same" not in candidates[0].confidence.lower()
    assert "identical" not in candidates[0].confidence.lower()


def test_confidence_label_bands() -> None:
    assert confidence_label(0.95) == "Potential match (high confidence)"
    assert confidence_label(0.75) == "Possible match (medium confidence)"
    assert confidence_label(0.60) == "Weak possible match (low confidence)"
    assert confidence_label(0.10) == "Unlikely match"


def test_evaluate_against_ground_truth_perfect_prediction() -> None:
    from app.processing.entity_resolution import MatchCandidate

    candidates = [
        MatchCandidate(id_a="1", name_a="A", id_b="2", name_b="B", similarity=0.9, confidence="x", reason="")
    ]
    ground_truth = {frozenset({"1", "2"})}
    result = evaluate_against_ground_truth(candidates, ground_truth)
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1_score == 1.0


def test_evaluate_against_ground_truth_with_false_positive_and_negative() -> None:
    from app.processing.entity_resolution import MatchCandidate

    candidates = [
        MatchCandidate(id_a="1", name_a="A", id_b="2", name_b="B", similarity=0.9, confidence="x", reason=""),
        MatchCandidate(id_a="3", name_a="C", id_b="4", name_b="D", similarity=0.6, confidence="x", reason=""),
    ]
    ground_truth = {frozenset({"1", "2"}), frozenset({"5", "6"})}
    result = evaluate_against_ground_truth(candidates, ground_truth)
    assert result.true_positives == 1
    assert result.false_positives == 1
    assert result.false_negatives == 1
    assert 0.0 < result.precision < 1.0
    assert 0.0 < result.recall < 1.0


def test_evaluate_against_ground_truth_empty_predictions() -> None:
    result = evaluate_against_ground_truth([], {frozenset({"1", "2"})})
    assert result.precision == 0.0
    assert result.recall == 0.0
    assert isinstance(result, EvaluationResult)


def test_generate_candidate_pairs_does_not_starve_small_blocks_when_one_block_is_huge() -> None:
    """Regression test for a real bug found during Phase 8 experiments:
    an earlier version of _generate_candidate_pairs stopped the instant the
    global pair cap was reached, so one oversized block (e.g. hundreds of
    names starting with the same letter) could exhaust the whole budget
    before any other block was even considered -- collapsing entity
    resolution recall at 10,000+ record scale. The fix budgets the cap
    across all blocks instead of filling it from whichever block comes
    first.
    """
    # One huge block: 200 records that all normalize to start with "a" and
    # share no other block key with each other or with the pair below.
    huge_block_records = [(f"huge-{i}", f"Aaaaaaa Zzzzzzz{i}") for i in range(200)]
    # A small, distinct pair that should still be found: shares a blocking
    # key (last token "Nnnnnnn") with each other, but not with the huge block.
    small_pair_records = [("small-1", "Bbbbbbb Nnnnnnn"), ("small-2", "Cccccc Nnnnnnn")]

    records = [(pid, normalize_string(name)) for pid, name in huge_block_records + small_pair_records]
    # Force a tiny cap so the huge block alone would, under the old
    # behavior, consume the entire budget before the small pair is reached.
    pairs = _generate_candidate_pairs(records, max_pairs=50)

    small_idx_a = len(huge_block_records)
    small_idx_b = len(huge_block_records) + 1
    assert (small_idx_a, small_idx_b) in pairs or (small_idx_b, small_idx_a) in pairs
