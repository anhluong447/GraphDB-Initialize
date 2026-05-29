import sys
import os
import time

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CODEBASE_PATH


def run_full_pipeline():
    print("=" * 60)
    print("GraphRAG Full Pipeline — Level 3")
    print("=" * 60)
    print(f"Target codebase: {CODEBASE_PATH}")

    # 1. Start Docker containers
    print("\n[1/8] Starting databases...")
    import subprocess
    try:
        subprocess.run(["docker-compose", "up", "-d"], cwd=os.path.dirname(os.path.abspath(__file__)), check=True)
        print("  Waiting for Neo4j to be ready...")
        time.sleep(10)
    except FileNotFoundError:
        try:
            subprocess.run(["docker", "compose", "up", "-d"], cwd=os.path.dirname(os.path.abspath(__file__)), check=True)
            print("  Waiting for Neo4j to be ready...")
            time.sleep(10)
        except Exception as e:
            print(f"  Warning: Could not start Docker: {e}")
            print("  Make sure Neo4j is running manually.")

    # 2. Init graph indexes
    print("\n[2/8] Initializing graph schema...")
    from graph.neo4j_client import get_client
    client = get_client()
    client.create_indexes()

    # 3. Parse codebase
    print("\n[3/8] Parsing codebase...")
    from parsers.ast_parser import parse_codebase
    from parsers.doc_parser import parse_docs
    from parsers.git_parser import parse_git_history

    parsed_files = parse_codebase(CODEBASE_PATH)
    docs = parse_docs(CODEBASE_PATH)
    commits = parse_git_history(CODEBASE_PATH, max_commits=200)

    # 4. Build structural graph
    print("\n[4/8] Building structural graph...")
    from graph.builder import build_file_nodes, build_git_nodes
    build_file_nodes(parsed_files)
    build_git_nodes(commits)

    # 5. LLM extraction
    print("\n[5/8] Extracting semantic entities (LLM)...")
    from extractors.llm_extractor import batch_extract
    from graph.builder import build_semantic_nodes

    significant_files = [
        pf for pf in parsed_files
        if len(pf.get("nodes", [])) >= 3
        and len(pf.get("raw_code", "")) >= 300
    ]
    if len(significant_files) < 10:
        # Fallback to sorting by size if codebase has very few large/modular files
        significant_files = sorted(parsed_files, key=lambda x: len(x.get("raw_code", "")), reverse=True)[:30]

    all_chunks = []
    for pf in significant_files:
        all_chunks.append({"content": pf.get("raw_code", ""), "file": pf["file"]})
    all_chunks.extend(docs)

    extracted = batch_extract(all_chunks)
    build_semantic_nodes(extracted)

    # 6. Embed nodes
    print("\n[6/8] Embedding nodes...")
    from embeddings.chroma_client import embed_all_nodes
    embed_all_nodes()

    # 7. Community detection
    print("\n[7/8] Detecting communities...")
    from community.detector import detect_communities
    from community.summarizer import summarize_all_communities
    detect_communities()
    summarize_all_communities()

    # 8. Done
    print("\n[8/8] Pipeline complete!")
    print("\n" + "=" * 60)
    print("✅ GraphRAG pipeline finished successfully!")
    print("=" * 60)
    print(f"\n   Neo4j Browser:     http://localhost:7474")
    print(f"   GraphRAG API:      http://localhost:8080")
    print(f"   Visualization UI:  http://localhost:5173")
    print(f"\nTo start the API server:")
    print(f"   cd D:\\GraphRAG")
    print(f"   .\\venv\\Scripts\\activate")
    print(f"   uvicorn visualization.backend.api:app --host 0.0.0.0 --port 8080 --reload")
    print(f"\nTo start the frontend:")
    print(f"   cd D:\\GraphRAG\\visualization\\frontend")
    print(f"   npm run dev")


if __name__ == "__main__":
    run_full_pipeline()
