"""Phase 8 research script: run the ATLAS pipeline at multiple dataset
sizes and measure what the research question asks about.

Research question (see docs/research.md):
"Can resource-efficient graph-based entity resolution and anomaly
detection improve exploratory analysis of heterogeneous datasets on
low-resource computing environments?"

For each requested size, this script:
  1. Generates (or reuses) the synthetic dataset via scripts/generate_data.py.
  2. Loads it into an isolated experiments database (never the main dev DB).
  3. Times database loading and graph construction.
  4. Runs entity resolution (baseline vs multi_feature) against the
     generator's injected ground-truth duplicate pairs, recording
     precision/recall/F1 and wall-clock time.
  5. Runs anomaly detection (statistical vs isolation_forest) against the
     generator's injected ground-truth outlier transactions, recording
     precision/recall/F1/false-positive-rate and wall-clock time.
  6. Records peak process memory (a cumulative watermark across the run --
     see docs/research.md for why that's a documented limitation, not an
     oversight).

Writes results to data/processed/experiments/results_<timestamp>.{json,csv}
and a handful of matplotlib charts to docs/experiments/.

Usage:
    python scripts/run_experiments.py --sizes 1000 10000
    python scripts/run_experiments.py --sizes 1000 10000 100000 --regenerate
"""

import argparse
import json
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import generate_data  # noqa: E402
from app.database.models import Base  # noqa: E402
from app.database.repositories import EntityRepository  # noqa: E402
from app.graph.analytics import compute_graph_metrics  # noqa: E402
from app.graph.builder import build_graph_for_dataset  # noqa: E402
from app.ml.anomaly_detection import (  # noqa: E402
    detect_anomalies_isolation_forest,
    detect_anomalies_statistical,
    evaluate_against_ground_truth as evaluate_anomalies,
    load_ground_truth_anomaly_ids,
)
from app.processing.entity_resolution import (  # noqa: E402
    evaluate_against_ground_truth as evaluate_entity_resolution,
    load_ground_truth_pairs,
    resolve_entities,
)
from app.processing.loading import load_synthetic_dataset  # noqa: E402

EXPERIMENTS_DB_PATH = PROJECT_ROOT / "data" / "processed" / "experiments.db"
RESULTS_DIR = PROJECT_ROOT / "data" / "processed" / "experiments"
CHARTS_DIR = PROJECT_ROOT / "docs" / "experiments"
ENTITY_RESOLUTION_THRESHOLD = 0.70  # see docs/research.md for why this value


def _make_session_factory():
    """A session factory bound to a dedicated experiments SQLite file --
    intentionally separate from the app's normal DATABASE_URL so running
    experiments never pollutes (or is polluted by) the demo database.
    """
    engine = create_engine(f"sqlite:///{EXPERIMENTS_DB_PATH}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


@contextmanager
def _session_scope(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _peak_memory_mb() -> float | None:
    """Peak resident set size of this process so far, in MB.

    This is a cumulative watermark (it only ever increases across the
    whole script run), not an isolated per-size measurement -- see
    docs/research.md for why that's a documented limitation. Returns None
    on platforms without the `resource` module (e.g. native Windows,
    which would need WSL for this measurement).
    """
    try:
        import resource
    except ImportError:
        return None
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def run_experiment_for_size(size: int, synthetic_dir: Path, session_factory, regenerate: bool) -> dict:
    """Run the full measurement suite for one dataset size and return a flat metrics dict."""
    persons_file = synthetic_dir / f"persons_{size}.csv"
    if regenerate or not persons_file.exists():
        tables = generate_data.generate_dataset(size)
        generate_data.save_dataset(tables, size, synthetic_dir)

    metrics: dict = {"size": size}

    with _session_scope(session_factory) as session:
        t0 = time.perf_counter()
        dataset = load_synthetic_dataset(session, synthetic_dir, size, dataset_name=f"Experiment ({size})")
        metrics["load_time_seconds"] = round(time.perf_counter() - t0, 4)
        dataset_id = dataset.dataset_id

    with _session_scope(session_factory) as session:
        t0 = time.perf_counter()
        graph = build_graph_for_dataset(session, dataset_id)
        metrics["graph_build_time_seconds"] = round(time.perf_counter() - t0, 4)

    metrics["graph_node_count"] = graph.number_of_nodes()
    metrics["graph_edge_count"] = graph.number_of_edges()

    t0 = time.perf_counter()
    graph_metrics = compute_graph_metrics(graph)
    metrics["graph_metrics_time_seconds"] = round(time.perf_counter() - t0, 4)
    metrics["betweenness_approximated"] = graph_metrics.betweenness_approximated

    with _session_scope(session_factory) as session:
        persons = EntityRepository(session).list_persons(dataset_id)
        transactions = EntityRepository(session).list_transactions(dataset_id)
        person_pairs = [(p.person_id, p.name) for p in persons]
        txn_dicts = [
            {"transaction_id": t.transaction_id, "source": t.source, "destination": t.destination, "amount": t.amount, "timestamp": str(t.timestamp)}
            for t in transactions
        ]

    ground_truth_er = load_ground_truth_pairs(synthetic_dir, size) or set()

    for method in ["baseline", "multi_feature"]:
        t0 = time.perf_counter()
        candidates = resolve_entities(person_pairs, method=method, threshold=ENTITY_RESOLUTION_THRESHOLD)
        elapsed = time.perf_counter() - t0
        evaluation = evaluate_entity_resolution(candidates, ground_truth_er)
        metrics[f"er_{method}_time_seconds"] = round(elapsed, 4)
        metrics[f"er_{method}_candidates"] = len(candidates)
        metrics[f"er_{method}_precision"] = evaluation.precision
        metrics[f"er_{method}_recall"] = evaluation.recall
        metrics[f"er_{method}_f1"] = evaluation.f1_score

    ground_truth_ad = load_ground_truth_anomaly_ids(synthetic_dir, size) or set()

    for method, detect_fn in [("statistical", detect_anomalies_statistical), ("isolation_forest", detect_anomalies_isolation_forest)]:
        t0 = time.perf_counter()
        results = detect_fn(txn_dicts)
        elapsed = time.perf_counter() - t0
        evaluation = evaluate_anomalies(results, ground_truth_ad)
        total_negatives = len(txn_dicts) - len(ground_truth_ad)
        fpr = evaluation.false_positives / total_negatives if total_negatives else 0.0
        metrics[f"anomaly_{method}_time_seconds"] = round(elapsed, 4)
        metrics[f"anomaly_{method}_precision"] = evaluation.precision
        metrics[f"anomaly_{method}_recall"] = evaluation.recall
        metrics[f"anomaly_{method}_f1"] = evaluation.f1_score
        metrics[f"anomaly_{method}_fpr"] = round(fpr, 4)

    with _session_scope(session_factory) as session:
        t0 = time.perf_counter()
        EntityRepository(session).count_by_dataset(dataset_id)
        metrics["simple_query_time_seconds"] = round(time.perf_counter() - t0, 4)

    metrics["peak_memory_mb"] = round(_peak_memory_mb(), 1)
    return metrics


def make_charts(results: list[dict], output_dir: Path) -> None:
    """Save a handful of comparison charts as PNGs for docs/experiments.md."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sizes = [r["size"] for r in results]

    fig, ax = plt.subplots()
    ax.plot(sizes, [r["er_baseline_f1"] for r in results], marker="o", label="baseline (Levenshtein only)")
    ax.plot(sizes, [r["er_multi_feature_f1"] for r in results], marker="o", label="multi-feature")
    ax.set_xlabel("Dataset size (person records)")
    ax.set_ylabel("F1 score")
    ax.set_title(f"Entity Resolution F1 by dataset size (threshold={ENTITY_RESOLUTION_THRESHOLD})")
    ax.set_xscale("log")
    ax.legend()
    fig.savefig(output_dir / "entity_resolution_f1.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots()
    ax.plot(sizes, [r["anomaly_statistical_f1"] for r in results], marker="o", label="statistical (robust z-score)")
    ax.plot(sizes, [r["anomaly_isolation_forest_f1"] for r in results], marker="o", label="isolation forest")
    ax.set_xlabel("Dataset size (transactions)")
    ax.set_ylabel("F1 score")
    ax.set_title("Anomaly Detection F1 by dataset size")
    ax.set_xscale("log")
    ax.legend()
    fig.savefig(output_dir / "anomaly_detection_f1.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots()
    ax.plot(sizes, [r["load_time_seconds"] for r in results], marker="o", label="DB load")
    ax.plot(sizes, [r["graph_build_time_seconds"] for r in results], marker="o", label="graph build")
    ax.plot(sizes, [r["graph_metrics_time_seconds"] for r in results], marker="o", label="graph metrics")
    ax.set_xlabel("Dataset size")
    ax.set_ylabel("Time (seconds)")
    ax.set_title("Processing time by dataset size")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.legend()
    fig.savefig(output_dir / "performance_time.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    if all(r.get("peak_memory_mb") is not None for r in results):
        fig, ax = plt.subplots()
        ax.plot(sizes, [r["peak_memory_mb"] for r in results], marker="o")
        ax.set_xlabel("Dataset size")
        ax.set_ylabel("Peak process memory so far (MB)")
        ax.set_title("Cumulative peak memory watermark by dataset size")
        ax.set_xscale("log")
        fig.savefig(output_dir / "memory_usage.png", dpi=150, bbox_inches="tight")
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ATLAS Phase 8 research experiments.")
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000])
    parser.add_argument("--regenerate", action="store_true", help="Force-regenerate synthetic data even if it already exists.")
    args = parser.parse_args()

    synthetic_dir = PROJECT_ROOT / "data" / "synthetic"
    session_factory = _make_session_factory()

    results = []
    for size in args.sizes:
        print(f"\n=== Running experiment for size={size:,} ===")
        metrics = run_experiment_for_size(size, synthetic_dir, session_factory, args.regenerate)
        results.append(metrics)
        print(json.dumps(metrics, indent=2))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = RESULTS_DIR / f"results_{timestamp}.json"
    csv_path = RESULTS_DIR / f"results_{timestamp}.csv"
    json_path.write_text(json.dumps(results, indent=2))
    pd.DataFrame(results).to_csv(csv_path, index=False)
    print(f"\nWrote {json_path.relative_to(PROJECT_ROOT)} and {csv_path.relative_to(PROJECT_ROOT)}")

    make_charts(results, CHARTS_DIR)
    print(f"Wrote charts to {CHARTS_DIR.relative_to(PROJECT_ROOT)}/")


if __name__ == "__main__":
    main()
