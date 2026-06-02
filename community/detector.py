import networkx as nx
import igraph as ig
import leidenalg
from graph.neo4j_client import get_client


def build_networkx_graph() -> nx.Graph:
    """Convert Neo4j graph to NetworkX graph for algorithms."""
    client = get_client()

    G = nx.Graph()

    # Get all nodes
    nodes = client.run("MATCH (n) WHERE n.name IS NOT NULL RETURN elementId(n) as id, labels(n) as labels, n.name as name")
    for record in nodes:
        G.add_node(record["id"], name=record["name"], label=record["labels"][0] if record["labels"] else "Unknown")

    # Get all edges
    edges = client.run("MATCH (a)-[r]->(b) WHERE a.name IS NOT NULL AND b.name IS NOT NULL RETURN elementId(a) as from_id, elementId(b) as to_id, type(r) as rel_type")
    for record in edges:
        G.add_edge(record["from_id"], record["to_id"], rel_type=record["rel_type"])

    print(f"[Community] NetworkX graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G


def detect_communities() -> dict:
    """
    Run Leiden algorithm via igraph/leidenalg.
    Returns mapping node_id -> community_id.
    Saves community_id to Neo4j nodes.
    """
    G = build_networkx_graph()
    if G.number_of_nodes() == 0:
        print("[Community] Empty graph, skipping community detection.")
        return {}

    # Convert NetworkX to igraph
    nx_nodes = list(G.nodes())
    node_id_map = {n: i for i, n in enumerate(nx_nodes)}

    ig_graph = ig.Graph()
    ig_graph.add_vertices(len(nx_nodes))

    for u, v in G.edges():
        ig_graph.add_edge(node_id_map[u], node_id_map[v])

    # Run Leiden algorithm
    partition = leidenalg.find_partition(ig_graph, leidenalg.ModularityVertexPartition)

    # Build result mapping: neo4j_node_id -> community_id
    result = {}
    for community_id, members in enumerate(partition):
        for member_idx in members:
            neo4j_id = nx_nodes[member_idx]
            result[neo4j_id] = community_id

    print(f"[Community] Detected {len(partition)} communities.")

    # Save community IDs to Neo4j
    client = get_client()
    for node_id, community_id in result.items():
        client.run("""
            MATCH (n) WHERE elementId(n) = $node_id
            SET n.community_id = $community_id
        """, {"node_id": node_id, "community_id": community_id})

    return result
