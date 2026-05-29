import openai
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, EMBEDDING_MODEL
from graph.neo4j_client import get_client

openai_client = openai.OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
)


def build_node_text(node_record: dict) -> str:
    """
    Build a comprehensive text representation of a node, including graph relations.
    This is critical — the vector must carry relationship info, not just content.
    """
    name = node_record.get("name", "")
    node_type = node_record.get("type", "")
    description = node_record.get("description", "")
    raw_code = node_record.get("raw_code", "")[:500]

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
Outgoing relations: {', '.join(outgoing) if outgoing else 'none'}
Incoming relations: {', '.join(incoming) if incoming else 'none'}
Code preview: {raw_code}
""".strip()

    return text


def embed_text(text: str) -> list[float]:
    """Embed a text string into a vector using OpenRouter embeddings API."""
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text[:8000],
    )
    return response.data[0].embedding


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of text strings into vectors in a single batch API call."""
    if not texts:
        return []
    # Truncate each text to 8000 chars to avoid model limits
    truncated = [t[:8000] for t in texts]
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=truncated,
    )
    return [item.embedding for item in response.data]
