import chromadb
from embeddings.embedder import build_node_text, embed_text, embed_texts
from graph.neo4j_client import get_client
from config import CHROMA_PATH

chroma = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma.get_or_create_collection("graphrag_nodes")


def embed_all_nodes():
    """Embed all nodes in Neo4j and save to ChromaDB in batches."""
    client = get_client()

    labels = ["Function", "Class", "Concept", "Feature", "Decision", "Risk", "Task"]
    total = 0

    for label in labels:
        nodes = client.run(f"MATCH (n:{label}) RETURN n")
        batch_ids, batch_docs, batch_metas = [], [], []

        for record in nodes:
            node = dict(record["n"])
            node["type"] = label
            node_id = f"{label}:{node.get('name', '')}:{node.get('file', '')}"

            text = build_node_text(node)
            batch_ids.append(node_id)
            batch_docs.append(text)
            batch_metas.append({"type": label, "name": node.get("name", ""), "file": node.get("file", "")})

            if len(batch_ids) >= 50:
                try:
                    vectors = embed_texts(batch_docs)
                    collection.upsert(ids=batch_ids, documents=batch_docs,
                                      metadatas=batch_metas, embeddings=vectors)
                    total += len(batch_ids)
                    print(f"[Chroma] Embedded batch ({total} total)...")
                except Exception as e:
                    print(f"[Chroma] Batch embedding error: {e}")
                batch_ids, batch_docs, batch_metas = [], [], []

        if batch_ids:
            try:
                vectors = embed_texts(batch_docs)
                collection.upsert(ids=batch_ids, documents=batch_docs,
                                  metadatas=batch_metas, embeddings=vectors)
                total += len(batch_ids)
            except Exception as e:
                print(f"[Chroma] Batch embedding error for final batch: {e}")

    print(f"[Chroma] Embedded {total} nodes total.")


def semantic_search(query: str, top_k: int = 10, filter_type: str = None) -> list[dict]:
    """Find most relevant nodes by cosine similarity."""
    query_vector = embed_text(query)
    where = {"type": filter_type} if filter_type else None

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    output = []
    if results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            output.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "score": 1 - results["distances"][0][i],
            })
    return output
