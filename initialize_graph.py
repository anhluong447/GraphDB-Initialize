"""
GraphRAG Knowledge Base Initializer & Incremental Sync Engine

Usage:
    python initialize_graph.py              # Auto-detect: full init or incremental sync
    python initialize_graph.py --force-init # Force full re-initialization
"""

import sys
import os
import json
import time
import argparse
import subprocess

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    CODEBASE_PATH, SUPPORTED_LANGUAGES, IGNORE_DIRS,
    GRAPHRAG_DATA_DIR, NEO4J_DATA_DIR, NEO4J_LOGS_DIR,
    SYNC_STATE_PATH,
)

GRAPHRAG_ROOT = os.path.dirname(os.path.abspath(__file__))


# ═══════════════════════════════════════════════════════════
# Utility helpers
# ═══════════════════════════════════════════════════════════

def _ensure_data_dirs():
    """Create .graphrag_data directories if they don't exist."""
    for d in [GRAPHRAG_DATA_DIR, NEO4J_DATA_DIR, NEO4J_LOGS_DIR]:
        os.makedirs(d, exist_ok=True)


def _load_sync_state() -> dict | None:
    """Load sync_state.json, returns None if not found."""
    if os.path.exists(SYNC_STATE_PATH):
        with open(SYNC_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_sync_state(state: dict):
    """Save sync_state.json."""
    with open(SYNC_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _get_head_commit(repo_path: str) -> str | None:
    """Get current HEAD commit hash."""
    try:
        import git
        repo = git.Repo(repo_path)
        return repo.head.commit.hexsha
    except Exception:
        return None


def _wait_for_neo4j(timeout=60):
    """Wait for Neo4j to become fully responsive to Bolt connection requests."""
    from neo4j import GraphDatabase
    from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    start_time = time.time()
    print("  Connecting to Neo4j database", end="", flush=True)
    while time.time() - start_time < timeout:
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                session.run("RETURN 1").single()
            driver.close()
            print(" -> Connection successful! Neo4j is ready.")
            return True
        except Exception:
            print(".", end="", flush=True)
            time.sleep(2)
    print("\n  ⚠ Warning: Neo4j did not respond within the timeout. Proceeding anyway...")
    return False


def _start_docker():
    """Start Docker containers with env vars for Neo4j volumes."""
    env = os.environ.copy()
    env["NEO4J_DATA_DIR"] = NEO4J_DATA_DIR
    env["NEO4J_LOGS_DIR"] = NEO4J_LOGS_DIR

    started = False
    for cmd in [["docker-compose", "up", "-d"], ["docker", "compose", "up", "-d"]]:
        try:
            subprocess.run(cmd, cwd=GRAPHRAG_ROOT, check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            started = True
            break
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"  Warning: Docker command failed: {e}")

    if not started:
        print("  ⚠ Could not start Docker. Make sure Neo4j is running manually.")

    _wait_for_neo4j()


def _is_supported_file(file_path: str) -> bool:
    """Check if a file has a supported extension for AST parsing."""
    from pathlib import Path
    return Path(file_path).suffix in SUPPORTED_LANGUAGES


def _auto_update_parent_gitignore():
    """Automatically append GraphRAG ignore patterns to the parent project's .gitignore."""
    parent_gitignore = os.path.join(CODEBASE_PATH, ".gitignore")
    subfolder_name = os.path.relpath(GRAPHRAG_ROOT, CODEBASE_PATH).replace("\\", "/")
    
    lines_to_add = [
        "",
        "# GraphRAG data and subfolder venv",
        ".graphrag_data/",
        f"{subfolder_name}/venv/",
        f"{subfolder_name}/.env",
    ]
    
    try:
        content = ""
        if os.path.exists(parent_gitignore):
            with open(parent_gitignore, "r", encoding="utf-8") as f:
                content = f.read()
        
        # Check if already added
        if ".graphrag_data/" not in content:
            with open(parent_gitignore, "a", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines_to_add) + "\n")
            print("[Sync] Automatically appended GraphRAG patterns to parent .gitignore.")
    except Exception as e:
        print(f"[Sync] Warning: Could not update parent .gitignore: {e}")


def _auto_generate_parent_launchers():
    """Generate run_graphrag.bat and run_graphrag.sh at the parent project root."""
    subfolder_name = os.path.relpath(GRAPHRAG_ROOT, CODEBASE_PATH).replace("\\", "/")

    # 1. Windows Launcher
    bat_path = os.path.join(CODEBASE_PATH, "run_graphrag.bat")
    bat_content = f"""@echo off
setlocal
cd /d "%~dp0"
if not exist "{subfolder_name}\\venv" (
    echo [GraphRAG] Virtual environment not found in {subfolder_name}. Creating one...
    python -m venv {subfolder_name}\\venv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment.
        exit /b 1
    )
    echo [GraphRAG] Installing dependencies...
    call {subfolder_name}\\venv\\Scripts\\activate.bat
    pip install -r {subfolder_name}\\requirements.txt
) else (
    call {subfolder_name}\\venv\\Scripts\\activate.bat
)
python {subfolder_name}\\initialize_graph.py %*
"""

    # 2. Unix Launcher
    sh_path = os.path.join(CODEBASE_PATH, "run_graphrag.sh")
    sh_content = f"""#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d "{subfolder_name}/venv" ]; then
    echo "[GraphRAG] Virtual environment not found in {subfolder_name}. Creating one..."
    python3 -m venv {subfolder_name}/venv
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create virtual environment."
        exit 1
    fi
    echo "[GraphRAG] Installing dependencies..."
    source {subfolder_name}/venv/bin/activate
    pip install -r {subfolder_name}/requirements.txt
else
    source {subfolder_name}/venv/bin/activate
fi
python3 {subfolder_name}/initialize_graph.py "$@"
"""

    try:
        # Write .bat
        with open(bat_path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(bat_content)
        
        # Write .sh
        with open(sh_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(sh_content)
        
        # Make sh executable
        try:
            import stat
            st = os.stat(sh_path)
            os.chmod(sh_path, st.st_mode | stat.S_IEXEC)
        except Exception:
            pass
            
        print("[Sync] Generated project root launchers: run_graphrag.bat & run_graphrag.sh")
    except Exception as e:
        print(f"[Sync] Warning: Could not generate launcher scripts: {e}")



# ═══════════════════════════════════════════════════════════
# Git-Diff Engine
# ═══════════════════════════════════════════════════════════

def _get_changed_files(repo_path: str, last_commit_hash: str) -> dict:
    """
    Get files changed since last sync using local git diff.
    Returns {"modified": [...], "deleted": [...]}
    """
    import git
    try:
        repo = git.Repo(repo_path)
    except git.InvalidGitRepositoryError:
        print("[Sync] No git repository found. Cannot compute diff.")
        return {"modified": [], "deleted": []}

    modified = set()
    deleted = set()

    # 1. Changes between last synced commit and current HEAD
    try:
        last_commit = repo.commit(last_commit_hash)
        head_commit = repo.head.commit
        if last_commit_hash != head_commit.hexsha:
            diff_index = last_commit.diff(head_commit)
            for diff_item in diff_index:
                if diff_item.change_type == 'D':
                    deleted.add(diff_item.a_path)
                else:  # A, M, R, T
                    path = diff_item.b_path or diff_item.a_path
                    modified.add(path)
    except Exception as e:
        print(f"[Sync] Warning: Could not diff commits: {e}")

    # 2. Unstaged changes (working tree vs index)
    try:
        for diff_item in repo.index.diff(None):
            if diff_item.change_type == 'D':
                deleted.add(diff_item.a_path)
            else:
                path = diff_item.b_path or diff_item.a_path
                modified.add(path)
    except Exception as e:
        print(f"[Sync] Warning: Could not get unstaged changes: {e}")

    # 3. Staged changes (index vs HEAD)
    try:
        for diff_item in repo.index.diff(repo.head.commit):
            if diff_item.change_type == 'D':
                deleted.add(diff_item.a_path)
            else:
                path = diff_item.b_path or diff_item.a_path
                modified.add(path)
    except Exception as e:
        print(f"[Sync] Warning: Could not get staged changes: {e}")

    # 4. Untracked files (new files not yet added to git)
    try:
        for f in repo.untracked_files:
            modified.add(f)
    except Exception as e:
        print(f"[Sync] Warning: Could not get untracked files: {e}")

    # Remove deleted from modified (if a file was modified then deleted)
    modified -= deleted

    # Convert to absolute paths and filter supported files
    def to_abs(rel_path):
        return os.path.join(repo_path, rel_path).replace("\\", "/")

    modified_abs = [to_abs(f) for f in modified if _is_supported_file(f)]
    deleted_abs = [to_abs(f) for f in deleted if _is_supported_file(f)]

    # Filter out files in ignored directories
    def not_ignored(path):
        parts = path.replace("\\", "/").split("/")
        return not any(p in IGNORE_DIRS for p in parts)

    modified_abs = [f for f in modified_abs if not_ignored(f)]
    deleted_abs = [f for f in deleted_abs if not_ignored(f)]

    return {"modified": modified_abs, "deleted": deleted_abs}


# ═══════════════════════════════════════════════════════════
# Full Initialization Pipeline
# ═══════════════════════════════════════════════════════════

def run_full_init():
    """Run the complete initialization pipeline from scratch."""
    print("=" * 60)
    print("GraphRAG — Full Initialization")
    print("=" * 60)
    print(f"Target codebase : {CODEBASE_PATH}")
    print(f"Data directory  : {GRAPHRAG_DATA_DIR}")

    _ensure_data_dirs()

    # 1. Start Docker
    print("\n[1/8] Starting databases...")
    _start_docker()

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
    from graph.builder import build_file_nodes, build_git_nodes, build_semantic_nodes, link_commits_to_functions
    build_file_nodes(parsed_files)
    build_git_nodes(commits)

    # 4b. Link commits to functions they changed
    print("\n[4b/8] Linking commits to changed functions...")
    link_commits_to_functions(commits, parsed_files, CODEBASE_PATH)

    # 5. LLM extraction
    print("\n[5/8] Extracting semantic entities (LLM)...")
    from extractors.llm_extractor import batch_extract

    significant_files = [
        pf for pf in parsed_files
        if len(pf.get("nodes", [])) >= 3 and len(pf.get("raw_code", "")) >= 300
    ]
    if len(significant_files) < 10:
        significant_files = sorted(parsed_files, key=lambda x: len(x.get("raw_code", "")), reverse=True)[:30]

    all_chunks = [{"content": pf.get("raw_code", ""), "file": pf["file"]} for pf in significant_files]
    all_chunks.extend(docs)

    extracted = batch_extract(all_chunks)
    build_semantic_nodes(extracted)

    # 6. Embed nodes
    print("\n[6/8] Embedding nodes...")
    from embeddings.chroma_client import embed_all_nodes
    embed_all_nodes()

    # 7. AI Testing Enrichment
    print("\n[7/8] Enriching functions with AI test specs...")
    from extractors.testing_enricher import enrich_all_functions
    enrich_all_functions()

    # 8. Community detection
    print("\n[8/8] Detecting communities...")
    from community.detector import detect_communities
    from community.summarizer import summarize_all_communities
    detect_communities()
    summarize_all_communities()

    # Save sync state
    head = _get_head_commit(CODEBASE_PATH)
    _save_sync_state({
        "last_synced_commit": head,
        "last_sync_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "codebase_path": CODEBASE_PATH,
        "mode": "full_init",
    })

    print("\n" + "=" * 60)
    print("✅ Full initialization complete!")
    print("=" * 60)
    print(f"   Data stored at: {GRAPHRAG_DATA_DIR}")
    print(f"   Neo4j Browser:  http://localhost:7474")


# ═══════════════════════════════════════════════════════════
# Incremental Sync Pipeline
# ═══════════════════════════════════════════════════════════

def run_incremental_sync():
    """Run incremental sync based on git diff since last sync."""
    sync_state = _load_sync_state()
    last_commit = sync_state["last_synced_commit"]

    print("=" * 60)
    print("GraphRAG — Incremental Sync")
    print("=" * 60)
    print(f"Target codebase : {CODEBASE_PATH}")
    print(f"Last synced     : {sync_state.get('last_sync_time', 'unknown')}")
    print(f"Last commit     : {last_commit[:8] if last_commit else 'N/A'}")

    # Ensure Docker is running
    print("\n[1/6] Ensuring databases are running...")
    _start_docker()

    # Compute diff
    print("\n[2/6] Computing git diff...")
    changes = _get_changed_files(CODEBASE_PATH, last_commit)

    modified_files = changes["modified"]
    deleted_files = changes["deleted"]

    if not modified_files and not deleted_files:
        print("\n✅ No changes detected. Graph is up to date.")
        return

    print(f"  Modified/Added : {len(modified_files)} files")
    print(f"  Deleted        : {len(deleted_files)} files")
    for f in modified_files[:10]:
        print(f"    + {os.path.basename(f)}")
    for f in deleted_files[:10]:
        print(f"    - {os.path.basename(f)}")

    from graph.neo4j_client import get_client
    client = get_client()

    # Clean up deleted files
    print("\n[3/6] Cleaning up deleted/modified nodes...")
    all_affected_files = deleted_files + modified_files
    for file_path in all_affected_files:
        # Delete Function and Class nodes belonging to this file
        client.run("""
            MATCH (n) WHERE n.file = $file AND (n:Function OR n:Class)
            DETACH DELETE n
        """, {"file": file_path})
        # Delete File node for deleted files
        if file_path in deleted_files:
            client.run("MATCH (f:File {path: $path}) DETACH DELETE f", {"path": file_path})

    # Clean up ChromaDB embeddings for affected files
    from embeddings.chroma_client import collection
    for file_path in all_affected_files:
        try:
            collection.delete(where={"file": file_path})
        except Exception:
            pass

    # Re-parse and rebuild modified files
    print("\n[4/6] Re-parsing and rebuilding modified files...")
    if modified_files:
        from parsers.ast_parser import parse_file
        from graph.builder import build_file_nodes

        parsed = [parse_file(f) for f in modified_files]
        parsed = [p for p in parsed if p is not None]

        if parsed:
            build_file_nodes(parsed)

            # Embed the new/modified nodes
            from embeddings.chroma_client import embed_nodes_for_files
            changed_file_paths = [p["file"] for p in parsed]
            embed_nodes_for_files(changed_file_paths)

            # Enrich new/modified functions with AI test specs
            print("\n[5/6] Enriching modified functions with AI test specs...")
            from extractors.testing_enricher import enrich_functions_for_files
            enrich_functions_for_files(changed_file_paths)
        else:
            print("  No parseable files found among modifications.")

    # Update git history for new commits
    from parsers.git_parser import parse_git_history
    from graph.builder import build_git_nodes
    new_commits = parse_git_history(CODEBASE_PATH, max_commits=50)
    if new_commits:
        build_git_nodes(new_commits)

    # Re-run community detection
    print("\n[6/6] Updating community clusters...")
    from community.detector import detect_communities
    from community.summarizer import summarize_all_communities
    detect_communities()
    summarize_all_communities()

    # 6b. Link new commits to functions
    if new_commits and modified_files:
        from graph.builder import link_commits_to_functions
        # Build parsed info for linking
        link_parsed = [p for p in [parse_file(f) for f in modified_files] if p] if modified_files else []
        if link_parsed:
            link_commits_to_functions(new_commits[:10], link_parsed, CODEBASE_PATH)

    # Update sync state
    head = _get_head_commit(CODEBASE_PATH)
    _save_sync_state({
        "last_synced_commit": head,
        "last_sync_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "codebase_path": CODEBASE_PATH,
        "mode": "incremental_sync",
        "files_modified": len(modified_files),
        "files_deleted": len(deleted_files),
    })

    print("\n" + "=" * 60)
    print("✅ Incremental sync complete!")
    print("=" * 60)
    print(f"   Modified: {len(modified_files)} | Deleted: {len(deleted_files)}")


# ═══════════════════════════════════════════════════════════
# CLI Entrypoint
# ═══════════════════════════════════════════════════════════

def main():
    # Automatically handle setup and wrappers for parent project
    _auto_update_parent_gitignore()
    _auto_generate_parent_launchers()

    parser = argparse.ArgumentParser(
        description="GraphRAG Knowledge Base — Initialize or sync the code knowledge graph."
    )
    parser.add_argument(
        "--force-init", action="store_true",
        help="Force full re-initialization, discarding existing sync state."
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Print current graph statistics and exit."
    )
    args = parser.parse_args()

    if args.status:
        run_status()
        return

    sync_state = _load_sync_state()

    if args.force_init or sync_state is None:
        if sync_state and args.force_init:
            print("[Init] Force re-initialization requested. Clearing existing graph...")
            _ensure_data_dirs()
            _start_docker()
            from graph.neo4j_client import get_client
            get_client().clear_all()
        run_full_init()
    else:
        run_incremental_sync()


def run_status():
    """Print current graph statistics without running any sync."""
    sync_state = _load_sync_state()
    print("=" * 60)
    print("GraphRAG — Status")
    print("=" * 60)
    print(f"Target codebase : {CODEBASE_PATH}")
    print(f"Data directory  : {GRAPHRAG_DATA_DIR}")

    if sync_state:
        print(f"Last sync time  : {sync_state.get('last_sync_time', 'unknown')}")
        print(f"Last commit     : {(sync_state.get('last_synced_commit') or 'N/A')[:12]}")
        print(f"Sync mode       : {sync_state.get('mode', 'unknown')}")
    else:
        print("Sync state      : Not initialized yet")
        return

    try:
        _start_docker()
        from graph.neo4j_client import get_client
        client = get_client()

        stats = client.run("""
            MATCH (f:Function) WITH count(f) as total_functions
            MATCH (f2:Function) WHERE f2.how_it_works IS NOT NULL
            WITH total_functions, count(f2) as enriched_functions
            OPTIONAL MATCH (m:Module) WITH total_functions, enriched_functions, count(m) as total_modules
            OPTIONAL MATCH (c:Commit) WITH total_functions, enriched_functions, total_modules, count(c) as total_commits
            RETURN total_functions, enriched_functions, total_modules, total_commits
        """)[0]

        total = stats["total_functions"]
        enriched = stats["enriched_functions"]
        coverage = f"{enriched / max(total, 1) * 100:.1f}%"

        print(f"\n--- Graph Statistics ---")
        print(f"Functions       : {total}")
        print(f"Enriched        : {enriched} ({coverage})")
        print(f"Modules         : {stats['total_modules']}")
        print(f"Commits indexed : {stats['total_commits']}")
    except Exception as e:
        print(f"\nCould not connect to Neo4j: {e}")
        print("Make sure Docker is running.")


if __name__ == "__main__":
    main()
