---
name: nelgraph-sync
description: >
  Set up and manage sync triggers for the nelgraph knowledge graph. Covers
  post-commit and pre-push git hooks, incremental sync logic, and troubleshooting
  stale graphs. Use this skill when installing hooks, debugging sync failures,
  or adding new sync triggers to a project.
---

# nelgraph — Sync & Git Hook Skill

## Sync Architecture Overview

nelgraph uses **two git hooks only** (no file watcher):

```
git commit  →  post-commit hook  →  update changed files + community diff
git push    →  pre-push hook     →  full incremental sync (all commits since last sync)
```

| Trigger                  | Scope                       | Community Update         |
| ------------------------ | --------------------------- | ------------------------ |
| post-commit              | Files in that commit only   | Yes (with snapshot diff) |
| pre-push                 | All commits since last sync | Yes (with snapshot diff) |
| `nelgraph sync` (manual) | Same as pre-push            | Yes                      |

---

## Installing Hooks

### Auto-install (runs on `nelgraph init`)
`core/init_pipeline.py` calls `install_hook()` automatically after full init.
No manual step needed for new projects.

### Manual install
```bash
nelgraph --install-hooks
```

Or from Python:
```python
from updater.git_hook import install_hook
install_hook()   # installs both post-commit and pre-push
```

### What gets installed

**post-commit hook** → `<CODEBASE_PATH>/.git/hooks/post-commit`
```bash
#!/bin/bash
NELGRAPH_PATH="{nelgraph_path}"
cd "$NELGRAPH_PATH" && python -c "
import git, os
from config import CODEBASE_PATH
from updater.git_hook import update_changed_files
from parsers.git_parser import parse_git_history
from graph.builder import build_git_nodes
from community.detector import detect_communities
from community.summarizer import summarize_all_communities

repo = git.Repo(CODEBASE_PATH)
latest_commit = repo.head.commit
changed_files = [os.path.join(CODEBASE_PATH, f).replace(os.sep, '/') for f in latest_commit.stats.files.keys()]

update_changed_files(changed_files)

commits = parse_git_history(max_commits=1)
if commits:
    build_git_nodes(commits)

detect_communities()
summarize_all_communities()   # snapshot diff — only LLMs changed communities

from graph.neo4j_client import get_client
get_client().close()
" &
```

**pre-push hook** → `<CODEBASE_PATH>/.git/hooks/pre-push`
```bash
#!/bin/bash
NELGRAPH_PATH="{nelgraph_path}"
cd "$NELGRAPH_PATH" && python -c "
from core.sync_pipeline import run_incremental_sync
run_incremental_sync()
from graph.neo4j_client import get_client
get_client().close()
" 
```

Note: post-commit runs with `&` (background, non-blocking). pre-push runs
synchronously (blocking push until sync is done — ensures graph is consistent
before remote receives the code).

---

## `updater/git_hook.py` — Key Functions

### `update_changed_files(changed_files: list[str])`
Core update logic. For each file:
1. If file deleted → remove Function/Class nodes + File node + ChromaDB embeddings
2. If file modified/added:
   - Delete old AST nodes for that file (delete-first pattern)
   - Re-parse → `build_file_nodes()`
   - Re-embed → `embed_nodes_for_files()`
   - Re-enrich → `enrich_functions_for_files()`

```python
from updater.git_hook import update_changed_files

changed = ["/abs/path/to/auth.py", "/abs/path/to/orders.php"]
update_changed_files(changed)
```

### `install_hook()` → `bool`
Installs post-commit + pre-push hooks. Returns `False` if target is not a git repo.

### `install_post_commit_hook()` / `install_pre_push_hook()`
Install individual hooks if you only want one.

---

## Incremental Sync Logic (`core/sync_pipeline.py`)

`run_incremental_sync()` flow:
```
[1] Load sync_state.json → get last_synced_commit
[2] Git diff last_synced_commit → HEAD (+ unstaged + staged + untracked)
[3] Delete Function/Class nodes for affected files
[4] Re-parse + rebuild modified files
[5] AI enrich modified functions
[6] detect_communities() + summarize_all_communities() (snapshot diff)
[7] Save new sync_state.json with HEAD commit
```

Sync state stored at: `<GRAPHRAG_DATA_DIR>/sync_state.json`

```json
{
  "last_synced_commit": "abc123...",
  "last_sync_time": "2026-06-23T10:00:00",
  "codebase_path": "/path/to/project",
  "mode": "incremental_sync",
  "files_modified": 3,
  "files_deleted": 0
}
```

---

## Troubleshooting

### Hook not running after commit
```bash
# Check hook is installed and executable
ls -la <CODEBASE_PATH>/.git/hooks/post-commit

# Reinstall
python -c "from updater.git_hook import install_hook; install_hook()"
```

### Graph is stale after pulling from remote
pre-push only runs before pushing — not after pulling. After `git pull`:
```bash
nelgraph --sync
# or
python -c "from core.sync_pipeline import run_incremental_sync; run_incremental_sync()"
```

### Sync fails: "No sync state found"
Graph has not been initialized. Run:
```bash
nelgraph init
# or
python initialize_graph.py
```

### post-commit hook runs but community doesn't update
The hook runs in background (`&`). Community update may still be in progress.
Wait a few seconds, or check Docker logs:
```bash
docker logs nelgraph-neo4j --tail 20
```

### pre-push hook is blocking push for too long
Large codebases with many changes can make pre-push slow. Options:
1. Run sync manually before push: `nelgraph sync`
2. Comment out pre-push hook temporarily and push, then run sync after

### Check what the last sync covered
```python
import json, os
from config import GRAPHRAG_DATA_DIR
with open(os.path.join(GRAPHRAG_DATA_DIR, "sync_state.json")) as f:
    state = json.load(f)
print(state)
```

---

## Environment Variables

| Variable             | Purpose                                          | Default                     |
| -------------------- | ------------------------------------------------ | --------------------------- |
| `NELGRAPH_NO_PROMPT` | Skip Docker confirmation prompt (for CI/scripts) | unset                       |
| `CODEBASE_PATH`      | Target codebase to analyze                       | set via configure() or .env |
| `OPENROUTER_API_KEY` | API key for LLM enrichment                       | set via configure() or .env |

Set for non-interactive environments:
```bash
export NELGRAPH_NO_PROMPT=1
nelgraph sync
```

---

## Rules

1. **post-commit runs in background** (`&`) — do not rely on it being complete immediately.
2. **pre-push runs synchronously** — it blocks the push. Keep codebase changes small per push if speed matters.
3. **Always delete-first before rebuilding** — `update_changed_files()` does this; never call `build_file_nodes()` directly without deleting old nodes first.
4. **After `git pull`, run sync manually** — hooks only fire on local actions.
5. **Do not mix watcher with hooks** — watcher has been removed; do not re-add it.
6. **Close Neo4j client after each hook run** — `get_client().close()` at end of every hook script.