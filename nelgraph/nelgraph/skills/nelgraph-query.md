---
name: nelgraph-query
description: >
  Query a codebase knowledge graph to understand code structure, function logic,
  dependencies, class hierarchies, and test recommendations. Use this skill whenever
  the task involves reading, analyzing, modifying, or testing existing code that has
  been indexed with nelgraph.
---

# nelgraph — Query Skill

You have access to a live codebase knowledge graph via `nelgraph`.
Neo4j and ChromaDB are running if the user previously ran `nelgraph init`.

## Rule: Always sync before starting a session

```python
import nelgraph
nelgraph.run_sync()   # incremental sync, safe to run anytime
```

If the codebase has not been initialized yet:

```python
nelgraph.configure(
    codebase_path="/absolute/path/to/project",
    openrouter_api_key="sk-or-..."
)
nelgraph.run_init()
```

---

## Core API

### `nelgraph.search(query, top_k=10)`
Semantic search across the codebase. Use when you don't know the exact function name.

```python
results = nelgraph.search("user authentication and session handling", top_k=10)
# Returns: [{"name": str, "file": str, "score": float, "description": str}, ...]
```

### `nelgraph.get_function_context(name, class_name=None, file=None)`
Full context for a single function: source code, dependencies, callers, test specs.

```python
ctx = nelgraph.get_function_context("login")
ctx = nelgraph.get_function_context("execute", class_name="OrderProcessor")
ctx = nelgraph.get_function_context("validate", file="src/auth/validator.py")

# Returns:
# {
#   "name": str,
#   "file": str,
#   "raw_code": str,           ← actual source code
#   "how_it_works": str,       ← plain-English summary
#   "inputs": list[dict],      ← [{name, type, default}]
#   "output": str,             ← return type
#   "edge_cases": list[str],   ← boundary scenarios
#   "test_recommendations": list[str],
#   "callers": list[str],      ← functions that call this one
#   "callees": list[str],      ← functions this one calls
#   "complexity": int,         ← cyclomatic complexity
#   "is_async": bool,
#   "raises": list[str],
# }
```

**Disambiguate common names** (`__init__`, `execute`, `run`, `handle`) using
`class_name` or `file`. Do not guess — if a name is common, always pass one of these.

### `nelgraph.get_class_context(class_name)`
Full class: methods, source code, parent/child classes.

```python
ctx = nelgraph.get_class_context("UserService")
# Returns:
# {
#   "class": {...},              ← class node properties
#   "methods": [{"name", "start_line", "complexity", "docstring"}, ...],
#   "parent_classes": [{"name", "file"}, ...],
#   "child_classes":  [{"name", "file"}, ...],
# }
```

### `nelgraph.get_snapshot(exclude_tests=True)`
Overview of the entire codebase grouped by community cluster, sorted by priority.

```python
snap = nelgraph.get_snapshot()
# Returns:
# {
#   "total": int,
#   "communities": [
#     {
#       "id": int,
#       "name": str,
#       "summary": str,
#       "functions": [{"name", "file", "priority_score", "complexity"}, ...]
#     }
#   ]
# }
```

Use this when you need an overview before deciding where to start.

### `nelgraph.get_changes(commit_hash)`
Functions changed in a specific commit.

```python
changes = nelgraph.get_changes("a3f9c12")
# Returns:
# {
#   "risk_level": "high" | "medium" | "low",
#   "changed_functions": [{"name", "file", "complexity"}, ...]
# }
```

### `nelgraph.mark_tested(function_name)`
Mark a function as tested. Persists to Neo4j.

```python
nelgraph.mark_tested("login")   # → True
```

---

## Recommended Workflow

### Starting fresh (no specific entry point)
```python
snap = nelgraph.get_snapshot()
# Pick highest priority_score community
# Then get_function_context() for key functions
```

### Working from a commit or PR
```python
changes = nelgraph.get_changes("abc123f")
for fn in changes["changed_functions"]:
    ctx = nelgraph.get_function_context(fn["name"], file=fn["file"])
    # analyze ctx["callers"] to understand blast radius
```

### Exploring an unknown codebase
```python
results = nelgraph.search("describe the feature you're looking for")
# Then drill into promising results with get_function_context()
```

### Understanding a class hierarchy
```python
ctx = nelgraph.get_class_context("BaseController")
for child in ctx["child_classes"]:
    child_ctx = nelgraph.get_class_context(child["name"])
```

---

## Quick Reference

| Situation                     | Call                                         |
| ----------------------------- | -------------------------------------------- |
| Don't know function name      | `search(query)`                              |
| Know the name                 | `get_function_context(name)`                 |
| Same name in multiple classes | `get_function_context(name, class_name=...)` |
| Need class hierarchy          | `get_class_context(name)`                    |
| Need codebase overview        | `get_snapshot()`                             |
| Working on a commit/PR        | `get_changes(commit_hash)`                   |
| After writing a test          | `mark_tested(name)`                          |

---

## Rules

1. **Sync first.** Always call `run_sync()` at session start.
2. **Never guess signatures.** `get_function_context()` has the source — use it.
3. **Disambiguate common names.** Pass `class_name` or `file` for `__init__`, `run`, `handle`, `execute`.
4. **Check callers before changing anything.** `ctx["callers"]` shows blast radius.
5. **Use `test_recommendations` as your test plan** — it already lists what to mock.
6. **Mark functions after testing** so other agents and future runs know coverage state.