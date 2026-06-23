---
name: nelgraph-dev
description: >
  Internal development skill for contributing to the nelgraph package itself
  (repo: GraphDB-Initialize). Use when implementing new features, fixing bugs,
  or executing tasks from the refactor plan. Covers repo structure, module
  responsibilities, data contracts between modules, and critical invariants
  that must not be broken.
---

# nelgraph — Internal Dev Skill

## Repo Layout

```
GraphDB-Initialize/
├── __init__.py                  ← Public API (configure, get_function_context, ...)
├── initialize_graph.py          ← CLI entrypoint (nelgraph command)
├── knowledge_base.py            ← Implementation of public API functions
├── config.py                    ← All config vars, loaded from .env / os.environ
│
├── core/
│   ├── init_pipeline.py         ← run_full_init(): full graph build from scratch
│   └── sync_pipeline.py         ← run_incremental_sync(): git diff → update
│
├── parsers/
│   ├── base_parser.py           ← Tree-sitter AST parser (Python/JS/TS)
│   ├── php_parser.py            ← PHP-specific Tree-sitter parser
│   ├── ast_parser.py            ← Thin wrapper, delegates to base/php
│   ├── git_parser.py            ← Parse git log → Commit dicts
│   └── doc_parser.py            ← Parse markdown docs
│
├── graph/
│   ├── neo4j_client.py          ← Neo4jClient singleton, run(), read_node_code()
│   ├── builder.py               ← build_file_nodes(), build_git_nodes(), link_*()
│   └── schema.py                ← Node labels and relationship type constants
│
├── embeddings/
│   ├── embedder.py              ← embed_texts() via OpenRouter
│   └── chroma_client.py         ← ChromaDB collection, embed_nodes_for_files()
│
├── extractors/
│   ├── testing_enricher.py      ← LLM enrichment: how_it_works, test_recommendations
│   └── llm_extractor.py         ← LLM extraction: Concepts, Features, Risks, Tasks
│
├── community/
│   ├── detector.py              ← Leiden clustering → saves community_id to Neo4j
│   └── summarizer.py            ← LLM summarize each community → :Community node
│
├── updater/
│   ├── git_hook.py              ← Hook scripts + update_changed_files()
│   └── watcher.py               ← [DEPRECATED — delete this file]
│
├── query/
│   └── engine.py                ← GraphRAG query engine (hybrid Neo4j + ChromaDB)
│
└── visualization/
    └── backend/api.py           ← FastAPI visualization endpoint
```

---

## Module Responsibilities — What Each Module Owns

| Module                    | Owns                                               | Does NOT own           |
| ------------------------- | -------------------------------------------------- | ---------------------- |
| `config.py`               | All env vars and derived paths                     | Anything else          |
| `parsers/*`               | Raw AST extraction → list of node dicts            | Neo4j, ChromaDB        |
| `graph/builder.py`        | Writing nodes/edges to Neo4j                       | Parsing, embedding     |
| `graph/neo4j_client.py`   | Neo4j connection, Cypher execution                 | Business logic         |
| `embeddings/*`            | ChromaDB writes, vector embedding                  | Neo4j                  |
| `extractors/*`            | LLM calls for enrichment                           | Parsing, Neo4j writes  |
| `community/detector.py`   | Leiden clustering, community_id on nodes           | Summaries, ChromaDB    |
| `community/summarizer.py` | LLM summaries, :Community nodes, snapshot diff     | Clustering             |
| `updater/git_hook.py`     | Hook install, hook scripts, update_changed_files() | Parsing internals      |
| `core/sync_pipeline.py`   | Orchestration of incremental sync                  | Implementation details |
| `core/init_pipeline.py`   | Orchestration of full init                         | Implementation details |
| `knowledge_base.py`       | Public API implementation                          | Orchestration          |
| `__init__.py`             | Public API surface, configure()                    | Implementation         |

**Rule: never import upward.** `parsers` must not import from `graph`.
`graph` must not import from `extractors`. Import direction: orchestrators
import from modules, never the reverse.

---

## Data Contracts

### Parser output (`parse_file()` → dict)
```python
{
    "file": str,           # absolute path, forward slashes
    "language": str,       # "python" | "javascript" | "typescript" | "php"
    "nodes": [
        {
            "type": str,           # "function_definition" | "class_definition" | ...
            "name": str,
            "file": str,
            "start_line": int,     # 1-indexed
            "end_line": int,
            "anchor": str,         # first line of code, for stale coord detection
            "calls": list[str],    # function names called inside
            "is_async": bool,
            "visibility": str,     # "public" | "protected" | "private"
            "class_name": str,     # parent class name or None
            "docstring": str,      # first 500 chars
            "inputs": str,         # JSON string: [{"name", "type", "default"}]
            "output": str,         # return type annotation
            "raises": str,         # JSON string: ["ExceptionType", ...]
            "complexity": int,     # cyclomatic complexity
            "annotations": str,    # JSON string: ["decorator_name", ...]
            "superclasses": str,   # JSON string: ["ParentClass", ...]
        }
    ],
    "imports": [
        {
            "module": str,
            "full_path": str,
            "alias": str,
            "names": list[str],
            "is_external": bool,
            "is_stdlib": bool,
            "source_file": str,
        }
    ],
    "raw_code": str,       # full file source
}
```

### Neo4j node properties (Function/Class)
```
name, file, start_line, end_line, anchor, raw_code (cap 5000→15000 chars),
language, class_name, is_async, visibility, docstring, inputs (JSON str),
output, raises (JSON str), complexity, annotations (JSON str),
superclasses (JSON str), is_test (bool), community_id (int),
how_it_works, edge_cases, test_recommendations (set by enricher),
tested (bool, set by mark_tested())
```

### Sync state (`sync_state.json`)
```json
{
    "last_synced_commit": "abc123...",
    "last_sync_time": "2026-06-23T10:00:00",
    "codebase_path": "/abs/path",
    "mode": "full_init" | "incremental_sync",
    "files_modified": 3,
    "files_deleted": 0
}
```

### Community snapshot (`community_snapshot.json`)
```json
{
    "generated_at": "2026-06-23T10:00:00",
    "communities": {
        "0": ["function_name::file_path", ...],
        "1": ["class_name::file_path", ...]
    }
}
```
Member key format: `"<node_name>::<file_path>"` — both fields required to
avoid collision (same function name in different files).

---

## Critical Invariants — Never Break These

**1. Delete-first before rebuild**
Whenever rebuilding nodes for a file, always delete existing Function/Class
nodes for that file BEFORE calling `build_file_nodes()`:
```python
client.run(
    "MATCH (n) WHERE n.file = $file AND (n:Function OR n:Class) DETACH DELETE n",
    {"file": file_path}
)
```
Violating this causes ghost nodes when functions are renamed.

**2. MERGE key for Function/Class nodes is `(name, file)`**
`graph/builder.py` uses `MERGE (n:Function {name: $name, file: $file})`.
If a function is renamed, the old node persists unless explicitly deleted first.
This is why delete-first is mandatory.

**3. Community diff must use frozenset, not community_id**
Leiden IDs are not stable between runs. Always compare by member set:
```python
old_sets = {frozenset(v) for v in old_snapshot["communities"].values()}
# NOT: old_ids = set(old_snapshot["communities"].keys())
```

**4. Never call summarize_all_communities() without detect_communities() first**
`summarize_all_communities()` reads `community_id` from nodes — those are only
correct after `detect_communities()` runs and writes them. Wrong order =
summaries assigned to wrong communities.

**5. Close Neo4j client after each hook/script run**
```python
from graph.neo4j_client import get_client
get_client().close()
```
Not closing causes connection leaks in the background hook processes.

**6. All file paths: absolute, forward slashes**
Use `.replace("\\", "/")` after any `os.path.join()`. Neo4j queries use
exact string match on `file` property — mixed separators cause misses.

**7. config.py vars must be propagated after configure()**
`__init__.py → configure()` iterates `sys.modules` and patches all loaded
modules when config changes. If you add a new module that reads config at
import time (e.g. `MY_VAR = config.SOMETHING`), add it to the propagation
list in `configure()`.

---

## Common Patterns

### Adding a new CLI flag
1. Add `parser.add_argument("--my-flag", ...)` in `initialize_graph.py → main()`
2. Add the handler block: `if args.my_flag: ...`
3. Add a Makefile target: `my-flag:\n\tpython initialize_graph.py --my-flag`
4. Expose via `__init__.py` if it makes sense as a Python API too

### Adding a new node property
1. Add to parser output dict in `parsers/base_parser.py` (or `php_parser.py`)
2. Add to the `SET n.property = $value` block in `graph/builder.py → build_file_nodes()`
3. Add the param to the Cypher params dict
4. Update `graph/schema.py` docstring
5. Expose in `knowledge_base.py` return dict if user-facing

### Adding a new relationship type
1. Add to `graph/schema.py → RELATION_TYPES`
2. Add Cypher `MERGE (a)-[:NEW_REL]->(b)` in `graph/builder.py`
3. Consider whether community detection should weight it differently

### Running a one-off Cypher query during dev
```python
from graph.neo4j_client import get_client
client = get_client()
rows = client.run("MATCH (f:Function) RETURN f.name, f.file LIMIT 5")
for r in rows:
    print(dict(r))
client.close()
```

---

## Active Refactor Tasks (from refactor plan)

Work through these in order. Each task references the exact files to touch.

### TASK 1 — Delete updater/watcher.py
```
DELETE: updater/watcher.py
GREP AND REMOVE:
  - "from updater.watcher" in any .py file
  - "import watcher" in any .py file
  - "watchdog" in requirements.txt / pyproject.toml
  - watcher-related entries in __init__.py __all__
  - "watch" target in Makefile
VERIFY: grep -r "watcher" . --include="*.py" returns nothing
```

### TASK 2 — Community snapshot save (detector.py)
```
FILE: community/detector.py
ADD after the Neo4j community_id save loop in detect_communities():

  _save_community_snapshot(result, client)

IMPLEMENT _save_community_snapshot(result: dict, client):
  - result is {neo4j_element_id: community_id}
  - query Neo4j for name+file of each node_id in result
  - build {str(community_id): ["name::file", ...]}
  - write to os.path.join(GRAPHRAG_DATA_DIR, "community_snapshot.json")
  - import: json, time, os, from config import GRAPHRAG_DATA_DIR
```

### TASK 3 — Community snapshot diff (summarizer.py)
```
FILE: community/summarizer.py
ADD three helpers:
  _load_community_snapshot() → dict | None
  _build_current_snapshot() → dict   (query Neo4j for current community_id membership)
  _diff_communities(old, new) → list[int]   (frozenset comparison)

MODIFY summarize_all_communities():
  1. At the TOP: client.run("MATCH (c:Community) DETACH DELETE c")
     (clean stale :Community nodes before rebuild)
  2. Load old_snapshot = _load_community_snapshot()
  3. Build new_snapshot = _build_current_snapshot()
  4. If old_snapshot is None → to_summarize = all community ids
     Else → to_summarize = set(_diff_communities(old_snapshot, new_snapshot))
  5. In the loop: if cid not in to_summarize: print skip, continue
  6. At the BOTTOM: save new_snapshot to community_snapshot.json
```

### TASK 4 — Git hook triggers community (git_hook.py)
```
FILE: updater/git_hook.py
IN update_changed_files(), after enrich_functions_for_files():

  from community.detector import detect_communities
  from community.summarizer import summarize_all_communities
  detect_communities()
  summarize_all_communities()

NOTE: This is safe only after TASK 2+3 are done. Otherwise it brute-forces
all communities on every commit.
```

### TASK 5 — Add pre-push hook (git_hook.py)
```
FILE: updater/git_hook.py
ADD constant: HOOK_PRE_PUSH_SCRIPT (bash script calling run_incremental_sync)
ADD function: install_pre_push_hook() → bool
  - writes to <CODEBASE_PATH>/.git/hooks/pre-push
  - chmod +x (same pattern as post-commit)
  - runs SYNCHRONOUSLY (no & at end) to block push until sync is done

MODIFY install_hook():
  - call both install_post_commit_hook() and install_pre_push_hook()
  - return True only if both succeed
```

### TASK 6 — CLI --install-hooks (initialize_graph.py)
```
FILE: initialize_graph.py
ADD argument: --install-hooks
HANDLER:
  from updater.git_hook import install_hook
  ok = install_hook()
  sys.exit(0 if ok else 1)

FILE: Makefile
UPDATE: hook target to call --install-hooks
```

### TASK 7 — _assert_configured guard (knowledge_base.py)
```
FILE: knowledge_base.py
ADD at top:
  def _assert_configured():
      import config
      if not config.CODEBASE_PATH or config.CODEBASE_PATH == "..":
          raise RuntimeError(
              "[nelgraph] Not configured. Call nelgraph.configure() first:\n"
              "  nelgraph.configure(codebase_path='/path/to/project', openrouter_api_key='sk-or-...')"
          )

CALL _assert_configured() at top of:
  get_function_context, get_class_context, get_snapshot, search,
  get_changes, run_init, run_sync
```

### TASK 8 — Skip Docker prompt in non-interactive mode (initialize_graph.py)
```
FILE: initialize_graph.py → main()
FIND:
  if sys.stdout.isatty():
      confirm = input("Bạn đã bật Docker chưa? ...")
REPLACE WITH:
  if sys.stdout.isatty() and not os.environ.get("NELGRAPH_NO_PROMPT"):
      confirm = input("Bạn đã bật Docker chưa? (y/n) [y]: ").strip().lower()
      if confirm not in ("", "y", "yes"):
          print("Vui lòng bật Docker trước khi chạy.")
          sys.exit(1)
```

### TASK 9 — Raise raw_code cap (builder.py)
```
FILE: graph/builder.py
FIND: raw_code[:5000]
REPLACE: raw_code[:15000]
```

### TASK 10 — Remove watchdog from dependencies
```
FILE: requirements.txt (or pyproject.toml)
REMOVE: watchdog
VERIFY: pip install -e . completes without watchdog
```

---

## Testing a Change

No formal test suite exists. Use `scratch/test_nelgraph.py` for manual testing:

```bash
cd GraphDB-Initialize
python scratch/test_nelgraph.py
```

For community-specific changes, verify manually:
```python
from community.detector import detect_communities
from community.summarizer import summarize_all_communities
result = detect_communities()
print(f"Detected {len(set(result.values()))} communities")
summarize_all_communities()
# Check: only changed communities should show "LLM:" in output
# Unchanged ones should show "unchanged, skipping LLM."
```

For hook testing:
```bash
# Install hooks
python initialize_graph.py --install-hooks

# Trigger post-commit hook manually (simulate)
cd <CODEBASE_PATH>
git commit --allow-empty -m "test hook"

# Check Neo4j was updated
python -c "
from graph.neo4j_client import get_client
r = get_client().run('MATCH (f:Function) RETURN count(f) as n')
print('Functions in graph:', r[0]['n'])
"
```