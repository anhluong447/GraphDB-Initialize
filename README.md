# GraphRAG for Codebases 🚀

An autonomous, zero-configuration Knowledge Graph builder and semantic search engine optimized for local codebases and AI testing agents. It ingests source code, AST Call Graphs, and Git history into a hybrid Graph-Vector database (**Neo4j** + **ChromaDB**) using **DeepSeek V4-Flash**.

---

## ✨ Key Features

1. **Zero-Configuration Isolation (Plug-and-Play)**:
   All database files, vector spaces, and sync status files are stored directly inside the target codebase's local hidden folder (`.graphrag_data/`). No centralized databases to manage or conflict.
   
2. **Rich AST Call-Graph Parser**:
   Uses **Tree-Sitter** to parse Python, PHP, JavaScript, TypeScript, JSX, and TSX files. It extracts class/function syntax structures, docstrings, complexity, inputs, outputs, decorators, and builds exact function call relationships.

3. **ChromaDB Storage & Dimension Optimization**:
   Omit raw codebase source code strings from ChromaDB entirely to prevent database bloating. Uses an optimized 512-dimension vector embedding configuration. Search result descriptions are dynamically reconstructed on the fly using a single batched database lookup to Neo4j.

4. **Dynamic Code Retrieval & Drift Recovery**:
   Instead of cache-bloating Neo4j with full source code copies, it maps functions and classes to exact line coordinates and an `anchor` string fingerprint. The system loads code dynamically on-demand from disk, with an auto-recovery parser that updates coordinates in Neo4j if line numbers shift due to codebase edits.

5. **Dynamic Import & Dependency Analyzer**:
   Tracks module import statements (`File -[:IMPORTS]-> Module`). Automatically detects Python standard library modules dynamically (using `sys.stdlib_module_names` in Python 3.10+ with local fallback) to cleanly categorize dependencies as *stdlib*, *external*, or *internal*.

6. **Git Commit-to-Function Line Mapper**:
   Tracks Git history, parses unified git diff hunks to retrieve exact line changes, and maps commits directly to the specific functions they modified (`Commit -[:CHANGED]-> Function`) using overlapping line ranges. Great for feeding Test Impact Analysis agents!

7. **Self-Correction LLM Extraction Loop**:
   Resolves common LLM JSON syntax errors by integrating `json-repair`. If parsing still fails or keys are missing, the system starts a self-correction feedback loop, feeding the incorrect text and error trace back to the LLM to rewrite the output (retrying up to 4 attempts).

8. **Robust Startup Handshake**:
   Uses connection polling (`_wait_for_neo4j()`) instead of static timeouts, ensuring that dockerized databases are fully initialized and Bolt handshake is ready before building indexes.

9. **Direct Python Module Interface**:
   Exposes a clean, state-free, programmatic Python API (`knowledge_base.py`) for autonomous agents to plan, query, and synchronize test generation tasks in-process.

---

## 🛠️ Tech Stack

* **Core**: Python 3.10+
* **Parsing**: Tree-Sitter (Python, PHP, TS, JS)
* **Graph DB**: Neo4j (Bolt protocol)
* **Vector DB**: ChromaDB
* **LLM / Embeddings**: DeepSeek V4-Flash & OpenAI Embeddings via OpenRouter
* **Visualization Backend**: FastAPI (Uvicorn)
* **Visualization Frontend**: React (`react-force-graph-2d` & D3)

---

## 📂 Project Structure

```text
D:\GraphRAG/
├── config.py                 # System configuration and environment loader
├── docker-compose.yml        # Multi-container orchestration (Neo4j, ChromaDB)
├── start_all.bat             # 1-Click launcher script for Windows developers
├── .env                      # Local environment configurations (ignored in git)
├── initialize_graph.py       # Main entry point for full init / incremental sync
├── knowledge_base.py         # Python module interface for autonomous agents
├── parsers/                  # Code and Git history parsers (upgraded rich AST)
├── extractors/               # Entity extractors and AI Testing Enricher
├── community/                # Graph clustering and community summarization
├── query/                    # Hybrid search and context synthesis engine
├── updater/                  # Filesystem Watcher and Git Hooks
├── visualization/            # FastAPI Backend & React Frontend Dashboard (Visualizer)
├── mcp/                      # Model Context Protocol TS/JS server
├── docs/                     # Documentation and integration guides
│   ├── USAGE.md              # Quick usage guide for knowledge_base.py
│   ├── INTEGRATION_GUIDE.md  # Detailed Vietnamese integration guide
│   ├── architecture.md       # High-level architecture documentation
│   ├── agent_design_guide.md # Integration guide for test generation agents
│   ├── api_sufficiency.md   # Evaluation of Python API sufficiency for agents
│   ├── graphrag-level3.md    # Deployment guide for all building phases
│   └── updates/              # Archive of historical update plans (0.1, 0.3, 0.4, 0.5)
├── _archive/                 # Archived components (like legacy REST API server)
└── scratch/                  # Test scripts and development playground
```

---

## 🚀 Quick Start

### 1. Configure Environment
Create a `.env` file in this directory (you can copy `.env.example`):
```env
# OpenRouter API Key (required for LLM & Embeddings)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx...

# Path to the target codebase you want to analyze (relative or absolute)
CODEBASE_PATH=../my-target-project
```

### 2. Run Initialization
Run the main script to start databases, update gitignores, and perform full ingestion:
```bash
python initialize_graph.py
```
*Tip: On the first run, this script will automatically create a quick-run wrapper (`run_graphrag.bat` on Windows or `run_graphrag.sh` on Unix) in your target codebase root so you can trigger updates without leaving your project directory.*

---

## 🔌 Programmatic Python Integration API (`knowledge_base.py`)

You can import the module directly into your local scripts/test agents to query the codebase knowledge base:

```python
from knowledge_base import get_snapshot, get_function_context, mark_tested

# 1. Get snapshot of prioritized functions needing tests
snapshot = get_snapshot()
for comm in snapshot['communities']:
    print(f"Community: {comm['name']}")
    for func in comm['functions']:
        print(f"  - {func['name']} (Priority: {func['priority_score']})")

# 2. Retrieve context (source code, calling graph, test specs) for a function
ctx = get_function_context("process_payment")
print(ctx["function"]["raw_code"])
print(ctx["function"]["edge_cases"])

# 3. Mark function as verified
mark_tested("process_payment")
```

For more details on integration, please refer to:
* 📖 [Quick Usage Guide](file:///D:/GraphRAG/docs/USAGE.md)
* 📖 [Vietnamese Integration Guide](file:///D:/GraphRAG/docs/INTEGRATION_GUIDE.md)
* 📖 [Agent Integration Guide](file:///D:/GraphRAG/docs/agent_design_guide.md)
* 📖 [Architecture Reference](file:///D:/GraphRAG/docs/architecture.md)
