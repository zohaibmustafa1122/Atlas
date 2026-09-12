"""Graph analytics: centrality measures, components, density, community
detection, and shortest path -- computed with resource limits in mind.

Exact betweenness centrality costs O(V * E) time, which is infeasible on
an 8 GB CPU-only laptop once a graph has more than a few thousand nodes.
Past LARGE_GRAPH_NODE_THRESHOLD, betweenness switches to NetworkX's
sampled/approximate variant (a bounded number of source nodes, `k`,
instead of all of them) and the result records that the value is an
approximation, rather than silently returning a number that looks exact
but was computed differently. The same threshold guards community
detection, which is also expensive on large graphs.
"""

from dataclasses import dataclass, field

import networkx as nx

LARGE_GRAPH_NODE_THRESHOLD = 3000
BETWEENNESS_SAMPLE_SIZE = 500


@dataclass
class GraphMetrics:
    """Dataset-wide graph statistics, as shown on the Graph Explorer page."""

    node_count: int
    edge_count: int
    connected_components: int
    density: float
    top_degree: list[tuple[str, float]] = field(default_factory=list)
    top_pagerank: list[tuple[str, float]] = field(default_factory=list)
    top_betweenness: list[tuple[str, float]] = field(default_factory=list)
    betweenness_approximated: bool = False


def _top_n(scores: dict[str, float], n: int) -> list[tuple[str, float]]:
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:n]


def compute_graph_metrics(graph: nx.MultiDiGraph, top_n: int = 10) -> GraphMetrics:
    """Compute degree/PageRank/betweenness centrality, components, and density.

    Betweenness is exact for graphs up to LARGE_GRAPH_NODE_THRESHOLD nodes
    and approximated (sampled) above that.
    """
    node_count = graph.number_of_nodes()
    edge_count = graph.number_of_edges()

    if node_count == 0:
        return GraphMetrics(node_count=0, edge_count=0, connected_components=0, density=0.0)

    undirected = graph.to_undirected()
    connected_components = nx.number_connected_components(undirected)
    density = round(nx.density(graph), 6)

    degree_centrality = nx.degree_centrality(graph)
    pagerank = nx.pagerank(graph, weight="weight")

    betweenness_approximated = node_count > LARGE_GRAPH_NODE_THRESHOLD
    if betweenness_approximated:
        k = min(BETWEENNESS_SAMPLE_SIZE, node_count)
        betweenness = nx.betweenness_centrality(graph, k=k, weight="weight", seed=42)
    else:
        betweenness = nx.betweenness_centrality(graph, weight="weight")

    return GraphMetrics(
        node_count=node_count,
        edge_count=edge_count,
        connected_components=connected_components,
        density=density,
        top_degree=_top_n(degree_centrality, top_n),
        top_pagerank=_top_n(pagerank, top_n),
        top_betweenness=_top_n(betweenness, top_n),
        betweenness_approximated=betweenness_approximated,
    )


def detect_communities(graph: nx.MultiDiGraph) -> list[list[str]] | None:
    """Detect communities via greedy modularity maximization.

    Returns None (rather than hanging) if the graph exceeds
    LARGE_GRAPH_NODE_THRESHOLD nodes, since modularity-based community
    detection is also expensive at that scale.
    """
    if graph.number_of_nodes() == 0 or graph.number_of_nodes() > LARGE_GRAPH_NODE_THRESHOLD:
        return None

    simple_undirected = nx.Graph(graph.to_undirected())
    if simple_undirected.number_of_edges() == 0:
        return None

    communities = nx.algorithms.community.greedy_modularity_communities(simple_undirected)
    return [sorted(community) for community in communities]


def find_shortest_path(graph: nx.MultiDiGraph, source: str, target: str) -> list[str] | None:
    """Return the shortest (unweighted) path between two nodes, or None if unreachable."""
    if source not in graph or target not in graph:
        return None
    try:
        return nx.shortest_path(graph.to_undirected(), source=source, target=target)
    except nx.NetworkXNoPath:
        return None
