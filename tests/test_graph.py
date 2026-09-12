"""Tests for the graph construction, analytics, and query modules."""

from collections.abc import Generator
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Base, Dataset, Organization, Person, RelationshipEdge, Transaction
from app.database.repositories import DatasetRepository, EntityRepository
from app.graph.analytics import compute_graph_metrics, detect_communities, find_shortest_path
from app.graph.builder import build_graph_for_dataset
from app.graph.queries import get_neighborhood, list_edge_types, search_nodes


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture
def sample_dataset_id(session: Session) -> str:
    """Build a small dataset: 4 persons, 2 orgs, a chain of relationships, one transaction."""
    dataset_repo = DatasetRepository(session)
    entity_repo = EntityRepository(session)

    dataset = dataset_repo.create(Dataset(name="Graph Test Dataset"))

    org_a = Organization(name="Acme Corp", dataset_id=dataset.dataset_id)
    org_b = Organization(name="Globex", dataset_id=dataset.dataset_id)
    entity_repo.bulk_add_organizations([org_a, org_b])

    alice = Person(name="Alice", organization_id=org_a.organization_id, dataset_id=dataset.dataset_id)
    bob = Person(name="Bob", organization_id=org_a.organization_id, dataset_id=dataset.dataset_id)
    carol = Person(name="Carol", organization_id=org_b.organization_id, dataset_id=dataset.dataset_id)
    dave = Person(name="Dave", dataset_id=dataset.dataset_id)  # unconnected
    entity_repo.bulk_add_persons([alice, bob, carol, dave])

    entity_repo.bulk_add_relationships(
        [
            RelationshipEdge(
                source_entity=alice.person_id,
                target_entity=bob.person_id,
                relationship_type="KNOWS",
                confidence=0.9,
                dataset_id=dataset.dataset_id,
            ),
            RelationshipEdge(
                source_entity=bob.person_id,
                target_entity=carol.person_id,
                relationship_type="ASSOCIATED_WITH",
                confidence=0.8,
                dataset_id=dataset.dataset_id,
            ),
        ]
    )
    entity_repo.bulk_add_transactions(
        [
            Transaction(
                source=alice.person_id,
                destination=carol.person_id,
                amount=500.0,
                timestamp=datetime(2024, 1, 1),
                dataset_id=dataset.dataset_id,
            )
        ]
    )
    session.commit()

    session.dataset_id = dataset.dataset_id  # stash for convenience
    session.alice_id = alice.person_id
    session.bob_id = bob.person_id
    session.carol_id = carol.person_id
    session.dave_id = dave.person_id
    session.org_a_id = org_a.organization_id
    return dataset.dataset_id


def test_build_graph_includes_all_entities_and_edges(session: Session, sample_dataset_id: str) -> None:
    graph = build_graph_for_dataset(session, sample_dataset_id)
    # 4 persons + 2 organizations
    assert graph.number_of_nodes() == 6
    # 2 relationships + 1 transaction + 3 WORKS_FOR edges (alice, bob -> org_a; carol -> org_b)
    assert graph.number_of_edges() == 6


def test_build_graph_works_for_edge_from_organization_id(session: Session, sample_dataset_id: str) -> None:
    graph = build_graph_for_dataset(session, sample_dataset_id)
    assert graph.has_edge(session.alice_id, session.org_a_id)
    edge_data = graph.get_edge_data(session.alice_id, session.org_a_id)
    assert any(d.get("edge_type") == "WORKS_FOR" for d in edge_data.values())


def test_dave_is_isolated_node(session: Session, sample_dataset_id: str) -> None:
    graph = build_graph_for_dataset(session, sample_dataset_id)
    assert graph.degree(session.dave_id) == 0


def test_compute_graph_metrics_reports_correct_counts(session: Session, sample_dataset_id: str) -> None:
    graph = build_graph_for_dataset(session, sample_dataset_id)
    metrics = compute_graph_metrics(graph)
    assert metrics.node_count == 6
    assert metrics.edge_count == 6
    assert not metrics.betweenness_approximated
    assert len(metrics.top_degree) > 0


def test_compute_graph_metrics_on_empty_graph_does_not_crash() -> None:
    import networkx as nx

    metrics = compute_graph_metrics(nx.MultiDiGraph())
    assert metrics.node_count == 0
    assert metrics.top_degree == []


def test_find_shortest_path_between_connected_nodes(session: Session, sample_dataset_id: str) -> None:
    graph = build_graph_for_dataset(session, sample_dataset_id)
    path = find_shortest_path(graph, session.alice_id, session.carol_id)
    assert path is not None
    assert path[0] == session.alice_id
    assert path[-1] == session.carol_id


def test_find_shortest_path_between_disconnected_nodes_returns_none(
    session: Session, sample_dataset_id: str
) -> None:
    graph = build_graph_for_dataset(session, sample_dataset_id)
    path = find_shortest_path(graph, session.alice_id, session.dave_id)
    assert path is None


def test_get_neighborhood_respects_depth(session: Session, sample_dataset_id: str) -> None:
    graph = build_graph_for_dataset(session, sample_dataset_id)
    one_hop = get_neighborhood(graph, session.alice_id, depth=1)
    two_hop = get_neighborhood(graph, session.alice_id, depth=2)
    assert one_hop.number_of_nodes() <= two_hop.number_of_nodes()
    assert session.carol_id not in one_hop.nodes or session.carol_id in two_hop.nodes


def test_get_neighborhood_respects_max_nodes(session: Session, sample_dataset_id: str) -> None:
    graph = build_graph_for_dataset(session, sample_dataset_id)
    neighborhood = get_neighborhood(graph, session.alice_id, depth=3, max_nodes=2)
    assert neighborhood.number_of_nodes() <= 2


def test_get_neighborhood_filters_by_edge_type(session: Session, sample_dataset_id: str) -> None:
    graph = build_graph_for_dataset(session, sample_dataset_id)
    neighborhood = get_neighborhood(graph, session.alice_id, depth=2, edge_types=["KNOWS"])
    # Only Alice-Bob (KNOWS) reachable; Carol requires ASSOCIATED_WITH or TRANSFERRED_TO
    assert session.bob_id in neighborhood.nodes


def test_search_nodes_finds_by_label(session: Session, sample_dataset_id: str) -> None:
    graph = build_graph_for_dataset(session, sample_dataset_id)
    results = search_nodes(graph, "ali")
    assert any(r["id"] == session.alice_id for r in results)


def test_list_edge_types_returns_distinct_types(session: Session, sample_dataset_id: str) -> None:
    graph = build_graph_for_dataset(session, sample_dataset_id)
    edge_types = list_edge_types(graph)
    assert "WORKS_FOR" in edge_types
    assert "KNOWS" in edge_types
    assert "TRANSFERRED_TO" in edge_types


def test_detect_communities_on_small_graph(session: Session, sample_dataset_id: str) -> None:
    graph = build_graph_for_dataset(session, sample_dataset_id)
    communities = detect_communities(graph)
    assert communities is not None
    all_members = {node for community in communities for node in community}
    assert all_members.issubset(set(graph.nodes))
