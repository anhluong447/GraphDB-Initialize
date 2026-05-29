import chromadb
from embeddings.embedder import build_node_text, embed_text, embed_texts
from graph.neo4j_client import get_client
from config import CHROMA_PATH

chroma = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma.get_or_create_collection("graphrag_nodes")


def embed_all_nodes():
    """Embed all nodes in Neo4j and save to ChromaDB in batches."""
    client = get_client()

    print("[Chroma] Fetching relations map from Neo4j...")
    all_relations = client.run("""
        MATCH (a)-[r]->(b)
        WHERE a.name IS NOT NULL AND b.name IS NOT NULL
        RETURN a.name as from_name, type(r) as rel, b.name as to_name
    """)
    relations_dict = {}
    for r in all_relations:
        from_name = r["from_name"]
        rel = r["rel"]
        to_name = r["to_name"]
        if from_name not in relations_dict:
            relations_dict[from_name] = {"outgoing": [], "incoming": []}
        if to_name not in relations_dict:
            relations_dict[to_name] = {"outgoing": [], "incoming": []}
        if len(relations_dict[from_name]["outgoing"]) < 20:
            relations_dict[from_name]["outgoing"].append(f"{rel} → {to_name}")
        if len(relations_dict[to_name]["incoming"]) < 10:
            relations_dict[to_name]["incoming"].append(f"{from_name} → {rel}")

    labels = ["Function", "Class", "Concept", "Feature", "Decision", "Risk", "Task"]
    total = 0

    for label in labels:
        nodes = client.run(f"MATCH (n:{label}) RETURN n")
        batch_ids, batch_docs, batch_metas = [], [], []

        for record in nodes:
            node = dict(record["n"])
            node["type"] = label
            node_id = f"{label}:{node.get('name', '')}:{node.get('file', '')}"

            text = build_node_text(node, relations_dict)
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


def embed_nodes_for_files(file_paths: list[str]):
    """Embed only the nodes defined in specific files and update/upsert them in ChromaDB."""
    client = get_client()
    labels = ["Function", "Class"]

    # 1. Clean up old embeddings for these files to handle deleted functions/classes
    try:
        for fp in file_paths:
            collection.delete(where={"file": fp})
        print(f"[Chroma] Cleared old embeddings for files: {file_paths}")
    except Exception as e:
        print(f"[Chroma] Warning: failed to delete old embeddings: {e}")

    # 2. Fetch relations from Neo4j in a single query
    all_relations = client.run("""
        MATCH (a)-[r]->(b)
        WHERE a.name IS NOT NULL AND b.name IS NOT NULL
        RETURN a.name as from_name, type(r) as rel, b.name as to_name
    """)
    relations_dict = {}
    for r in all_relations:
        from_name = r["from_name"]
        rel = r["rel"]
        to_name = r["to_name"]
        if from_name not in relations_dict:
            relations_dict[from_name] = {"outgoing": [], "incoming": []}
        if to_name not in relations_dict:
            relations_dict[to_name] = {"outgoing": [], "incoming": []}
        if len(relations_dict[from_name]["outgoing"]) < 20:
            relations_dict[from_name]["outgoing"].append(f"{rel} → {to_name}")
        if len(relations_dict[to_name]["incoming"]) < 10:
            relations_dict[to_name]["incoming"].append(f"{from_name} → {rel}")

    total = 0
    for label in labels:
        nodes = client.run(f"""
            MATCH (n:{label})
            WHERE n.file IN $file_paths
            RETURN n
        """, {"file_paths": file_paths})

        batch_ids, batch_docs, batch_metas = [], [], []

        for record in nodes:
            node = dict(record["n"])
            node["type"] = label
            node_id = f"{label}:{node.get('name', '')}:{node.get('file', '')}"

            text = build_node_text(node, relations_dict)
            batch_ids.append(node_id)
            batch_docs.append(text)
            batch_metas.append({"type": label, "name": node.get("name", ""), "file": node.get("file", "")})

            if len(batch_ids) >= 50:
                try:
                    vectors = embed_texts(batch_docs)
                    collection.upsert(ids=batch_ids, documents=batch_docs,
                                      metadatas=batch_metas, embeddings=vectors)
                    total += len(batch_ids)
                    print(f"[Chroma] Embedded incremental batch ({total} total)...")
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

    print(f"[Chroma] Incrementally embedded {total} nodes for files: {file_paths}")


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
