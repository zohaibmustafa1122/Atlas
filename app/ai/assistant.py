"""AI assistant: retrieval-grounded question answering over a dataset.

Architecture (see docs/architecture.md section 17 / the project brief):

    question -> intent detection -> evidence retrieval -> answer
                                                              |
                                              (LLM explanation, optional)

The retrieval step ALWAYS runs and is the source of truth -- every fact
the assistant can state comes from calling the same graph/ML/database
modules already built in Phases 2-6, not from the LLM. The optional LLM
step only explains that retrieved evidence in natural language; its
system prompt (app/ai/prompts.py) requires it to separate FACT from
INFERENCE from UNCERTAINTY and forbids it from adding facts of its own.

If no LLM API key is configured, or the API call fails for any reason,
`answer_question` falls back to a deterministic template built directly
from the same evidence -- "fallback analytical mode". This is not a
degraded afterthought: it is the required behavior per the project brief
("if no LLM API key is configured, the system must still work").
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.ai.prompts import ASSISTANT_SYSTEM_PROMPT
from app.core.config import Settings, get_settings
from app.database.models import Dataset
from app.database.repositories import EntityRepository
from app.graph.analytics import compute_graph_metrics, find_shortest_path
from app.graph.builder import build_graph_for_dataset
from app.ml.anomaly_detection import detect_anomalies_statistical
from app.nlp.entity_extraction import extract_entities_baseline
from app.processing.entity_resolution import resolve_entities

INTENT_PATTERNS = {
    "shortest_path": re.compile(r"\bconnect(ed|ion)?\b.*\band\b|\bhow (is|are)\b.*\bconnected\b|\bpath between\b", re.I),
    "most_connected": re.compile(r"\bmost connected\b|\bstrongest connections?\b|\bmost connections?\b|\bcentral\b|\binfluential\b", re.I),
    "anomalies": re.compile(r"\banomal\w*\b|\bsuspicious\b|\bunusual\b|\boutlier\w*\b", re.I),
    "duplicates": re.compile(r"\bduplicate\w*\b|\bsame person\b|\bsimilar name\w*\b|\bpotential match\w*\b", re.I),
    "quality": re.compile(r"\bdata quality\b|\bquality score\b|\bhow clean\b", re.I),
}
DEFAULT_INTENT = "overview"

MIN_MENTION_SIMILARITY = 0.6


@dataclass
class AssistantAnswer:
    """The result of answer_question: what was asked, found, and said."""

    question: str
    intent: str
    evidence: list[str]
    answer: str
    mode: str  # "llm" or "fallback"
    sources: list[str] = field(default_factory=list)


def detect_intent(question: str) -> str:
    """Rule-based intent classification -- deliberately not an ML model.

    Question interpretation here only needs to route to the right
    retrieval function; a handful of keyword patterns does that reliably
    and stays fully explainable, which a learned classifier wouldn't add
    value over at this scale.
    """
    for intent, pattern in INTENT_PATTERNS.items():
        if pattern.search(question):
            return intent
    return DEFAULT_INTENT


def find_mentioned_entities(session: Session, dataset_id: str, question: str) -> list[dict]:
    """Find dataset entities (persons/organizations) named in the question.

    Reuses the Phase 6 baseline extractor to find capitalized-sequence
    candidates in the question text, then the Phase 4-adjacent indexed
    search (EntityRepository.search_entities) to match each candidate
    against real records -- the same retrieval path used elsewhere in the
    app, not a separate implementation.
    """
    candidates = [e.text for e in extract_entities_baseline(question) if e.label == "PROPER_NOUN"]
    repo = EntityRepository(session)
    matches: list[dict] = []
    seen_ids: set[str] = set()
    for phrase in candidates:
        for match in repo.search_entities(dataset_id, phrase, limit=3):
            if match["id"] in seen_ids:
                continue
            similarity = SequenceMatcher(None, phrase.lower(), match["name"].lower()).ratio()
            if similarity < MIN_MENTION_SIMILARITY:
                continue
            seen_ids.add(match["id"])
            matches.append(match)
    return matches


def _handle_overview(session: Session, dataset: Dataset, _mentioned: list[dict]) -> tuple[list[str], list[str]]:
    counts = EntityRepository(session).count_by_dataset(dataset.dataset_id)
    evidence = [f"Dataset '{dataset.name}' contains {dataset.row_count:,} total rows across its tables."]
    evidence += [f"{label}: {count:,} records." for label, count in counts.items()]
    if dataset.quality_score is not None:
        evidence.append(f"Data Quality Score: {dataset.quality_score:.0f}/100.")
    return evidence, ["database.repositories.EntityRepository.count_by_dataset"]


def _handle_most_connected(session: Session, dataset: Dataset, mentioned: list[dict]) -> tuple[list[str], list[str]]:
    graph = build_graph_for_dataset(session, dataset.dataset_id)
    sources = ["graph.builder.build_graph_for_dataset", "graph.analytics.compute_graph_metrics"]

    if mentioned:
        entity = mentioned[0]
        if entity["id"] not in graph:
            return [f"'{entity['name']}' was found in the dataset but has no graph connections."], sources
        neighbor_ids = set(graph.successors(entity["id"])) | set(graph.predecessors(entity["id"]))
        neighbor_labels = [graph.nodes[n].get("label", n) for n in list(neighbor_ids)[:10]]
        evidence = [
            f"{entity['name']} has {len(neighbor_ids)} direct connection(s) in the graph.",
            f"Directly connected entities: {', '.join(neighbor_labels) if neighbor_labels else 'none'}.",
        ]
        return evidence, sources

    metrics = compute_graph_metrics(graph, top_n=5)
    if not metrics.top_degree:
        return ["The graph for this dataset has no entities or connections."], sources
    top_lines = [f"{graph.nodes[node_id].get('label', node_id)} (degree centrality {score:.4f})" for node_id, score in metrics.top_degree]
    evidence = [f"Top entities by degree centrality (most direct connections): {'; '.join(top_lines)}."]
    if metrics.betweenness_approximated:
        evidence.append("Note: betweenness centrality was approximated for this dataset's size; degree centrality above is exact.")
    return evidence, sources


def _handle_shortest_path(session: Session, dataset: Dataset, mentioned: list[dict]) -> tuple[list[str], list[str]]:
    sources = ["graph.builder.build_graph_for_dataset", "graph.analytics.find_shortest_path"]
    if len(mentioned) < 2:
        return ["Could not identify two distinct entities in the question to find a path between."], sources

    graph = build_graph_for_dataset(session, dataset.dataset_id)
    entity_a, entity_b = mentioned[0], mentioned[1]
    path = find_shortest_path(graph, entity_a["id"], entity_b["id"])
    if path is None:
        return [f"No path was found between {entity_a['name']} and {entity_b['name']} in this dataset's graph."], sources

    labels = [graph.nodes[n].get("label", n) for n in path]
    evidence = [
        f"Shortest path between {entity_a['name']} and {entity_b['name']}: {' -> '.join(labels)} ({len(path) - 1} hop(s))."
    ]
    return evidence, sources


def _handle_anomalies(session: Session, dataset: Dataset, _mentioned: list[dict]) -> tuple[list[str], list[str]]:
    transactions = EntityRepository(session).list_transactions(dataset.dataset_id)
    sources = ["ml.anomaly_detection.detect_anomalies_statistical"]
    if not transactions:
        return ["This dataset has no transactions to check for anomalies."], sources

    txn_dicts = [
        {"transaction_id": t.transaction_id, "source": t.source, "destination": t.destination, "amount": t.amount, "timestamp": str(t.timestamp)}
        for t in transactions
    ]
    results = detect_anomalies_statistical(txn_dicts)[:5]
    if not results:
        return ["No statistically unusual transaction amounts were found (using the default robust z-score threshold)."], sources

    evidence = [
        f"Potential anomaly: transaction amount {r.amount:,.2f} (anomaly score {r.anomaly_score:.2f}). {r.reason}"
        for r in results
    ]
    evidence.insert(0, f"{len(results)} potential anomal{'y' if len(results) == 1 else 'ies'} found among {len(transactions)} transactions.")
    return evidence, sources


def _handle_duplicates(session: Session, dataset: Dataset, _mentioned: list[dict]) -> tuple[list[str], list[str]]:
    persons = EntityRepository(session).list_persons(dataset.dataset_id)
    sources = ["processing.entity_resolution.resolve_entities"]
    if not persons:
        return ["This dataset has no person records to check for duplicates."], sources

    person_pairs = [(p.person_id, p.name) for p in persons]
    candidates = resolve_entities(person_pairs, method="multi_feature", threshold=0.70)[:5]
    if not candidates:
        return ["No potential duplicate person records were found at the default similarity threshold."], sources

    evidence = [f"Potential duplicate: '{c.name_a}' and '{c.name_b}' ({c.confidence}, similarity {c.similarity:.2f})." for c in candidates]
    evidence.insert(0, f"{len(candidates)} potential duplicate pair(s) found among {len(persons)} person records.")
    return evidence, sources


def _handle_quality(_session: Session, dataset: Dataset, _mentioned: list[dict]) -> tuple[list[str], list[str]]:
    sources = ["database.models.Dataset"]
    if dataset.quality_score is None:
        return ["No Data Quality Score has been computed for this dataset yet."], sources
    evidence = [
        f"Data Quality Score: {dataset.quality_score:.0f}/100.",
        f"Missing values: {dataset.missing_value_pct:.2f}% of cells.",
        f"Duplicate rows: {dataset.duplicate_row_pct:.2f}% of rows.",
    ]
    return evidence, sources


_INTENT_HANDLERS = {
    "overview": _handle_overview,
    "most_connected": _handle_most_connected,
    "shortest_path": _handle_shortest_path,
    "anomalies": _handle_anomalies,
    "duplicates": _handle_duplicates,
    "quality": _handle_quality,
}


def _format_fallback_answer(evidence: list[str]) -> str:
    """Deterministic, template-based answer built directly from evidence -- no LLM."""
    if not evidence:
        return "UNCERTAINTY: No relevant data was found in this dataset to answer that question."
    lines = ["FACT (retrieved directly from the dataset; no LLM was used to generate this answer):"]
    lines += [f"- {line}" for line in evidence]
    return "\n".join(lines)


def _call_llm(question: str, evidence: list[str], settings: Settings) -> str | None:
    """Ask the configured LLM to explain the evidence. Returns None on any
    failure (missing key, missing package, network error, API error) so the
    caller can fall back -- this is intentionally a broad catch, since the
    project requirement is that ANY LLM failure degrades gracefully rather
    than crashing the assistant.
    """
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    evidence_block = "\n".join(f"- {line}" for line in evidence) if evidence else "(no evidence was retrieved)"
    user_message = f"Question: {question}\n\nRetrieved evidence:\n{evidence_block}\n\nAnswer using only this evidence."

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=400,
            system=ASSISTANT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
    except Exception:
        return None


def answer_question(session: Session, dataset: Dataset, question: str, settings: Settings | None = None) -> AssistantAnswer:
    """Answer a natural-language question about `dataset`, grounded in retrieved evidence."""
    settings = settings or get_settings()
    intent = detect_intent(question)
    mentioned = find_mentioned_entities(session, dataset.dataset_id, question)

    handler = _INTENT_HANDLERS[intent]
    evidence, sources = handler(session, dataset, mentioned)

    llm_answer = _call_llm(question, evidence, settings)
    if llm_answer:
        return AssistantAnswer(question=question, intent=intent, evidence=evidence, answer=llm_answer, mode="llm", sources=sources)

    fallback_answer = _format_fallback_answer(evidence)
    return AssistantAnswer(question=question, intent=intent, evidence=evidence, answer=fallback_answer, mode="fallback", sources=sources)
