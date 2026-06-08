import openai
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
from graph.neo4j_client import get_client

_openai_client = None

def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL
        _openai_client = openai.OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
        )
    return _openai_client


def build_node_text(node_record: dict, relations_dict: dict = None) -> str:
    """
    Build a comprehensive text representation of a node, including graph relations.
    This is critical — the vector must carry relationship info, not just content.
    """
    name = node_record.get("name", "")
    node_type = node_record.get("type", "")
    description = node_record.get("description", "") or node_record.get("docstring", "")
    how_it_works = node_record.get("how_it_works", "")
    input_spec = node_record.get("input_spec", "")
    output_spec = node_record.get("output_spec", "")

    if relations_dict is not None:
        rel_info = relations_dict.get(name, {"outgoing": [], "incoming": []})
        outgoing = rel_info["outgoing"]
        incoming = rel_info["incoming"]
    else:
        client = get_client()

        # Get outgoing neighbors from graph
        result = client.run("""
            MATCH (n) WHERE n.name = $name
            OPTIONAL MATCH (n)-[r]->(neighbor)
            RETURN type(r) as rel_type, neighbor.name as neighbor_name
            LIMIT 20
        """, {"name": name})

        outgoing = [f"{r['rel_type']} → {r['neighbor_name']}" for r in result if r['neighbor_name']]

        result2 = client.run("""
            MATCH (n) WHERE n.name = $name
            OPTIONAL MATCH (neighbor)-[r]->(n)
            RETURN type(r) as rel_type, neighbor.name as neighbor_name
            LIMIT 10
        """, {"name": name})

        incoming = [f"{r['neighbor_name']} → {r['rel_type']}" for r in result2 if r['neighbor_name']]

    text = f"""
{node_type}: {name}
Description: {description}
How it works: {how_it_works}
Inputs: {input_spec}
Outputs: {output_spec}
Outgoing relations: {', '.join(outgoing) if outgoing else 'none'}
Incoming relations: {', '.join(incoming) if incoming else 'none'}
""".strip()

    return text


def embed_text(text: str) -> list[float]:
    """Embed a text string into a vector using OpenRouter embeddings API."""
    import config
    response = _get_openai_client().embeddings.create(
        model=config.EMBEDDING_MODEL,
        input=text[:8000],
        dimensions=config.EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of text strings into vectors in a single batch API call."""
    if not texts:
        return []
    import config
    # Truncate each text to 8000 chars to avoid model limits
    truncated = [t[:8000] for t in texts]
    response = _get_openai_client().embeddings.create(
        model=config.EMBEDDING_MODEL,
        input=truncated,
        dimensions=config.EMBEDDING_DIMENSIONS,
    )
    return [item.embedding for item in response.data]
