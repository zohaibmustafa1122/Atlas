"""Bounded graph queries for interactive exploration.

The one rule every function here follows: never return more than
`max_nodes` nodes. A dataset can have 100,000 entities; rendering all of
them in a single interactive graph view would exhaust an 8 GB laptop's
memory and be unreadable regardless. Instead, exploration always starts
from a specific node and expands outward a bounded number of hops,
capped at `max_nodes` (see docs/architecture.md section 5).
"""

import networkx as nx

DEFAULT_MAX_NODES = 300


def search_nodes(graph: nx.MultiDiGraph, query: str, node_types: list[str] | None = None, limit: int = 25) -> list[dict]:
    """Case-insensitive substring search over node labels in an in-memory graph.

    Kept for graphs already loaded into memory (e.g. reused across several
    Graph Explorer interactions); for a fresh, indexed search over the
    database itself, prefer EntityRepository.search_entities instead, which
    scales better for large datasets.
    """
    query_norm = query.strip().lower()
    if not query_norm:
        return []

    results = []
    for node_id, data in graph.nodes(data=True):
        if node_types and data.get("node_type") not in node_types:
            continue
        label = str(data.get("label", ""))
        if query_norm in label.lower():
            results.append({"id": node_id, **data})
        if len(results) >= limit:
            break
    return results


def get_neighborhood(
    graph: nx.MultiDiGraph,
    center_id: str,
    depth: int = 1,
    edge_types: list[str] | None = None,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> nx.MultiDiGraph:
    """Return the induced subgraph reachable from `center_id` within `depth`
    hops, following only edges whose type is in `edge_types` (or all edges,
    if not given), capped at `max_nodes` total nodes.

    This is a breadth-first expansion rather than nx.ego_graph because we
    need to filter by edge type as we expand, not just by hop count.
    """
    if center_id not in graph:
        return graph.__class__()

    visited = {center_id}
    frontier = {center_id}

    for _ in range(depth):
        if len(visited) >= max_nodes:
            break
        next_frontier: set[str] = set()
        for node in frontier:
            for _, neighbor, data in graph.out_edges(node, data=True):
                if edge_types and data.get("edge_type") not in edge_types:
                    continue
                next_frontier.add(neighbor)
            for neighbor, _, data in graph.in_edges(node, data=True):
                if edge_types and data.get("edge_type") not in edge_types:
                    continue
                next_frontier.add(neighbor)
        next_frontier -= visited
        visited |= next_frontier
        frontier = next_frontier
        if not frontier:
            break

    limited_nodes = list(visited)[:max_nodes]
    return graph.subgraph(limited_nodes).copy()


def list_edge_types(graph: nx.MultiDiGraph) -> list[str]:
    """Return the distinct edge types present in a graph, for filter UIs."""
    return sorted({data.get("edge_type", "UNKNOWN") for _, _, data in graph.edges(data=True)})
