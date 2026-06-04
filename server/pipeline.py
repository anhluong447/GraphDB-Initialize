"""
Async Pipeline Runner — Runs the full initialization pipeline in a background
thread with progress reporting to ServerState.

This module wraps the step functions from initialize_graph.py and adds:
- Background execution (non-blocking)
- Progress reporting per step
- Git clone/pull support for remote repos
- ServerState integration (mode transitions, function counting)
"""

import os
import sys
import subprocess
import threading
import time

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import WORKSPACE_DIR, GRAPHRAG_DATA_DIR
from server.state import get_state, MODE_FIRST_RUN


def _resolve_codebase(repo_url: str, language: str = "") -> str:
    """
    Resolve repo_url to a local directory path.
    - If it's a local path that exists → use directly
    - If it's a remote Git URL → clone into workspace/
    Returns the absolute local path.
    """
    # Check if it's a local path
    if os.path.isdir(repo_url):
        resolved = os.path.abspath(repo_url).replace("\\", "/")
        print(f"[Pipeline] Using local codebase: {resolved}")
        return resolved

    # Treat as remote Git URL — clone into workspace/
    # Extract project name from URL
    project_name = repo_url.rstrip("/").split("/")[-1]
    if project_name.endswith(".git"):
        project_name = project_name[:-4]

    clone_dir = os.path.join(WORKSPACE_DIR, project_name).replace("\\", "/")
    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    if os.path.isdir(clone_dir) and os.path.isdir(os.path.join(clone_dir, ".git")):
        # Already cloned — pull latest
        print(f"[Pipeline] Pulling latest for {project_name}...")
        subprocess.run(["git", "pull"], cwd=clone_dir, check=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Fresh clone
        print(f"[Pipeline] Cloning {repo_url} into {clone_dir}...")
        subprocess.run(["git", "clone", repo_url, clone_dir], check=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return clone_dir


def _count_functions() -> int:
    """Count total Function nodes in Neo4j."""
    try:
        from graph.neo4j_client import get_client
        client = get_client()
        result = client.run("MATCH (f:Function) RETURN count(f) as cnt")
        return result[0]["cnt"] if result else 0
    except Exception:
        return 0


def _run_pipeline_worker(repo_url: str, language: str, job_id: str):
    """
    Background worker that runs the full 9-step pipeline.
    Updates ServerState.current_job at each step.
    """
    state = get_state()

    try:
        # Import step functions from initialize_graph
        from initialize_graph import (
            step_start_databases,
            step_create_indexes,
            step_parse_codebase,
            step_build_graph,
            step_link_commits,
            step_extract_semantics,
            step_embed_nodes,
            step_enrich_functions,
            step_detect_communities,
            _get_head_commit,
            _save_sync_state,
        )

        # Step 0: Resolve codebase path
        state.update_job(0, "Resolving codebase path...")
        codebase_path = _resolve_codebase(repo_url, language)

        # Dynamically update CODEBASE_PATH in config for this pipeline run
        import config
        config.CODEBASE_PATH = codebase_path

        # Step 1: Start databases
        state.update_job(1, "Starting databases...")
        step_start_databases()

        # Step 2: Create indexes
        state.update_job(2, "Initializing graph schema...")
        step_create_indexes()

        # Step 3: Parse codebase
        state.update_job(3, "Parsing codebase (AST, docs, git)...")
        parsed_data = step_parse_codebase(codebase_path)
        parsed_files = parsed_data["parsed_files"]
        docs = parsed_data["docs"]
        commits = parsed_data["commits"]

        # Step 4: Build structural graph
        state.update_job(4, "Building structural graph...")
        step_build_graph(parsed_files, commits)

        # Step 5: Link commits to functions
        state.update_job(5, "Linking commits to changed functions...")
        step_link_commits(commits, parsed_files, codebase_path)

        # Step 6: LLM semantic extraction
        state.update_job(6, "Extracting semantic entities (LLM)...")
        step_extract_semantics(parsed_files, docs)

        # Step 7: Embed nodes
        state.update_job(7, "Embedding nodes to vector store...")
        step_embed_nodes()

        # Step 8: AI Testing Enrichment
        state.update_job(8, "Enriching functions with AI test specs...")
        step_enrich_functions()

        # Step 9: Community detection
        state.update_job(9, "Detecting communities...")
        step_detect_communities()

        # Pipeline complete — count functions and transition to FIRST_RUN
        total_functions = _count_functions()
        state.complete_job(success=True, message=f"Pipeline complete. {total_functions} functions indexed.")
        state.set_first_run(total_functions=total_functions, codebase_path=codebase_path)

        # Save sync state
        head = _get_head_commit(codebase_path)
        state.update_last_sync(head or "")
        _save_sync_state({
            "last_synced_commit": head,
            "last_sync_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "codebase_path": codebase_path,
            "mode": "full_init",
        })

        # Send webhook if configured
        from config import WEBHOOK_URL
        if WEBHOOK_URL:
            try:
                import requests as http_requests
                http_requests.post(WEBHOOK_URL, json={
                    "event": "pipeline_ready",
                    "job_id": job_id,
                    "total_functions": total_functions,
                    "codebase_path": codebase_path,
                }, timeout=10)
                print(f"[Pipeline] Webhook sent: pipeline_ready")
            except Exception as e:
                print(f"[Pipeline] Warning: Could not send webhook: {e}")

        print(f"\n{'=' * 60}")
        print(f"✅ Pipeline complete! {total_functions} functions indexed.")
        print(f"   Mode: FIRST_RUN")
        print(f"{'=' * 60}")

    except Exception as e:
        state.complete_job(success=False, message=str(e))
        print(f"\n[Pipeline] ❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()


def run_pipeline_async(repo_url: str, language: str = "") -> str:
    """
    Start the full initialization pipeline in a background thread.
    Returns the job_id for progress polling.
    """
    state = get_state()

    # Check if a job is already running
    if state.current_job and state.current_job.get("status") == "running":
        raise RuntimeError("A pipeline job is already running. Wait for it to finish.")

    job_id = state.create_job(total_steps=9)

    thread = threading.Thread(
        target=_run_pipeline_worker,
        args=(repo_url, language, job_id),
        daemon=True,
        name=f"pipeline-{job_id}",
    )
    thread.start()

    return job_id


def run_git_sync(codebase_path: str):
    """
    Run incremental sync after a git push.
    Called by the /api/git-sync webhook endpoint.
    Runs in the current thread (called from a background task).
    """
    state = get_state()

    try:
        # Pull latest changes
        if os.path.isdir(os.path.join(codebase_path, ".git")):
            print(f"[Sync] Pulling latest changes in {codebase_path}...")
            subprocess.run(["git", "pull"], cwd=codebase_path, check=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Run incremental sync using initialize_graph logic
        from initialize_graph import (
            _load_sync_state, _get_changed_files, _is_supported_file,
            _get_head_commit, _save_sync_state,
        )

        import config
        config.CODEBASE_PATH = codebase_path

        sync_state = _load_sync_state()
        if not sync_state or not sync_state.get("last_synced_commit"):
            print("[Sync] No previous sync state found. Use /api/repo/init for full initialization.")
            return

        last_commit = sync_state["last_synced_commit"]
        changes = _get_changed_files(codebase_path, last_commit)

        modified_files = changes["modified"]
        deleted_files = changes["deleted"]

        if not modified_files and not deleted_files:
            print("[Sync] No changes detected. Graph is up to date.")
            return

        print(f"[Sync] Modified: {len(modified_files)}, Deleted: {len(deleted_files)}")

        from graph.neo4j_client import get_client
        client = get_client()

        # Clean up deleted/modified nodes
        all_affected = deleted_files + modified_files
        for fp in all_affected:
            client.run("""
                MATCH (n) WHERE n.file = $file AND (n:Function OR n:Class)
                DETACH DELETE n
            """, {"file": fp})
            if fp in deleted_files:
                client.run("MATCH (f:File {path: $path}) DETACH DELETE f", {"path": fp})

        # Clean ChromaDB embeddings
        from embeddings.chroma_client import collection
        for fp in all_affected:
            try:
                collection.delete(where={"file": fp})
            except Exception:
                pass

        # Re-parse modified files
        changed_functions = []
        if modified_files:
            from parsers.ast_parser import parse_file
            from graph.builder import build_file_nodes

            parsed = [parse_file(f) for f in modified_files]
            parsed = [p for p in parsed if p is not None]

            if parsed:
                build_file_nodes(parsed)

                # Collect changed function names for webhook
                for p in parsed:
                    for node in p.get("nodes", []):
                        if node.get("type", "").endswith("definition"):
                            changed_functions.append(node["name"])

                # Embed
                from embeddings.chroma_client import embed_nodes_for_files
                changed_paths = [p["file"] for p in parsed]
                embed_nodes_for_files(changed_paths)

                # Enrich
                from extractors.testing_enricher import enrich_functions_for_files
                enrich_functions_for_files(changed_paths)

        # Update git history
        from parsers.git_parser import parse_git_history
        from graph.builder import build_git_nodes
        new_commits = parse_git_history(codebase_path, max_commits=50)
        if new_commits:
            build_git_nodes(new_commits)

        # Community detection
        from community.detector import detect_communities
        from community.summarizer import summarize_all_communities
        detect_communities()
        summarize_all_communities()

        # Update sync state
        head = _get_head_commit(codebase_path)
        _save_sync_state({
            "last_synced_commit": head,
            "last_sync_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "codebase_path": codebase_path,
            "mode": "incremental_sync",
            "files_modified": len(modified_files),
            "files_deleted": len(deleted_files),
        })
        state.update_last_sync(head or "")

        # Determine risk level based on changed function complexity
        risk_level = "low"
        if changed_functions:
            try:
                complexities = client.run("""
                    MATCH (f:Function) WHERE f.name IN $names
                    RETURN max(f.complexity) as max_complexity
                """, {"names": changed_functions})
                max_c = complexities[0]["max_complexity"] if complexities else 0
                if max_c and max_c >= 10:
                    risk_level = "high"
                elif max_c and max_c >= 5:
                    risk_level = "medium"
            except Exception:
                pass

        # Enqueue or send commit webhook
        if head:
            state.enqueue_commit(
                commit_hash=head,
                changed_functions=changed_functions,
                risk_level=risk_level,
            )

        print(f"[Sync] ✅ Incremental sync complete. {len(modified_files)} modified, {len(deleted_files)} deleted.")

    except Exception as e:
        print(f"[Sync] ❌ Sync failed: {e}")
        import traceback
        traceback.print_exc()
