---
name: nelgraph
description: >
  Query a codebase knowledge graph to understand code structure, function logic,
  dependencies, class hierarchies, and test recommendations. Use this skill
  whenever the task involves reading, analyzing, modifying, or testing existing
  code that has been indexed with nelgraph.
---

# nelgraph — Agent Interface

> **You are operating on a codebase that has been indexed with nelgraph.**
> The knowledge graph is your primary and mandatory source of truth.
> Do not read files or explore directories to understand the codebase —
> the graph already has everything: structure, logic, relationships, test plans.

---

## ⛔ FORBIDDEN — Never do these

These actions are **prohibited** when working on a nelgraph-indexed codebase.
Violating these means you are ignoring the tool you were given.

| Forbidden action                                       | Do this instead                                       |
| ------------------------------------------------------ | ----------------------------------------------------- |
| Reading `.py`, `.js`, `.php` files to understand logic | `get_function_context(name)["raw_code"]`              |
| Listing directories to understand project structure    | `get_snapshot()` — community summaries                |
| Guessing function signatures or return types           | `get_function_context(name)["inputs"]` / `["output"]` |
| Summarizing the codebase from raw files                | `get_snapshot()` → read community summaries           |
| Writing tests without checking recommendations         | `get_function_context(name)["test_recommendations"]`  |
| Changing a function without checking who calls it      | `get_function_context(name)["callers"]`               |
| Starting any task before syncing                       | `nelgraph.run_sync()` — mandatory first step          |

---

## ✅ Mandatory workflow for every session

Follow these steps **in order**, every time, no exceptions.

### Step 1 — Sync (REQUIRED, do this first)

```python
import nelgraph
nelgraph.run_sync()
```

Or via CLI:
```bash
nelgraph sync
```

If you get a "not configured" error, the project needs initialization:
```python
nelgraph.configure(
    codebase_path="/absolute/path/to/project",
    openrouter_api_key="sk-or-..."
)
nelgraph.run_init()
```

Do not proceed until sync completes successfully.

### Step 2 — Orient (REQUIRED before any task)

Always get the codebase overview before doing anything else:

```python
snap = nelgraph.get_snapshot()
# Read the community names and summaries
# Identify which community is relevant to the task
# Note the highest priority_score functions — those are the most critical
```

If the task involves a specific commit or PR, use this instead:
```python
changes = nelgraph.get_changes("commit_hash")
# → {"risk_level": "high"|"medium"|"low", "changed_functions": [...]}
```

### Step 3 — Drill down

Now that you know where to look, get function or class detail:

```python
# By name (fastest when you know it)
ctx = nelgraph.get_function_context("function_name")

# When the same name exists in multiple classes
ctx = nelgraph.get_function_context("execute", class_name="OrderProcessor")
ctx = nelgraph.get_function_context("validate", file="src/auth/validator.py")

# For a class and its full hierarchy
ctx = nelgraph.get_class_context("ClassName")

# When you don't know the name
results = nelgraph.search("what this feature does", top_k=10)
ctx = nelgraph.get_function_context(results[0]["name"], file=results[0]["file"])
```

### Step 4 — Act

With full context from the graph, write code, tests, or analysis.
Use `ctx["raw_code"]` to read actual source — never open the file directly.

### Step 5 — Mark progress (when writing tests)

```python
nelgraph.mark_tested("function_name")   # after tests pass
```

---

## API Reference

### `nelgraph.get_snapshot(exclude_tests=True)`
Codebase overview grouped by community cluster, sorted by priority.

```python
snap = nelgraph.get_snapshot()
# {
#   "total": int,
#   "communities": [
#     {
#       "id": int,
#       "name": str,       ← LLM-generated cluster name (e.g. "Auth & Session")
#       "summary": str,    ← plain-English description of what this cluster does
#       "functions": [
#         {"name", "file", "priority_score", "complexity"},
#         ...              ← sorted by priority_score descending
#       ]
#     }
#   ]
# }
```

### `nelgraph.get_function_context(name, class_name=None, file=None)`
Full context for one function. This is your primary tool for reading code.

```python
ctx = nelgraph.get_function_context("login")
# {
#   "name": str,
#   "file": str,
#   "raw_code": str,                ← actual source code — read this, not the file
#   "how_it_works": str,            ← plain-English summary
#   "inputs": list[dict],           ← [{name, type, default}]
#   "output": str,                  ← return type
#   "raises": list[str],            ← exceptions this function raises
#   "edge_cases": list[str],        ← boundary scenarios to handle
#   "test_recommendations": list[str], ← what to mock, what cases to cover
#   "callers": list[str],           ← functions that call this one (blast radius)
#   "callees": list[str],           ← functions this one calls
#   "complexity": int,              ← cyclomatic complexity
#   "is_async": bool,
# }
```

### `nelgraph.get_class_context(class_name)`
Full class with methods, source, and inheritance chain.

```python
ctx = nelgraph.get_class_context("UserService")
# {
#   "class": {...},
#   "methods": [{"name", "start_line", "complexity", "docstring"}, ...],
#   "parent_classes": [{"name", "file"}, ...],
#   "child_classes":  [{"name", "file"}, ...],
# }
```

### `nelgraph.search(query, top_k=10, exclude_tests=True)`
Semantic search when you don't know the exact function name.

```python
results = nelgraph.search("user authentication and session handling", top_k=10)
# [{"name": str, "file": str, "score": float, "description": str}, ...]
```

Always follow up with `get_function_context()` to get the actual source.

### `nelgraph.dump_context_to_file(name, path, format="markdown")`
Export full context to a file. Use this on Windows (encoding issues) or when
context is too large to print to console.

```python
nelgraph.dump_context_to_file("login", "context/login.md")
nelgraph.dump_context_to_file("AuthService", "context/auth_class.md")
nelgraph.dump_context_to_file("login", "context/login.json", format="json")
# Returns True on success, False if name not found
```

### `nelgraph.get_changes(commit_hash)`
Functions changed in a specific commit with risk assessment.

```python
changes = nelgraph.get_changes("a3f9c12")
# {
#   "risk_level": "high" | "medium" | "low",
#   "changed_functions": [{"name", "file", "complexity", "has_test"}, ...]
# }
```

### `nelgraph.mark_tested(function_name, file=None)`
Persist test coverage status to the graph.

```python
nelgraph.mark_tested("login")
nelgraph.mark_tested("execute", file="src/services/runner.py")
```

---

## When to use what

| Goal                                 | Correct approach                                             |
| ------------------------------------ | ------------------------------------------------------------ |
| Understand overall project structure | `get_snapshot()` → read community names + summaries          |
| Find functions related to a feature  | `search(query)` → then `get_function_context()`              |
| Read source code of a function       | `get_function_context(name)["raw_code"]`                     |
| Know who breaks if I change this     | `get_function_context(name)["callers"]`                      |
| Understand a class and its hierarchy | `get_class_context(name)`                                    |
| Plan what tests to write             | `get_function_context(name)["test_recommendations"]`         |
| Work from a diff or PR               | `get_changes(commit_hash)`                                   |
| Context too large / Windows encoding | `dump_context_to_file(name, path)`                           |
| Debug a line-level issue             | `get_function_context(name)["raw_code"]` — read it carefully |

Note: the graph is excellent for architecture and navigation questions.
For line-level bugs (off-by-one, wrong variable), read `raw_code` — metadata
summaries will not surface those details.

---

## CLI Reference

```bash
nelgraph init            # first-time setup: parse + embed + enrich codebase
nelgraph sync            # incremental sync since last commit
nelgraph sync --silent   # sync without stdout (for scripts/hooks)
nelgraph status          # show graph stats and last sync info
nelgraph install-hook    # install git post-commit + pre-push hooks
nelgraph viz             # launch local dashboard at http://localhost:8080
```

---

## Rules

1. **Sync first, always.** No exceptions. Run `nelgraph.run_sync()` before any task.
2. **Orient before acting.** Call `get_snapshot()` before writing a single line of code or analysis.
3. **Graph over filesystem.** Never read files or list directories to understand the codebase — the graph has it.
4. **`raw_code` over file opens.** When you need source, read `ctx["raw_code"]` — do not open the file.
5. **Disambiguate common names.** Pass `class_name` or `file` for `__init__`, `run`, `handle`, `execute`.
6. **Check callers before changing anything.** `ctx["callers"]` is the blast radius — always check it.
7. **Use `test_recommendations` as your test plan.** Do not write tests from scratch without reading it first.
8. **Dump for large context.** Use `dump_context_to_file()` on Windows or when context is very large.
9. **Mark tested functions.** Always call `mark_tested()` after a function's tests pass.
