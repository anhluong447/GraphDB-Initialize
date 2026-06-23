"""
Git Hook Setup

This module provides a function to install a post-commit hook
that auto-updates the GraphRAG graph after each git commit.
"""

import os
import sys
import stat

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CODEBASE_PATH


HOOK_SCRIPT = """#!/bin/bash
# GraphRAG post-commit hook
# Auto-update graph after each commit

GRAPHRAG_PATH="{graphrag_path}"
cd "$GRAPHRAG_PATH" && python -c "
import git
import os
from config import CODEBASE_PATH
from updater.git_hook import update_changed_files
from parsers.git_parser import parse_git_history
from graph.builder import build_git_nodes

repo = git.Repo(CODEBASE_PATH)
latest_commit = repo.head.commit
changed_files = [os.path.join(CODEBASE_PATH, f).replace(os.sep, '/') for f in latest_commit.stats.files.keys()]

# Update positions and nodes for changed files
update_changed_files(changed_files)

# Update git nodes
commits = parse_git_history(max_commits=1)
if commits:
    build_git_nodes(commits)
    print('GraphRAG: Git graph updated.')

# Close Neo4j client connection
from graph.neo4j_client import get_client
get_client().close()
" &
"""

HOOK_PRE_PUSH_SCRIPT = """#!/bin/bash
# nelgraph pre-push hook
# Sync graph trước khi push để đảm bảo graph up-to-date
NELGRAPH_PATH="{nelgraph_path}"
cd "$NELGRAPH_PATH" && python -c "
from core.sync_pipeline import run_incremental_sync
run_incremental_sync()
from graph.neo4j_client import get_client
get_client().close()
"
"""


def update_changed_files(changed_files: list[str]):
    """Re-parse and update coordinates/embeddings for changed files."""
    from parsers.ast_parser import parse_file
    from graph.builder import build_file_nodes
    from graph.neo4j_client import get_client
    from embeddings.chroma_client import collection, embed_nodes_for_files
    from extractors.testing_enricher import enrich_functions_for_files
    
    client = get_client()
    has_changes = False
    for f in changed_files:
        f = f.replace("\\", "/")
        if not os.path.exists(f):
            # Clean up deleted files
            print(f"[GitHook] Cleaning up deleted file: {f}")
            client.run("MATCH (n) WHERE n.file = $file AND (n:Function OR n:Class) DETACH DELETE n", {"file": f})
            client.run("MATCH (f:File {path: $path}) DETACH DELETE f", {"path": f})
            try:
                collection.delete(where={"file": f})
            except Exception:
                pass
            has_changes = True
            continue

        print(f"[GitHook] Updating changed file: {f}")
        parsed = parse_file(f)
        if parsed:
            # Delete old AST nodes belonging to this file first
            client.run("MATCH (n) WHERE n.file = $file AND (n:Function OR n:Class) DETACH DELETE n", {"file": f})
            build_file_nodes([parsed])
            
            # Re-embed
            try:
                collection.delete(where={"file": f})
            except Exception:
                pass
            embed_nodes_for_files([f])
            
            # Enrich
            enrich_functions_for_files([f])
            has_changes = True

    if has_changes:
        print("[GitHook] Triggering community detection and summarization...")
        from community.detector import detect_communities
        from community.summarizer import summarize_all_communities
        detect_communities()
        summarize_all_communities()


def install_post_commit_hook() -> bool:
    """Install post-commit hook in the target codebase."""
    hooks_dir = os.path.join(CODEBASE_PATH, ".git", "hooks")
    if not os.path.exists(hooks_dir):
        print(f"[GitHook] No .git/hooks directory found at {hooks_dir}")
        return False

    hook_path = os.path.join(hooks_dir, "post-commit")
    graphrag_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    with open(hook_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(HOOK_SCRIPT.format(graphrag_path=graphrag_path))

    # Make executable
    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC)

    print(f"[GitHook] Post-commit hook installed at {hook_path}")
    return True


def install_pre_push_hook() -> bool:
    """Install pre-push hook in the target codebase."""
    hooks_dir = os.path.join(CODEBASE_PATH, ".git", "hooks")
    if not os.path.exists(hooks_dir):
        print(f"[GitHook] No .git/hooks directory found at {hooks_dir}")
        return False

    hook_path = os.path.join(hooks_dir, "pre-push")
    graphrag_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    with open(hook_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(HOOK_PRE_PUSH_SCRIPT.format(nelgraph_path=graphrag_path))

    # Make executable
    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC)

    print(f"[GitHook] Pre-push hook installed at {hook_path}")
    return True


def install_hook() -> bool:
    """Install both post-commit and pre-push hooks."""
    ok_post = install_post_commit_hook()
    ok_push = install_pre_push_hook()
    return ok_post and ok_push


if __name__ == "__main__":
    install_hook()
