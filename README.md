# GraphRAG for Codebases 🚀

An autonomous, zero-configuration Knowledge Graph builder and semantic search engine optimized for local codebases and AI testing agents. It ingests source code, AST Call Graphs, and Git history into a hybrid Graph-Vector database (**Neo4j** + **ChromaDB**) using **DeepSeek V4-Flash**.

---

## ✨ Key Features

1. **Zero-Configuration Isolation (Plug-and-Play)**:
   All database files, vector spaces, and sync status files are stored directly inside the target codebase's local hidden folder (`.graphrag_data/`). No centralized databases to manage or conflict.
   
2. **Rich AST Call-Graph Parser**:
   Uses **Tree-Sitter** to parse Python, JavaScript, TypeScript, JSX, and TSX files. It extracts class/function syntax structures, docstrings, complexity, inputs, outputs, decorators, and builds exact function call relationships.

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

---

## 🛠️ Tech Stack

* **Core**: Python 3.10+
* **Parsing**: Tree-Sitter (Python, TS, JS)
* **Graph DB**: Neo4j (Bolt protocol)
* **Vector DB**: ChromaDB
* **LLM / Embeddings**: DeepSeek V4-Flash & OpenAI Embeddings via OpenRouter
* **Backend API**: FastAPI (Uvicorn)
* **Frontend Dashboard**: React (`react-force-graph-2d` & D3)

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

## 💻 CLI Commands

Run `initialize_graph.py` with these helpful flags:

* **Inspect Graph Status**:
  Prints statistics of the indexed codebase (number of files, functions, AI enrichment coverage, modules, and commits) without performing any sync or LLM operations.
  ```bash
  python initialize_graph.py --status
  ```
  
* **Force Full Reinitialization**:
  Wipes clean all data inside `.graphrag_data/` (Neo4j and ChromaDB) and restarts the ingestion process from scratch.
  ```bash
  python initialize_graph.py --force-init
  ```

* **Incremental Sync**:
  Running without arguments parses only new, deleted, or modified files since the last run. Saves time and LLM token costs!
  ```bash
  python initialize_graph.py
  ```

---

## 📊 Verification Queries (Neo4j Cypher)

Open the Neo4j Browser at `http://localhost:7474` (credentials: `neo4j` / `graphrag123`) and run these queries to verify your graph structure:

* **Find External Dependencies Called by Functions**:
  ```cypher
  MATCH (f:Function)-[:USES_EXTERNAL]->(m:Module {is_external: true})
  RETURN f.name, f.file, m.name LIMIT 10
  ```

* **Inspect Commits Modifying Specific Functions**:
  ```cypher
  MATCH (c:Commit)-[:CHANGED]->(fn:Function)
  RETURN c.hash, c.author, fn.name, fn.file LIMIT 10
  ```

* **View AI-Enriched Test Recommendations**:
  ```cypher
  MATCH (f:Function) WHERE f.test_recommendations IS NOT NULL
  RETURN f.name, f.test_recommendations LIMIT 5
  ```

---

## 🔌 Local Python Integration API

You can import the query engine directly into your local scripts/test agents to retrieve contextual codebase answers or structured test specs:

```python
import sys
import os

# Add GraphRAG to path
sys.path.append(os.path.abspath("path/to/GraphRAG"))

from query.engine import query_codebase

# Retrieve synthesized answers with source nodes and relations
response = query_codebase("How does the authenticating flow work?")
print(response["answer"])
```

---

## 🖥️ Server Mode (Knowledge Base API Server) 🌐

GraphRAG can run as a standalone API server to decouple the database from client codebases. This exposes REST endpoints designed for autonomous testing agents (Mô hình A).

### 1. Setup Server Mode
In your `.env` file, configure the server options:
```env
# Enable server mode (centralizes storage inside ./server_data/)
SERVER_MODE=true

# Secure your endpoints with an API key (requests must pass X-API-Key header)
API_KEY=your-secret-api-key-here

# Directory on the server where repositories will be cloned
WORKSPACE_DIR=./workspace

# Optional: Webhook URL of the Auto-Test Agent to notify on pipeline changes
WEBHOOK_URL=
```

### 2. Start the Server
Start the Uvicorn-based FastAPI server (which automatically boots Neo4j and ChromaDB):
```bash
# On Windows, double-click:
.\start_server.bat

# Or run via Python:
python start_server.py --port 8080
```
API Documentation will be accessible at: `http://localhost:8080/docs`

### 3. API Endpoints Reference (DA01 Spec)

| Mode | Endpoint | Method | Description |
|---|---|---|---|
| **FIRST_RUN** | `/api/repo/init` | `POST` | Initialize codebase from local path or remote Git URL. Runs async pipeline. |
| **FIRST_RUN** | `/api/repo/status/{job_id}` | `GET` | Get status and progress percentage of initialization pipeline. |
| **FIRST_RUN** | `/api/repo/snapshot` | `POST` | Return all parsed functions grouped by community with computed `priority_score`. |
| **FIRST_RUN** | `/api/first_run/complete` | `POST` | Mark test generation finished, switch server to `ONGOING` mode, flush commit queue. |
| **ONGOING** | `/api/changes` | `GET` | Get list of functions changed by a specific commit hash and its risk level. |
| **BOTH** | `/api/context/{name}` | `GET` | Retrieve full subgraph context, docstrings, source code, and AI test specs. |
| **BOTH** | `/api/functions` | `GET` | List all indexed functions with optional filters. |
| **BOTH** | `/api/test/done` | `POST` | Mark a function as tested (`has_test = true` flag updated in Neo4j). |
| **BOTH** | `/api/git-sync` | `POST` | Webhook triggered on Git Push events. Executes background incremental sync. |
| **BOTH** | `/api/health` | `GET` | Verify server status, DB connections, and current operating mode. |

### 4. Client Integration Examples

#### Initialize Codebase
```bash
curl -X POST http://localhost:8080/api/repo/init \
  -H "X-API-Key: your-secret-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/example/demo-project.git", "language": "python"}'
```

#### Poll Status
```bash
curl http://localhost:8080/api/repo/status/job-123456 \
  -H "X-API-Key: your-secret-api-key-here"
```

#### Get Snapshot
```bash
curl -X POST http://localhost:8080/api/repo/snapshot \
  -H "X-API-Key: your-secret-api-key-here"
```

#### Get Function Context
```bash
curl http://localhost:8080/api/context/process_payment \
  -H "X-API-Key: your-secret-api-key-here"
```

