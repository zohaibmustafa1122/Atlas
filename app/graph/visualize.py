"""Render a (bounded) NetworkX graph to standalone HTML using Pyvis.

Kept separate from app/graph/queries.py because this is presentation, not
a query -- Pyvis's job here is only to turn an already-bounded subgraph
(see get_neighborhood, which caps node count) into an interactive vis.js
visualization that Streamlit can embed via components.v1.html.
"""

import networkx as nx
from pyvis.network import Network

NODE_COLORS = {
    "Person": "#4C78A8",
    "Organization": "#F58518",
    "Location": "#54A24B",
    "Event": "#B279A2",
}
DEFAULT_NODE_COLOR = "#999999"


def render_graph_html(graph: nx.MultiDiGraph, height: str = "600px", highlight_node: str | None = None) -> str:
    """Return a self-contained HTML string rendering `graph` with Pyvis.

    `graph` is expected to already be small enough to render (see
    app/graph/queries.get_neighborhood) -- this function does not itself
    limit size.
    """
    net = Network(height=height, width="100%", directed=True, notebook=False, bgcolor="#ffffff")
    net.barnes_hut()

    for node_id, data in graph.nodes(data=True):
        node_type = data.get("node_type", "Unknown")
        label = str(data.get("label", node_id))[:40]
        title_lines = [f"{key}: {value}" for key, value in data.items() if value is not None]
        net.add_node(
            node_id,
            label=label,
            title="\n".join(title_lines),
            color=NODE_COLORS.get(node_type, DEFAULT_NODE_COLOR),
            borderWidth=3 if node_id == highlight_node else 1,
            size=20 if node_id == highlight_node else 12,
        )

    for source, target, data in graph.edges(data=True):
        edge_type = data.get("edge_type", "")
        net.add_edge(source, target, label=edge_type, title=edge_type, arrows="to")

    return net.generate_html(notebook=False)
