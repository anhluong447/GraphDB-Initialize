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

    # --- Fallback Logic (Fix C) ---
    def count_tokens_local(text: str) -> int:
        return len(text.split()) * 4 // 3

    FALLBACK_NODE_THRESHOLD = 3
    FALLBACK_TOKEN_THRESHOLD = 600

    if len(relevant_nodes) < FALLBACK_NODE_THRESHOLD or count_tokens_local(context) < FALLBACK_TOKEN_THRESHOLD:
        import os
        from config import CODEBASE_PATH
        # Extract unique file paths from matched nodes
        seen_files = []
        for n in relevant_nodes:
            meta = n.get("metadata", {})
            fp = meta.get("file")
            if fp and fp not in seen_files:
                seen_files.append(fp)
        
        fallback_parts = []
        for f in seen_files[:2]:  # cap at 2 files to avoid token bloat
            # Query Neo4j for nodes in this file to fetch their codes using read_node_code
            res = client.run("""
                MATCH (n) WHERE n.file = $file AND n.start_line IS NOT NULL AND n.end_line IS NOT NULL
                RETURN n.file as file, n.start_line as start_line, n.end_line as end_line, n.raw_code as raw_code, n.name as name
                ORDER BY n.start_line ASC
            """, {"file": f})
            
            if res:
                file_chunks = []
                for record in res:
                    node_info = dict(record)
                    code_chunk = client.read_node_code(node_info)
                    if code_chunk:
                        file_chunks.append(f"# Node: {node_info.get('name')}\n{code_chunk}")
                if file_chunks:
                    fallback_parts.append(f"### Fallback Source for File: {f}\n```python\n" + "\n\n".join(file_chunks) + "\n```\n")
            else:
                # Fallback to reading the whole file using read_node_code with just file path
                code_content = client.read_node_code({"file": f})
                if code_content:
                    fallback_parts.append(f"### Fallback Source for File: {f}\n```python\n{code_content}\n```\n")
        
        if fallback_parts:
            context += "\n\n## Fallback Source Context\n" + "\n".join(fallback_parts)

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
            MATCH (n) WHERE n.name = $name AND n.file IS NOT NULL
            MATCH (n)-[:CALLS|IMPLEMENTS|DEPENDS_ON|RELATES_TO|CONTAINS*1..2]-(neighbor)
            WHERE neighbor.name IS NOT NULL AND neighbor.file IS NOT NULL AND NOT neighbor:Community
            WITH DISTINCT neighbor
            WITH neighbor,
                 CASE WHEN neighbor.is_entry_point THEN 1 ELSE 0 END AS ep_boost,
                 coalesce(neighbor.complexity, 0) as comp
            RETURN neighbor.name as name,
                   labels(neighbor)[0] as type,
                   coalesce(neighbor.description, neighbor.how_it_works, neighbor.docstring) as description
            ORDER BY ep_boost DESC, comp DESC
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
        OPTIONAL MATCH (n:Class)-[:HAS_ATTRIBUTE]->(attr:ClassAttribute)
        WITH n, labels(n) as labels,
             collect(DISTINCT {type: type(r), target: neighbor.name}) as outgoing,
             collect(DISTINCT {type: type(r2), source: caller.name}) as incoming,
             collect(DISTINCT {
                 name: attr.name,
                 type: attr.type_hint,
                 default: attr.default_value,
                 is_field: attr.is_dataclass_field
             }) AS attributes
        RETURN n, labels, outgoing, incoming, attributes
        LIMIT 1
    """, {"name": name})

    if not result:
        return {}

    record = result[0]
    node_dict = dict(record["n"])
    labels = record.get("labels", [])
    if any(l in ["Function", "Class"] for l in labels):
        node_dict["raw_code"] = client.read_node_code(node_dict)

    raw_attrs = record.get("attributes", [])
    attributes = [a for a in raw_attrs if a.get("name") is not None]

    return {
        "node": node_dict,
        "outgoing": record["outgoing"],
        "incoming": record["incoming"],
        "attributes": attributes,
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
