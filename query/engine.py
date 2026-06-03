from embeddings.chroma_client import semantic_search
from graph.neo4j_client import get_client


def query(question: str, top_k: int = 5) -> dict:
    """
    Hybrid query with 4 layers, auto-cascading from fast/cheap to slow/expensive.
    Returns dict with community_context, relevant_nodes, subgraph_summary.
    """
    # Layer 1: Community lookup
    communities = _find_relevant_communities(question)

    # Layer 2: Semantic search in related communities
    relevant_nodes = semantic_search(question, top_k=top_k)

    # Layer 3: Graph expansion — get neighbors
    expanded_nodes = _expand_neighbors(relevant_nodes)

    # Layer 4: Assemble context
    context = _assemble_context(communities, relevant_nodes, expanded_nodes)

    return {
        "question": question,
        "communities": communities,
        "relevant_nodes": relevant_nodes,
        "expanded_context": expanded_nodes,
        "summary": context,
    }


def _find_relevant_communities(question: str) -> list[dict]:
    """Find most relevant communities based on semantic search in community summaries."""
    from embeddings.embedder import embed_text
    import chromadb
    from config import CHROMA_PATH

    chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        comm_collection = chroma.get_collection("community_summaries")
        query_vector = embed_text(question)
        results = comm_collection.query(
            query_embeddings=[query_vector],
            n_results=3,
            include=["documents", "metadatas"],
        )
        communities = []
        for i in range(len(results["ids"][0])):
            communities.append({
                "id": results["ids"][0][i],
                "summary": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
            })
        return communities
    except Exception:
        return []


def _expand_neighbors(nodes: list[dict], hops: int = 1) -> list[dict]:
    """Expand subgraph: get neighbors of top nodes."""
    client = get_client()
    expanded = []

    for node in nodes[:3]:  # Only expand top-3 to avoid too many tokens
        name = node["metadata"].get("name", "")
        if not name:
            continue

        result = client.run("""
            MATCH (n) WHERE n.name = $name
            MATCH (n)-[:CALLS|IMPLEMENTS|DEPENDS_ON|RELATES_TO|CONTAINS*1..2]-(neighbor)
            WHERE neighbor.name IS NOT NULL AND NOT neighbor:Community
            RETURN DISTINCT neighbor.name as name,
                   labels(neighbor)[0] as type,
                   coalesce(neighbor.description, neighbor.how_it_works, neighbor.docstring) as description
            LIMIT 10
        """, {"name": name})

        for record in result:
            expanded.append({
                "name": record["name"],
                "type": record["type"],
                "description": record["description"],
                "source_node": name,
            })

    return expanded


def _assemble_context(communities, nodes, expanded) -> str:
    """Assemble context into concise text for the agent."""
    parts = []

    if communities:
        parts.append("## Relevant Areas")
        for c in communities:
            meta = c.get("metadata", {})
            parts.append(f"**{meta.get('name', 'Community')}**: {c['summary']}")

    if nodes:
        parts.append("\n## Key Elements")
        for n in nodes[:5]:
            meta = n.get("metadata", {})
            parts.append(f"- [{meta.get('type', '?')}] **{meta.get('name', '?')}**: {n.get('document', '')[:200]}")

    if expanded:
        parts.append("\n## Related Context")
        seen = set()
        for n in expanded[:8]:
            if n["name"] not in seen:
                parts.append(f"- [{n['type']}] {n['name']}: {n.get('description', '') or ''}")
                seen.add(n["name"])

    return "\n".join(parts)


def get_node_detail(name: str) -> dict:
    """Get full info about a specific node."""
    client = get_client()
    result = client.run("""
        MATCH (n) WHERE n.name = $name
        OPTIONAL MATCH (n)-[r]->(neighbor)
        OPTIONAL MATCH (caller)-[r2]->(n)
        RETURN n,
               labels(n) as labels,
               collect(DISTINCT {type: type(r), target: neighbor.name}) as outgoing,
               collect(DISTINCT {type: type(r2), source: caller.name}) as incoming
        LIMIT 1
    """, {"name": name})

    if not result:
        return {}

    record = result[0]
    node_dict = dict(record["n"])
    labels = record.get("labels", [])
    if any(l in ["Function", "Class"] for l in labels):
        node_dict["raw_code"] = client.read_node_code(node_dict)

    return {
        "node": node_dict,
        "outgoing": record["outgoing"],
        "incoming": record["incoming"],
    }


def list_open_tasks() -> list[dict]:
    """List all Task nodes not marked as done."""
    client = get_client()
    result = client.run("""
        MATCH (t:Task)
        WHERE NOT EXISTS(t.status) OR t.status <> 'done'
        OPTIONAL MATCH (t)-[:BLOCKS]->(blocked)
        RETURN t.name as name, t.description as description,
               collect(blocked.name) as blocks
        ORDER BY t.name
    """)
    return [dict(r) for r in result]
