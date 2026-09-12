"""Entity resolution: find person records that likely refer to the same
real-world identity, despite not being written identically
(e.g. "Muhammad Ali" vs "M. Ali").

This module deliberately never claims two records ARE the same entity --
only that they are a "potential match" at some confidence level. See
`ConfidenceLevel` and docs/defense_questions.md for why that distinction
matters.

Two scoring methods are implemented, for the baseline-vs-improved
comparison described in the project brief:

  - "baseline": a single similarity feature (normalized Levenshtein ratio).
  - "multi_feature": a weighted combination of Levenshtein ratio, token
    (word-set) Jaccard similarity, and character n-gram TF-IDF cosine
    similarity.

Both methods first reduce the O(n^2) all-pairs comparison problem with
blocking: records are only compared if they share a cheap-to-compute key,
which is what makes this feasible at 100,000-record scale on a laptop
(see `_blocking_keys`).
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from app.processing.normalization import normalize_string

MAX_CANDIDATE_PAIRS = 200_000

# Similarity score bands. These are deliberately labeled "potential" /
# "possible" / "weak possible" rather than "same" / "different" -- entity
# resolution here is a confidence estimate, not a verified fact. See
# docs/defense_questions.md for the reasoning.
HIGH_CONFIDENCE_THRESHOLD = 0.85
MEDIUM_CONFIDENCE_THRESHOLD = 0.70
LOW_CONFIDENCE_THRESHOLD = 0.55


@dataclass
class MatchCandidate:
    """A candidate pair of person records that may refer to the same identity."""

    id_a: str
    name_a: str
    id_b: str
    name_b: str
    similarity: float
    confidence: str
    reason: str


@dataclass
class EvaluationResult:
    """Precision/recall/F1 of a set of predicted matches against ground truth."""

    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float


def confidence_label(score: float) -> str:
    """Map a similarity score to a human-readable, appropriately hedged label."""
    if score >= HIGH_CONFIDENCE_THRESHOLD:
        return "Potential match (high confidence)"
    if score >= MEDIUM_CONFIDENCE_THRESHOLD:
        return "Possible match (medium confidence)"
    if score >= LOW_CONFIDENCE_THRESHOLD:
        return "Weak possible match (low confidence)"
    return "Unlikely match"


def _blocking_keys(normalized_name: str) -> set[str]:
    """Cheap keys used to decide which record pairs are even worth comparing.

    Two keys are used together (a record needs to share only one to be
    compared against another record):
      - the first character of the normalized name -- survives "Muhammad
        Ali" -> "M. Ali" (both normalize to start with 'm').
      - the last token -- survives most abbreviation/typo/honorific
        variants, since surnames are rarely the part that gets shortened.

    This is a standard entity-resolution trade-off: blocking trades a small
    amount of recall (a pair sharing neither key is never compared) for
    turning an O(n^2) comparison into something closer to O(n) in practice.
    """
    if not normalized_name:
        return set()
    tokens = normalized_name.split()
    keys = {normalized_name[0]}
    if tokens:
        keys.add(tokens[-1])
    return keys


def _generate_candidate_pairs(records: list[tuple[str, str]], max_pairs: int = MAX_CANDIDATE_PAIRS) -> list[tuple[int, int]]:
    """Return index pairs (into `records`) worth comparing, via blocking.

    `records` is a list of (id, normalized_name). Returns pairs of indices
    rather than ids so callers can look up precomputed feature vectors
    (e.g. TF-IDF rows) by position.
    """
    blocks: dict[str, list[int]] = {}
    for idx, (_, normalized_name) in enumerate(records):
        for key in _blocking_keys(normalized_name):
            blocks.setdefault(key, []).append(idx)

    seen: set[tuple[int, int]] = set()
    for indices in blocks.values():
        if len(indices) < 2:
            continue
        for i, j in combinations(sorted(indices), 2):
            seen.add((i, j))
            if len(seen) >= max_pairs:
                return list(seen)
    return list(seen)


def _token_jaccard(a: str, b: str) -> float:
    tokens_a, tokens_b = set(a.split()), set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _levenshtein_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def resolve_entities(
    persons: list[tuple[str, str]],
    method: str = "multi_feature",
    threshold: float = LOW_CONFIDENCE_THRESHOLD,
    max_candidate_pairs: int = MAX_CANDIDATE_PAIRS,
) -> list[MatchCandidate]:
    """Find candidate duplicate persons among `persons` (list of (id, name)).

    Args:
        persons: list of (person_id, name) tuples.
        method: "baseline" (Levenshtein ratio only) or "multi_feature"
            (Levenshtein + token Jaccard + TF-IDF cosine, weighted).
        threshold: minimum similarity score to include in the results.
        max_candidate_pairs: safety cap on blocking output, so an
            unexpectedly dense block can't blow up runtime on a laptop.

    Returns:
        MatchCandidate list, sorted by similarity descending.
    """
    if method not in {"baseline", "multi_feature"}:
        raise ValueError(f"Unknown method: {method}")

    records = [(person_id, normalize_string(name)) for person_id, name in persons]
    candidate_pairs = _generate_candidate_pairs(records, max_pairs=max_candidate_pairs)
    if not candidate_pairs:
        return []

    original_names = {person_id: name for person_id, name in persons}

    tfidf_matrix = None
    if method == "multi_feature":
        # char_wb n-grams (word-boundary-aware character n-grams) are a good
        # fit for short name-like strings, where whole-word TF-IDF would
        # treat "Muhammad" and "Muhamad" as entirely unrelated tokens.
        # norm="l2" (the default) means cosine similarity is just a dot
        # product of the resulting rows -- no extra normalization needed.
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3))
        tfidf_matrix = vectorizer.fit_transform([name for _, name in records])

    candidates: list[MatchCandidate] = []
    for i, j in candidate_pairs:
        id_a, name_a = records[i]
        id_b, name_b = records[j]

        levenshtein = _levenshtein_ratio(name_a, name_b)

        if method == "baseline":
            score = levenshtein
            reason = f"Character-level similarity (Levenshtein ratio): {levenshtein:.2f}."
        else:
            jaccard = _token_jaccard(name_a, name_b)
            cosine = float((tfidf_matrix[i] @ tfidf_matrix[j].T)[0, 0])
            score = 0.4 * levenshtein + 0.3 * jaccard + 0.3 * cosine
            reason = (
                f"Levenshtein ratio {levenshtein:.2f}, token overlap (Jaccard) {jaccard:.2f}, "
                f"character n-gram cosine similarity {cosine:.2f} -> weighted score {score:.2f}."
            )

        if score >= threshold:
            original_a = original_names[id_a]
            original_b = original_names[id_b]
            candidates.append(
                MatchCandidate(
                    id_a=id_a,
                    name_a=original_a,
                    id_b=id_b,
                    name_b=original_b,
                    similarity=round(score, 4),
                    confidence=confidence_label(score),
                    reason=reason,
                )
            )

    return sorted(candidates, key=lambda c: c.similarity, reverse=True)


def evaluate_against_ground_truth(
    candidates: list[MatchCandidate], ground_truth_pairs: set[frozenset[str]]
) -> EvaluationResult:
    """Compare predicted match candidates against known true duplicate pairs.

    `ground_truth_pairs` is a set of frozenset({id_a, id_b}) pairs known
    (by construction, e.g. from the synthetic generator) to be the same
    identity. This is a development-time sanity check, not the full
    multi-size benchmark study (that's Phase 8's job) -- but since the
    ground truth already exists, there's no reason not to expose it here.
    """
    predicted_pairs = {frozenset({c.id_a, c.id_b}) for c in candidates}

    true_positives = len(predicted_pairs & ground_truth_pairs)
    false_positives = len(predicted_pairs - ground_truth_pairs)
    false_negatives = len(ground_truth_pairs - predicted_pairs)

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


def load_ground_truth_pairs(synthetic_dir: str | Path, size: int) -> set[frozenset[str]] | None:
    """Load the known duplicate-identity pairs injected by scripts/generate_data.py.

    Returns None if no ground-truth file exists for this size (e.g. the
    loaded dataset wasn't generated synthetically).
    """
    path = Path(synthetic_dir) / f"ground_truth_entity_resolution_{size}.csv"
    if not path.exists():
        return None
    ground_truth_df = pd.read_csv(path, dtype=str)
    if ground_truth_df.empty:
        return set()
    return {
        frozenset({row["person_id"], row["true_identity_id"]}) for _, row in ground_truth_df.iterrows()
    }
