from __future__ import annotations

import networkx as nx
from typing import List, Dict
from .models import NormalizedFinding, AttackStep, AttackPath
import uuid

# Deterministic correlation rules mapping categories to next step labels
_CORRELATION_MAP: Dict[str, str] = {
    "secret": "Cloud Access",
    "dependency": "Remote Code Execution",
    "privilege_escalation": "Data Exposure",
}

def build_graph(findings: List[NormalizedFinding]) -> nx.DiGraph:
    """Build a directed graph linking findings according to correlation rules.

    Each finding becomes a node. For a finding whose ``category`` matches a key in
    ``_CORRELATION_MAP`` an edge is added to an abstract intermediate node that
    represents the correlated step.
    """
    graph = nx.DiGraph()

    # Add finding nodes
    for f in findings:
        node_id = f.id
        label = f.title if f.title else f.category
        graph.add_node(node_id, step=AttackStep(label=label, finding_id=f.id))

    # Add correlation edges using abstract intermediate nodes
    for f in findings:
        next_label = _CORRELATION_MAP.get(f.category)
        if not next_label:
            continue
        # Create a unique intermediate node for this correlation type if not exists
        inter_id = f"{f.category}_intermediate"
        if not graph.has_node(inter_id):
            graph.add_node(inter_id, step=AttackStep(label=next_label))
        graph.add_edge(f.id, inter_id)

    return graph

def extract_paths(graph: nx.DiGraph) -> List[AttackPath]:
    """Extract all linear paths from source finding nodes to leaf nodes.

    The function walks each source node (nodes without incoming edges) to every
    reachable leaf (nodes without outgoing edges) and builds an ``AttackPath``
    consisting of the ordered ``AttackStep`` objects.
    """
    paths: List[AttackPath] = []
    sources = [n for n in graph.nodes if graph.in_degree(n) == 0]
    leaves = [n for n in graph.nodes if graph.out_degree(n) == 0]

    for src in sources:
        for leaf in leaves:
            if src == leaf:
                continue
            try:
                for node_path in nx.all_simple_paths(graph, source=src, target=leaf):
                    steps = [graph.nodes[n]["step"] for n in node_path]
                    path_id = str(uuid.uuid4())
                    paths.append(AttackPath(id=path_id, steps=steps, risk_score=0.0))
            except nx.NetworkXNoPath:
                continue
    return paths
