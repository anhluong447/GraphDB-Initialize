"""
GraphRAG Knowledge Base Initializer & Incremental Sync Engine — CLI Entrypoint

Usage:
    python initialize_graph.py              # Auto-detect: full init or incremental sync
    python initialize_graph.py --force-init # Force full re-initialization
    python initialize_graph.py --status     # Show current graph statistics
"""

import sys
import os
import argparse

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CODEBASE_PATH, GRAPHRAG_DATA_DIR

# --- Backwards compatibility imports & exports ---
from core.init_pipeline import (
    run_full_init,
    _start_docker,
    _load_sync_state,
    _auto_update_parent_gitignore,
    _auto_generate_parent_launchers,
)
from core.sync_pipeline import run_incremental_sync

__all__ = [
    "run_full_init",
    "run_incremental_sync",
    "_start_docker",
    "_load_sync_state",
]


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

        stats_list = client.run("""
            OPTIONAL MATCH (f:Function)
            WITH count(f) as total_functions
            OPTIONAL MATCH (f2:Function) WHERE f2.how_it_works IS NOT NULL
            WITH total_functions, count(f2) as enriched_functions
            OPTIONAL MATCH (m:Module)
            WITH total_functions, enriched_functions, count(m) as total_modules
            OPTIONAL MATCH (c:Commit)
            RETURN total_functions, enriched_functions, total_modules, count(c) as total_commits
        """)
        stats = stats_list[0] if stats_list else {
            "total_functions": 0,
            "enriched_functions": 0,
            "total_modules": 0,
            "total_commits": 0
        }

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
            _start_docker()
            from graph.neo4j_client import get_client
            get_client().clear_all()
        run_full_init()
    else:
        run_incremental_sync()


if __name__ == "__main__":
    main()
