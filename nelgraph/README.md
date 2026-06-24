# nelgraph 🚀

An autonomous, zero-configuration Knowledge Graph builder and semantic search engine optimized for local codebases and AI testing agents. It ingests source code, AST Call Graphs, Class Inheritance structures, and Git history into a hybrid Graph-Vector database (**Neo4j** + **ChromaDB**) using **DeepSeek V4-Flash**.

## 🛠️ Installation

```bash
pip install nelgraph
```

## 🚀 CLI Usage

### 1. Initialize GraphRAG for your project
Navigate to your project directory and run:

```bash
nelgraph init
```

During initialization, it will:
- Prompt you for your OpenRouter API key.
- Configure the local `.env` and `.graphrag_data/` directory.
- Start Neo4j inside a local Docker container.
- Build structural nodes, relations, and indexes.
- Install a git post-commit hook so the graph auto-syncs.
- Automatically generate the AI Agent Skill definition file at `.agents/nelgraph/SKILL.md`.

### 2. Manual Synchronization
If you want to manually trigger incremental synchronization (e.g. after changes):

```bash
nelgraph sync
```

### 3. Check Status
View current database metrics, indexed function counts, and AI enrichment coverage:

```bash
nelgraph status
```

### 4. Install Git Hook
Manually install the Git post-commit / pre-push hook for auto-syncing the graph:

```bash
nelgraph install-hook
```

---

## 🔌 Programmatic Python API

You can import `nelgraph` directly into your scripts or AI testing agents:

```python
import nelgraph

# Configure (if .env is not present or needs custom config)
nelgraph.configure(
    codebase_path="/absolute/path/to/project",
    openrouter_api_key="your-openrouter-key"
)

# 1. Get snapshot of prioritized functions
# Returns functions grouped by community, sorted by priority score
snapshot = nelgraph.get_snapshot()
print(f"Total functions: {snapshot['total']}")

# 2. Retrieve detailed context for a function
# Disambiguate functions with same name using optional class_name or file filters
ctx = nelgraph.get_function_context("execute", class_name="CalculationContext")
print(ctx.get("function", {}).get("how_it_works"))

# 3. Retrieve detailed context for a class
# Returns class details, parent classes, child classes, methods, docstring, and source code
class_ctx = nelgraph.get_class_context("ExpressionParser")
print(class_ctx.get("parent_classes"))

# 4. Export context to a file (Markdown or JSON)
# Resolves class before function; saves to path
success = nelgraph.dump_context_to_file("ExpressionParser", "./scratch/class_context.md", format="markdown")

# 5. Semantic Search
# Uses vector similarity search to find functions/concepts related to a query
results = nelgraph.search("user authentication flow")
for r in results:
    print(r["name"], r["score"])

# 6. Mark function as tested/verified
# Persists testing status directly to the graph
nelgraph.mark_tested("process_order")
```

---

## 🤖 AI Agent Skill Interface

When `nelgraph init` runs, it generates `.agents/nelgraph/SKILL.md`. This file contains standard Model Context Protocol (MCP) skill signatures and operational rules for downstream LLM agents. Agents can read this file at the start of a session to understand how to query code context, track progress, and run synchronization.
