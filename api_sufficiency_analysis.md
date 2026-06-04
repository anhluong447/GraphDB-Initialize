# GraphRAG API Sufficiency Analysis for Autonomous Test Agents

This document evaluates the suitability of the GraphRAG Knowledge Base REST API (implemented in `server/api.py` and documented in `README.md`) for integration with an autonomous AI test-generation agent. It details how the agent can consume the API and outlines a concrete fix plan for all identified gaps.

---

## 📌 Executive Summary

**Verdict:** **SUFFICIENT with Minor Gaps**

The GraphRAG REST API provides a complete end-to-end integration flow matching the **DA01 Workflow Design**. A test generation agent has access to all necessary metadata, code content, call graphs, and AI-enriched recommendations to plan, generate, execute, and track unit tests.

### 🌟 Key Strengths
1. **Dynamic Code Retrieval**: Unlike standard GraphRAG implementations that bloat the database with static code blocks, the `/api/context/{name}` endpoint loads the code dynamically from disk. This guarantees the agent always acts on the latest source code.
2. **Prioritization Layer**: `/api/repo/snapshot` returns functions sorted by a computed `priority_score` (combining complexity, imports/callers, and git churn), saving valuable LLM tokens by letting the agent target high-risk components first.
3. **Pre-Generated Test Specs**: Function nodes are pre-enriched with inputs/outputs specifications, specific edge cases, and mocking targets, lowering the cognitive load of the test agent.

---

## 🔄 Integration Architecture & Workflow

Since diagram engines can be difficult to interpret, the execution flow is visualized below using a simple ASCII diagram followed by a step-by-step text description:

### 1. ASCII Flow Diagram

```text
[ Phase 1: Planning ]
  │
  ├──► 1. POST /api/repo/init ──────► Clones and analyzes repository
  │
  └──► 2. POST /api/repo/snapshot ──► Retrieves all functions sorted by Priority Score
                                      (Complexity + Churn + Caller Connections)

[ Phase 2: Generation Loop ]
  │
  ├──► 3. GET /api/context/{name} ──► Fetch function source code, dependency mocks, 
  │                                   edge cases, and class constructors
  ├──► 4. Run Locally ──────────────► Agent writes and executes tests in local sandbox
  │
  └──► 5. POST /api/test/done ──────► Mark function as tested (has_test = true)

[ Phase 3: Incremental Sync ]
  │
  ├──► 6. Git Push Webhook ─────────► Server automatically triggers background updates
  │
  └──► 7. GET /api/changes ─────────► Retrieve only the changed functions for testing
```

### 2. Step-by-Step Workflow Explanation

* **Step 1: Initialization** — The test agent initiates the pipeline for a codebase by calling `/api/repo/init`. It polls the status endpoint `/api/repo/status/{job_id}` until the extraction is complete.
* **Step 2: Coverage Mapping** — The agent calls `/api/repo/snapshot` to fetch a list of all functions in the codebase. It filters for functions where `has_test == false` and sorts them by `priority_score` (highest priority first).
* **Step 3: context-Rich Prompting** — For each function in the queue, the agent calls `/api/context/{function_name}` to load:
  * The exact python/javascript source code string.
  * The names of external modules/functions it calls (for mock setup).
  * The target edge cases and testing recommendations pre-extracted by the AI.
* **Step 4: Test Compilation & Execution** — The agent feeds this structured context to its test-generation LLM, runs the generated test file locally, and verifies it passes.
* **Step 5: Updating Progress** — Once the test passes, the agent updates the database by calling `/api/test/done`.
* **Step 6: Completion** — After completing all files, the agent transitions the server to lightweight monitor mode using `/api/first_run/complete`.

---

## 🧪 Mock Agent Integration Test Script

To verify that the APIs are ready and functional, we have implemented a standalone mock agent integration script in the workspace at:
👉 **[scratch/mock_agent.py](file:///d:/GraphDB-Initialize/scratch/mock_agent.py)**

This script serves as a test suite for the REST API server itself, simulating a real agent client session.

### What the Mock Agent Does:
1. **Trigger & Poll**: Starts the ingestion pipeline via `/api/repo/init` and polls `/api/repo/status/{job_id}` until completion.
2. **Retrieve Blueprint**: Requests `/api/repo/snapshot` and prints the top 5 highest-priority functions needing tests.
3. **Loop & Inspect**: Queries `/api/context/{name}` for the top 2 functions to inspect the returned payloads (`raw_code`, `edge_cases`, `test_recommendations`, and `class_context`).
4. **Mark Accomplished**: Submits test completions back using `/api/test/done`.
5. **Transition Server**: Signals completion via `/api/first_run/complete` and displays final server states.

### How to Run the Mock Agent:
1. Start the API server in server mode (port 8080):
   ```bash
   python start_server.py --port 8080
   ```
2. In a separate terminal, execute the mock agent:
   ```bash
   python scratch/mock_agent.py
   ```

---

## 🛠️ Gap Analysis & Concrete Fix Plan

We have identified **three specific gaps** that could cause the test-generation agent to crash or produce invalid mock setups. Below is the concrete implementation plan to fix each gap in the codebase.

### Gap 1: Namespace Collisions (Duplicate Function Names)
* **The Problem:** The current `/api/context/{name}` endpoint searches for functions solely by name (`MATCH (f:Function {name: $name})`). If the target codebase has multiple functions with the same name in different directories (e.g. `save()` in `database.py` and `save()` in `image_processor.py`), the endpoint returns the first one it finds.
* **The Fix:** Allow the client to pass an optional `file` query parameter to filter by path.
* **Implementation Plan (File: `server/api.py`):**
  Modify `/api/context/{name}` to accept a `file` parameter:
  ```python
  @app.get("/api/context/{name}")
  def get_context(name: str, file: Optional[str] = None):
      # ...
      if file:
          result = client.run("""
              MATCH (f:Function {name: $name, file: $file})
              OPTIONAL MATCH (f)-[:BELONGS_TO]->(c:Community)
              RETURN f, c.id as community_id, c.name as community_name, c.summary as community_summary
              LIMIT 1
          """, {"name": name, "file": file})
      else:
          result = client.run("""
              MATCH (f:Function {name: $name})
              OPTIONAL MATCH (f)-[:BELONGS_TO]->(c:Community)
              RETURN f, c.id as community_id, c.name as community_name, c.summary as community_summary
              LIMIT 1
          """, {"name": name})
  ```

---

### Gap 2: Missing Class Constructor Context for Class Methods
* **The Problem:** When writing unit tests for a class method, the test agent must instantiate the class. This requires knowing the constructor method (`__init__`) signature. Currently, the API returns the source code of the method itself, but not the constructor, leaving the agent blind on how to construct the object.
* **The Fix:** If the requested function has a `class_name` attribute, query the database to retrieve the `__init__` constructor of that same class and append it to the response object.
* **Implementation Plan (File: `server/api.py`):**
  Add a `class_context` block inside `/api/context/{name}`:
  ```python
      # Retrieve constructor context if it belongs to a class
      class_context = None
      if func_data.get("class_name") and func_data.get("file"):
          class_res = client.run("""
              MATCH (f:Function {name: "__init__", file: $file, class_name: $class_name})
              RETURN f
              LIMIT 1
          """, {"file": func_data["file"], "class_name": func_data["class_name"]})
          
          if class_res:
              init_node = dict(class_res[0]["f"])
              # Read constructor source code dynamically
              init_node["raw_code"] = client.read_node_code(init_node)
              class_context = {
                  "class_name": func_data["class_name"],
                  "constructor": {
                      "inputs": init_node.get("inputs"),
                      "docstring": init_node.get("docstring"),
                      "raw_code": init_node["raw_code"]
                  }
              }
              
      return {
          "function": func_data,
          "class_context": class_context,  # Added constructor info
          "community": community,
          "calls_outside": [dict(r) for r in calls_outside],
          "called_by": [dict(r) for r in called_by],
      }
  ```

---

### Gap 3: Missing Search & Query Endpoints in API Documentation
* **The Problem:** The backend server file `server/api.py` implements `/api/health` and `/api/test/done`, but does not document search endpoints like `/query` or `/graph/search` in `README.md` under the REST API section.
* **The Fix:** Document these endpoints in the REST specification table of `README.md` so the integrating team knows they can query general codebase questions semantic-style.
* **Implementation Plan (File: `README.md`):**
  Update the REST API table to include:
  ```markdown
  | **BOTH** | `/query?q={query}` | `GET` | Perform hybrid semantic query on the codebase knowledge base. |
  | **BOTH** | `/graph/search?q={query}` | `GET` | Retrieve nodes and descriptions that match keyword/text search. |
  ```

---

## 📝 Conclusion & Action Items

Implementing these fixes guarantees that the third-party testing agent will:
1. Never import/mock the wrong function when name overlaps exist across files.
2. Successfully compile class-method tests by knowing how to initialize class arguments.
3. Utilize search capabilities for open-ended queries about code integration.
