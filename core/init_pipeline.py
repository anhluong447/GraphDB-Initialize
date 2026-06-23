import os
import sys
import json
import time
import subprocess
from config import (
    CODEBASE_PATH, SUPPORTED_LANGUAGES, GRAPHRAG_DATA_DIR,
    NEO4J_DATA_DIR, NEO4J_LOGS_DIR, SYNC_STATE_PATH,
)

GRAPHRAG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_docker_started = False


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
    global _docker_started
    if _docker_started:
        return
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
    _docker_started = True


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





def step_start_databases():
    """Step 1: Start Docker databases and wait for Neo4j."""
    _ensure_data_dirs()
    _start_docker()


def step_create_indexes():
    """Step 2: Create Neo4j indexes."""
    from graph.neo4j_client import get_client
    client = get_client()
    client.create_indexes()
    return client


def step_parse_codebase(codebase_path: str) -> dict:
    """Step 3: Parse codebase AST, docs, and git history. Returns parsed data."""
    from parsers.ast_parser import parse_codebase
    from parsers.doc_parser import parse_docs
    from parsers.git_parser import parse_git_history

    parsed_files = parse_codebase(codebase_path)
    docs = parse_docs(codebase_path)
    commits = parse_git_history(codebase_path, max_commits=200)

    return {"parsed_files": parsed_files, "docs": docs, "commits": commits}


def step_build_graph(parsed_files: list, commits: list):
    """Step 4: Build structural graph nodes (File, Function, Class, Commit, Person)."""
    from graph.builder import build_file_nodes, build_git_nodes
    build_file_nodes(parsed_files)
    build_git_nodes(commits)


def step_link_commits(commits: list, parsed_files: list, codebase_path: str):
    """Step 5: Link commits to the specific functions they changed."""
    from graph.builder import link_commits_to_functions
    link_commits_to_functions(commits, parsed_files, codebase_path)


def step_extract_semantics(parsed_files: list, docs: list):
    """Step 6: LLM semantic extraction (Concepts, Features, Risks, etc.)."""
    from graph.neo4j_client import get_client
    from graph.builder import build_semantic_nodes
    from extractors.llm_extractor import batch_extract

    # Check if we already have semantic nodes (concepts/features) in Neo4j
    client = get_client()
    labels = ["Concept", "Feature", "Decision", "Risk", "Task"]
    existing_count = 0
    try:
        for label in labels:
            res = client.run(f"MATCH (n:{label}) RETURN count(n) as cnt")
            if res:
                existing_count += res[0]["cnt"]
    except Exception as e:
        print(f"[Pipeline] Warning checking existing semantic nodes: {e}")

    if existing_count > 10:
        print(f"[Pipeline] Found {existing_count} existing semantic nodes. Skipping LLM semantic extraction (Resume Mode).")
        return

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


def step_embed_nodes():
    """Step 7: Embed all nodes to ChromaDB vector store."""
    from embeddings.chroma_client import embed_all_nodes
    embed_all_nodes()


def step_enrich_functions():
    """Step 8: AI Testing Enrichment — generate test specs for functions."""
    from extractors.testing_enricher import enrich_all_functions
    enrich_all_functions()


def step_detect_communities():
    """Step 9: Community detection and summarization."""
    from community.detector import detect_communities
    from community.summarizer import summarize_all_communities
    detect_communities()
    summarize_all_communities()


def run_full_init():
    """Run the complete initialization pipeline from scratch."""
    print("=" * 60)
    print("GraphRAG — Full Initialization")
    print("=" * 60)
    print(f"Target codebase : {CODEBASE_PATH}")
    print(f"Data directory  : {GRAPHRAG_DATA_DIR}")

    print("\n[1/9] Starting databases...")
    step_start_databases()

    print("\n[2/9] Initializing graph schema...")
    step_create_indexes()

    print("\n[3/9] Parsing codebase...")
    parsed_data = step_parse_codebase(CODEBASE_PATH)
    parsed_files = parsed_data["parsed_files"]
    docs = parsed_data["docs"]
    commits = parsed_data["commits"]

    print("\n[4/9] Building structural graph...")
    step_build_graph(parsed_files, commits)

    print("\n[5/9] Linking commits to changed functions...")
    step_link_commits(commits, parsed_files, CODEBASE_PATH)

    print("\n[6/9] Extracting semantic entities (LLM)...")
    step_extract_semantics(parsed_files, docs)

    print("\n[7/9] Embedding nodes...")
    step_embed_nodes()

    print("\n[8/9] Enriching functions with AI test specs...")
    step_enrich_functions()

    print("\n[9/9] Detecting communities...")
    step_detect_communities()

    # Save sync state
    head = _get_head_commit(CODEBASE_PATH)
    _save_sync_state({
        "last_synced_commit": head,
        "last_sync_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "codebase_path": CODEBASE_PATH,
        "mode": "full_init",
    })

    _generate_agent_query_guide()
    _copy_agent_skills()

    # Automatically install git post-commit hook
    from updater.git_hook import install_hook
    hook_installed = install_hook()

    # Close Neo4j client connection
    try:
        from graph.neo4j_client import get_client
        get_client().close()
    except Exception:
        pass

    print("\n" + "=" * 60)
    print("✅ Full initialization complete!")
    print("=" * 60)
    print(f"   Data stored at: {GRAPHRAG_DATA_DIR}")
    print(f"   Neo4j Browser:  http://localhost:7474")
    if not hook_installed:
        print("\n[GitHook] ⚠ Warning: Target directory is not a Git repository. The graph will not be auto-updated on commit.")


def _generate_agent_query_guide():
    agent_dir = os.path.join(CODEBASE_PATH, ".agent", "nelgraph")
    os.makedirs(agent_dir, exist_ok=True)
    guide_path = os.path.join(agent_dir, "SKILL.md")
    
    guide_content = """# nelgraph — Agent Interface

## ---
name: nelgraph
description: Query a codebase knowledge graph to understand code structure, function logic, dependencies, and test recommendations. Use when you need to analyze, test, or modify an existing codebase.
---

# nelgraph — Agent Interface

You have access to a codebase knowledge graph via `nelgraph`.
Always query the graph before writing any code, tests, or analysis.
Neo4j and ChromaDB are already running if the user ran `nelgraph init`.

## When to use this skill

- Use this when the task involves reading, analyzing, or testing existing code
- Use this before writing any new code that touches existing functions
- Use this when you need to understand how functions relate to each other
- Use this when working from a commit or PR and need to know what changed

## How to use it

### Step 0: Sync before starting

Always run this at the start of a session to avoid stale data:

```python
import subprocess
subprocess.run(["nelgraph", "sync"], check=True)
```

### Step 1: Get your bearings

If you're starting fresh and don't know the codebase:

```python
import nelgraph

snap = nelgraph.get_snapshot()
# → {"total": int, "communities": [{"id", "summary", "functions": [...]}]}
# functions inside each community are sorted by priority_score
# (complexity + call frequency + change count)
```

If you're working from a specific commit:

```python
changes = nelgraph.get_changes("a3f9c12")
# → {"risk_level": "high"|"medium"|"low", "changed_functions": [...]}
```

### Step 2: Find the functions you need

If you don't know the function name, search by intent:

```python
results = nelgraph.search("how does user authentication work", top_k=10)
# → [{"name": str, "file": str, "score": float, "description": str}, ...]
```

If you know the name, go straight to full context:

```python
ctx = nelgraph.get_function_context("login")
# → {
#     "name", "file", "raw_code",
#     "how_it_works",           # plain-English summary
#     "inputs",                 # parameters + types
#     "edge_cases",             # list of boundary scenarios
#     "test_recommendations",   # what to mock, what test cases to write
#     "callers",                # functions that call this one
#     "callees"                 # functions this one calls
#   }
```

> **Ambiguous name?** If multiple classes have the same method name (e.g. `__init__`, `execute`),
> the graph may return the wrong one. Disambiguate with `class_name` or `file`:
> ```python
> nelgraph.get_function_context("__init__", class_name="ShimizuBot")
> nelgraph.get_function_context("execute", file="src/services/runner.py")
> ```

### Step 3: Mark progress

After writing and verifying a test, persist the result to the graph:

```python
nelgraph.mark_tested("login")  # → True
```

---

## Quick reference

| Situation                                    | Call                                         |
| -------------------------------------------- | -------------------------------------------- |
| Starting fresh, don't know the codebase      | `get_snapshot()`                             |
| User mentions a specific function            | `get_function_context(name)`                 |
| Same method name appears in multiple classes | `get_function_context(name, class_name=...)` |
| Looking for functions related to a feature   | `search(query)`                              |
| Working on a specific commit or PR           | `get_changes(commit_hash)`                   |
| After writing and verifying a test           | `mark_tested(name)`                          |

---

## Rules

1. **Always sync first.** Run `nelgraph sync` before starting any session to avoid working with stale data.
2. **Always query before writing.** Never guess at function signatures, logic, or dependencies — `get_function_context()` has the source code.
3. **Use test_recommendations as your test plan.** It already lists what to mock and which cases to cover.
4. **Prefer `get_function_context()` over `search()`** when you know the name. It's faster and returns full source code.
5. **Disambiguate when the name is common.** Pass `class_name` or `file` to avoid getting the wrong function.
6. **Mark functions after testing.** This persists to the graph so other agents and future runs know what's covered.
"""


    try:
        with open(guide_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(guide_content)
        print(f"[Init] Generated agent query guide at: {guide_path}")
    except Exception as e:
        print(f"[Init] Warning: Could not generate agent query guide: {e}")


def _copy_agent_skills():
    """Copy the 3 skill files from package skills/ directory to <CODEBASE_PATH>/.agent/nelgraph/"""
    import shutil
    dest_dir = os.path.join(CODEBASE_PATH, ".agent", "nelgraph")
    os.makedirs(dest_dir, exist_ok=True)
    
    # Source directory inside package
    package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_dir = os.path.join(package_root, "skills")
    
    # Fallback to updates/skills in the dev repo
    if not os.path.exists(src_dir) or not os.listdir(src_dir):
        src_dir = os.path.join(package_root, "updates", "skills")
        
    print(f"[Init] Copying agent skills from {src_dir} to {dest_dir}...")
    if os.path.exists(src_dir):
        copied_count = 0
        for f in os.listdir(src_dir):
            if f.endswith(".md"):
                shutil.copy2(os.path.join(src_dir, f), os.path.join(dest_dir, f))
                copied_count += 1
        print(f"[Init] Copied {copied_count} agent skill files.")
    else:
        print(f"[Init] Warning: Agent skills source directory not found: {src_dir}")

    # Cleanup redundant / old paths if they exist
    # 1. Old .agents directory
    old_agents_dir = os.path.join(CODEBASE_PATH, ".agents")
    if os.path.exists(old_agents_dir):
        try:
            shutil.rmtree(old_agents_dir)
            print(f"[Init] Cleaned up legacy directory {old_agents_dir}")
        except Exception:
            pass
            
    # 2. Old loose files in .agent/
    for f in ["nelgraph-community.md", "nelgraph-query.md", "nelgraph-sync.md"]:
        old_file = os.path.join(CODEBASE_PATH, ".agent", f)
        if os.path.exists(old_file):
            try:
                os.remove(old_file)
                print(f"[Init] Cleaned up legacy file {old_file}")
            except Exception:
                pass

