import os
import time
from config import CODEBASE_PATH, IGNORE_DIRS
from core.init_pipeline import (
    _start_docker, _load_sync_state, _save_sync_state,
    _get_head_commit, _is_supported_file
)


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


def run_incremental_sync():
    """Run incremental sync based on git diff since last sync."""
    sync_state = _load_sync_state()
    if not sync_state:
        print("Error: No sync state found. Run full initialization first.")
        return
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
        from parsers.ast_parser import parse_file
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

    # Close Neo4j client connection
    try:
        from graph.neo4j_client import get_client
        get_client().close()
    except Exception:
        pass
