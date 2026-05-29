import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from graph.neo4j_client import get_client
from parsers.ast_parser import parse_codebase
from graph.builder import build_file_nodes
from embeddings.chroma_client import chroma
from embeddings.embedder import build_node_text, embed_texts

def main():
    # Set stdout to UTF-8
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    # 1. Delete Function and Class nodes from Neo4j
    print("Deleting Function and Class nodes from Neo4j...")
    client = get_client()
    client.run("MATCH (n:Function) DETACH DELETE n")
    client.run("MATCH (c:Class) DETACH DELETE c")

    # 2. Delete Function and Class documents from ChromaDB
    print("Deleting Function and Class embeddings from ChromaDB...")
    collection = chroma.get_or_create_collection("graphrag_nodes")
    try:
        collection.delete(where={"type": "Function"})
        collection.delete(where={"type": "Class"})
    except Exception as e:
        print(f"Error clearing ChromaDB: {e}")

    # 3. Parse codebase with fixed AST parser
    print("Parsing codebase...")
    parsed_files = parse_codebase()

    # 4. Rebuild File -> Function/Class nodes and CALLS relationships in Neo4j
    print("Rebuilding nodes in Neo4j...")
    build_file_nodes(parsed_files)

    # 5. Embed only the new Function and Class nodes into ChromaDB
    print("Embedding new Function and Class nodes into ChromaDB...")
    total = 0
    for label in ["Function", "Class"]:
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

    print(f"Rebuild complete! Rebuilt and embedded {total} code nodes successfully.")

if __name__ == "__main__":
    main()
