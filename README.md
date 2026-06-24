# nelgraph 🚀

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]()
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()
[![Version](https://img.shields.io/badge/version-1.1.4-orange.svg)]()

An autonomous, zero-configuration **GraphRAG (Graph Retrieval-Augmented Generation)** knowledge base builder and semantic search engine optimized for local codebases and autonomous AI coding agents. 

It automatically parses source code, builds Abstract Syntax Tree (AST) call graphs, resolves class hierarchies, maps Git commit histories, and ingests them into a unified hybrid database system (**Neo4j** for structural graph relations + **ChromaDB** for vector semantic indexes) powered by **DeepSeek V4-Flash**.

---

## 📖 Table of Contents
1. [Core Philosophy](#-core-philosophy)
2. [Key Features](#-key-features)
3. [Technology Stack](#-technology-stack)
4. [Project Structure](#-project-structure)
5. [Installation & Setup](#-installation--setup)
6. [CLI Command Reference](#-cli-command-reference)
7. [Programmatic Python API](#-programmatic-python-api)
8. [Interactive Visualization Dashboard](#-interactive-visualization-dashboard)
9. [Automated Testing Environment](#-automated-testing-environment)
10. [Agent Skill Integration](#-agent-skill-integration)

---

## 💡 Core Philosophy

AI coding agents struggle with large codebases because reading raw files is slow, expensive, and lacks structural context. `nelgraph` bridges this gap:
* **Graph-Driven Navigation**: Instead of searching files blindly, agents query a structured knowledge graph to instantly understand function calls, dependencies, and inheritance paths.
* **Isolated Zero-Config Storage**: All database assets, environment details, and sync status profiles are nested locally within the target codebase's hidden directory (`.graphrag_data/`). No centralized servers to maintain or conflict.
* **Dynamic Code Resolution**: Rather than duplicating source code into Neo4j (which bloats caches and causes drift), the graph maps methods to exact coordinates and code fingerprints. Code is loaded dynamically from disk on demand, with an auto-recovery parser that corrects coordinates if lines shift due to local edits.

---

## ✨ Key Features

* 🧬 **AST Call-Graph Parser**: Powered by **Tree-Sitter** to parse Python, PHP, JavaScript, and TypeScript/JSX/TSX. It extracts classes, functions, complexity, input signatures, return types, raises, and constructs precise call relationships.
* 📦 **Dynamic Import & Dependency Tracker**: Maps module imports (`File -[:IMPORTS]-> Module`). Automatically distinguishes standard library, external packages, and internal project dependencies.
* 🌿 **Git Commit-to-Function Mapper**: Parses Git commit diffs to link modified lines directly to the specific functions they affected (`Commit -[:CHANGED]-> Function`), enabling precise Test Impact Analysis.
* 🔍 **Hybrid Vector-Graph Queries**: Combines vector database semantic similarity searches (ChromaDB) with graph relation expansions (Neo4j) to synthesis comprehensive multi-layered context.
* 🔄 **Git Hooks Auto-Sync**: Integrates post-commit and pre-push hooks to automatically run incremental synchronizations, ensuring the graph never becomes stale.
* 🛠️ **Self-Healing LLM Extraction**: Combines `json-repair` with a self-correction feedback loop. If the LLM generates malformed JSON metadata, the system automatically feeds the errors back to the LLM to self-heal and regenerate (up to 4 retries).
* 📊 **Interactive Force-Directed Dashboard**: Launch a local web explorer (`nelgraph viz`) with optimized layout physics (node collision protection, charge range limits) to visually map and filter classes, functions, files, communities, and test coverage.

---

## 🛠️ Technology Stack

* **Parsing**: Tree-Sitter (Python, PHP, JS, TS)
* **Graph Database**: Neo4j (Bolt Protocol, Dockerized)
* **Vector Database**: ChromaDB (Flat Vector Indexing)
* **LLM Engine**: DeepSeek V4-Flash & OpenAI Text Embeddings via OpenRouter
* **Visualization Backend**: FastAPI (Uvicorn)
* **Visualization Frontend**: React (Vite) + `react-force-graph-2d` + D3 Force

---

## 📂 Project Structure

```text
D:\GraphRAG/
├── config.py                 # System config and environment loader
├── docker-compose.yml        # Docker orchestration for local Neo4j
├── start_all.bat             # 1-Click developer launcher for Windows
├── Makefile                  # Cross-platform orchestration tasks
├── initialize_graph.py       # CLI wrapper for ingestion & sync
├── knowledge_base.py         # Python programmatic API for AI agents
├── core/                     # Core synchronization & database pipelines
├── parsers/                  # Code AST and Git history parsers
├── extractors/               # AI metadata extraction & enrichment loops
├── community/                # Graph clustering and community summarization
├── query/                    # Hybrid search and context synthesis engine
├── updater/                  # Filesystem watcher & Git hook scripts
├── visualization/            # FastAPI + React visualization dashboard
├── mcp/                      # Model Context Protocol TS/JS server
└── docs/                     # Comprehensive documentation & architecture references
```

---

## 🚀 Installation & Setup

### 1. Prerequisites
- **Python 3.10+**
- **Docker Desktop** (running and configured)
- **Node.js 18+** (only if building/developing visualization frontend)

### 2. Standard Installation
Install the package directly from PyPI:
```bash
pip install nelgraph
```

### 3. Local Development Setup
Clone the repository and install packages:
```bash
git clone https://github.com/anhluong447/GraphDB-Initialize.git D:\GraphRAG
cd D:\GraphRAG
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e ./nelgraph
```

---

## 💻 CLI Command Reference

Execute commands from your terminal:

```bash
nelgraph init            # 1. First-time setup: launches Neo4j container, parses code, embeds and enriches codebase
nelgraph sync            # 2. Performs incremental sync to index changes since last synced commit
nelgraph sync --silent   # Run synchronization silently (ideal for git hooks)
nelgraph status          # 3. View current DB metrics, function counts, and enrichment coverage
nelgraph install-hook    # 4. Install post-commit hooks for automatic graph synchronization
nelgraph viz             # 5. Launch the local interactive visualization dashboard at http://localhost:8080
```

---

## 🔌 Programmatic Python API

Import `nelgraph` to query your codebase programmatically:

```python
import nelgraph

# 1. Optional configuration (fallback to local .env if not specified)
nelgraph.configure(
    codebase_path="/absolute/path/to/project",
    openrouter_api_key="your-openrouter-api-key"
)

# 2. Orient: Get high-level overview of codebase grouped by community clusters
snapshot = nelgraph.get_snapshot()
print(f"Total indexed functions: {snapshot['total']}")
for comm in snapshot["communities"]:
    print(f"Cluster: {comm['name']} - {comm['summary'][:100]}...")

# 3. Search: Retrieve relevant functions via semantic vector similarity
search_results = nelgraph.search("database connection handling", top_k=5)
for res in search_results:
    print(f"Match: {res['name']} in {res['file']} (Score: {res['score']})")

# 4. Retrieve Context: Get full signatures, calls, test plans, and raw source
ctx = nelgraph.get_function_context("execute", class_name="OrderProcessor")
print("Source Code:\n", ctx["raw_code"])
print("Parameters Input:", ctx["inputs"])
print("Test Recommendations:", ctx["test_recommendations"])
print("Exceptions Raised:", ctx["raises"])
print("Callers (Blast Radius):", ctx["callers"])

# 5. Retrieve Class: Get class hierarchy, parent classes, and child methods
class_ctx = nelgraph.get_class_context("BaseController")
print("Parent classes:", class_ctx["parent_classes"])
print("Class methods:", class_ctx["methods"])

# 6. Save Context: Export large context files to bypass terminal encoding limits on Windows
nelgraph.dump_context_to_file("execute", "context_export.md", format="markdown")

# 7. Mark Tested: Persist unit test completion status directly into Neo4j
nelgraph.mark_tested("execute", file="src/processors/order.py")
```

---

## 📊 Interactive Visualization Dashboard

Launch the visual explorer:
```bash
nelgraph viz
```
This starts a FastAPI backend and loads the React dashboard at `http://localhost:8080`.

### Physical Layout Optimizations
To ensure complex codebases are easy to explore, the visualizer uses customized D3 force simulations:
* **Anti-Overlap Collision**: Integrates `forceCollide` representing nodes as physical circles with safety margins (`radius + 14px`). Node labels and icons never overlap.
* **Compact Peripheries**: Restricts many-body repulsion (`charge`) to a maximum radius using `distanceMax(250)`. This prevents disconnected files and external libraries from floating away into infinity, keeping them compactly structured around the main clusters.
* **Stretched Clusters**: Adjusts default link distances to `80px`, spreading out highly connected clusters for clean visibility.

---

## 🧪 Automated Testing Environment

The workspace includes a complete testing setup for both Frontend (React) and Backend (FastAPI).

### 1. Frontend UI Tests
Uses **Vitest** + **React Testing Library** + **jsdom** to test React components.
- **Location**: `nelgraph/nelgraph/visualization/frontend/`
- **Execution**:
  ```bash
  cd nelgraph/nelgraph/visualization/frontend
  npm run test          # Run once
  npm run test:watch    # Run in watch mode
  ```
- **Test Coverage**:
  - `DetailPanel.test.jsx`: Verifies metadata cards, list rendering of complex JSON structures (resolves Error 31), and chip navigations.
  - `GraphView.test.jsx`: Mocks canvas elements, tests filter switching, and verifies filtering out dangling links.
  - `ErrorBoundary.test.jsx`: Verifies rendering fallback panels and sending POST error logs to the API.

### 2. Backend Integration Tests
Uses **pytest** to verify FastAPI API routes.
- **Location**: `nelgraph/tests/`
- **Execution**:
  ```bash
  cd nelgraph
  pytest -v tests/
  ```
- **Test Coverage**:
  - `conftest.py`: Configures `mock_neo4j` fixture to intercept `get_client` calls, bypassing live database requirements.
  - `test_api.py`: Validates `/status`, `/log`, `/node/{name}`, `/node/{name}/mark_tested`, and checks dangling edge filtering in `/graph/full`.

---

## 🤖 Agent Skill Integration

When `nelgraph init` runs, it generates `.agents/nelgraph/SKILL.md`. This file contains strict instructions, workflows, and API descriptions that downstream LLM coding agents can load. Agents reading this file are instructed to:
1. Always run synchronization (`nelgraph.run_sync()`) before taking actions.
2. Read overall project structure via `get_snapshot()` rather than scanning directory trees.
3. Query source code via `get_function_context()["raw_code"]` instead of opening files directly.
4. Inspect `ctx["callers"]` to calculate change blast radii before refactoring.
5. Use `test_recommendations` as a baseline blueprint for test writing.
