# Integration Guide: How External Test Agents Consume GraphRAG

This guide details the API protocols, integration architecture, and status synchronization flows exposed by the GraphRAG Knowledge Base server. It is designed to assist external autonomous test agents in integrating with and consuming the GraphRAG pipeline from separate codebase projects.

---

## 🏗️ 1. Architecture Overview (Client-Server Separation)

The GraphRAG Knowledge Base operates on a decoupled client-server model:
* **GraphRAG Server (Host/Server)**: The server houses the database engines (Neo4j, ChromaDB) and coordinates the AST extraction, LLM semantic enrichment, and community division.
* **Test Agent (Client)**: The agent runs locally or in CI/CD within the target project codebase. It connects to the server REST API over HTTP, analyzes the codebase blueprint, and designs/saves tests directly inside the local project files.

```text
  ┌──────────────────────────────┐              ┌───────────────────────────────┐
  │      Target Project          │              │    GraphRAG Server (Remote)   │
  │     (Separate Workspace)     │              │     (FastAPI, Neo4j, Chroma)  │
  │                              │              │                               │
  │ 1. Verify health & path  ────┼─────────────►│ GET /api/health               │
  │ 2. Ingest codebase (init) ───┼─────────────►│ POST /api/repo/init           │
  │ 3. Poll pipeline progress ───┼─────────────►│ GET /api/repo/status/{job}    │
  │ 4. Get blueprint/snapshot ───┼─────────────►│ POST /api/repo/snapshot       │
  │ 5. Request function context ─┼─────────────►│ GET /api/context/{func_name}  │
  │ 6. Sync test status (done) ──┼─────────────►│ POST /api/test/done           │
  └──────────────────────────────┘              └───────────────────────────────┘
```

---

## 🔄 2. Connection, Discovery & Ingestion Flow

When the agent starts up inside a codebase, it must verify if the codebase has already been indexed on the server. The client-side agent does not initiate new builds or call `/api/repo/init` (which is restricted on the server to prevent data loss). Instead, it locates the pre-existing graph for the repository.

### Step A: Verify Graph Status by Repository Name
1. Send a `GET` request to `/api/health` to inspect the server's current operational state:
```http
GET /api/health
```

#### Response Structure:
```json
{
  "status": "ok",
  "mode": "ONGOING",
  "total_functions": 125,
  "queued_commits": 0,
  "last_sync": "2026-06-04T12:00:00",
  "current_job": null,
  "codebase_path": "/app/opensourcepos"
}
```

2. Extract and compare the **repository directory name** from both the server's `codebase_path` and the client's `TARGET_REPO_URL` (case-insensitive) to handle cross-platform paths (e.g. comparing `opensourcepos` from `/app/opensourcepos` and `D:\projects\opensourcepos`).

3. **Fallback Discovery**: If the server is in `IDLE` mode or the codebase path does not match directly, the agent sends a query to `GET /api/functions?limit=5` and inspects the first few returned function file paths. If the extracted repository name of those functions matches the target repository, the graph exists in the database.

#### State Evaluation Matrix:
| Server Mode / DB State | Repository Name Matches? | Action Required |
| :--- | :--- | :--- |
| **`FIRST_RUN`** | **Yes** | **Ingestion Running/Unfinished**: Retrieve `current_job`. If a job is active, attach to it and poll status (Step B). |
| **`ONGOING` / `IDLE` (with functions)** | **Yes** | **Complete**: The graph is fully built. Skip ingestion and proceed to test planning (Step C). |
| *Any* | **No / Not Found** | **Not Indexed**: Print a clear error message instructing the user to run the indexer on the server first, then exit with code 1. |

---

### Step B: Tracking Active Ingestion Progress
If an ingestion job is still running (in `FIRST_RUN` mode), the agent attaches to the job and polls `GET /api/repo/status/{job_id}`:
* **Request**:
  ```http
  GET /api/repo/status/job-a1b2c3d4
  ```
* **Response**:
  ```json
  {
    "job_id": "job-a1b2c3d4",
    "step": "6/9",
    "progress": 66,
    "status": "running",
    "message": "Extracting semantic entities (LLM)..."
  }
  ```
The agent prints in-place status updates until the job transitions to `success` or `failed`.

* **Status Completion**: Poll until `status` is `"success"`, `"done"`, or `"complete"`. If status is `"failed"`, halt execution and inspect server logs.

> [!TIP]
> **Poller Performance**: To minimize CLI visual spam, agents should track the status string in memory and print update lines to stdout using `\r` (carriage returns) only when the step, progress, or message changes.

---

### Step C: Fetching Snapshot & Analyzing Existing Test Coverage
Once the codebase is indexed, retrieve the snapshot to review the codebase architecture and check for existing test coverage:
* **Request**:
  ```http
  POST /api/repo/snapshot
  ```
* **Response**:
  ```json
  {
    "total": 3,
    "communities": [
      {
        "id": 4,
        "name": "Billing & Invoicing Services",
        "functions": [
          {
            "name": "process_payment",
            "file": "services/payment.py",
            "has_test": false,
            "priority_score": 8.5
          },
          {
            "name": "get_user",
            "file": "db/users.py",
            "has_test": true,
            "priority_score": 4.1
          }
        ]
      }
    ]
  }
  ```

#### How the Agent Builds the Test Backlog:
1. **Calculate Coverage Baseline**: Count functions where `has_test == true` divided by total functions to compute existing graph-indexed test coverage.
2. **Filter Out Existing Tests**: Exclude any functions where `has_test == true` to avoid duplicating existing test suites.
3. **Sort by Priority**: Sort remaining functions (`has_test == false`) by `priority_score` descending.

The priority score weights coupling, activity, and complexity:
$$\text{Priority Score} = (\text{Complexity} \times 0.3) + (\text{In-Degree Callers} \times 0.4) + (\text{Commit Churn} \times 0.3)$$

---

## 🔌 3. Consuming Context for Test Generation

For each target function in the backlog queue, retrieve the full semantic context required to design high-quality mocks and assert edge cases.

### Requesting Context
```http
GET /api/context/{function_name}
```

### Response Schema:
```json
{
  "function": {
    "name": "process_payment",
    "file": "services/payment.py",
    "class_name": "PaymentService",
    "visibility": "public",
    "is_async": true,
    "complexity": 6,
    "inputs": [
      {"name": "user_id", "type": "str"}, 
      {"name": "amount", "type": "float"}
    ],
    "output": "bool",
    "raises": ["ValueError", "InsufficentFundsError"],
    "annotations": ["@transactional"],
    "docstring": "Executes payments for registered users.",
    "raw_code": "async def process_payment(self, user_id, amount):\n    ...",
    "how_it_works": "Validates user balances and interfaces with external Stripe client.",
    "input_spec": "user_id: Must be valid UUIDv4 string, not nullable. amount: Positive float, minimum 0.50, max 10000.00",
    "output_spec": "Returns True if payment succeeded. Raises InsufficientFundsError if balance too low.",
    "edge_cases": [
      "Negative amount value passed",
      "User ID does not exist in db",
      "Stripe client returns API connection timeout"
    ],
    "test_recommendations": [
      {"type": "mock", "target": "stripe.Charge.create", "reason": "Prevent remote Stripe call"},
      {"type": "test_case", "name": "test_negative_amount", "path": "error", "description": "Verify ValueError is raised if amount <= 0"}
    ]
  },
  "community": {
    "id": 4,
    "name": "Billing & Invoicing Services",
    "summary": "Handles subscription lifecycle, direct charges, and Stripe integrations."
  },
  "calls_outside": [
    {"name": "stripe.Charge.create", "file": "external", "type": "Function"},
    {"name": "check_user_balance", "file": "services/user.py", "type": "Function"}
  ],
  "called_by": [
    {"name": "checkout_cart", "file": "controllers/checkout.py", "type": "Function"}
  ]
}
```

---

## 💾 4. Synchronizing Test Coverage States

To maintain database alignment as the agent creates tests in the local project workspace, synchronize progress back to the server.

### A. Marking a Function as Tested
On writing and successfully verifying a test in the local suite, flag the function as covered:
```http
POST /api/test/done
Content-Type: application/json

{
  "function_name": "process_payment",
  "file": "services/payment.py",
  "status": "pass"
}
```
*This updates the Neo4j graph, setting `has_test = true` on the target function node.*

### B. Finalizing the Run
After finishing the initial backlog iteration, transition the server mode:
```http
POST /api/first_run/complete
Content-Type: application/json

{
  "generated_count": 12
}
```
*This transitions the server from `FIRST_RUN` → `ONGOING`, activating real-time change synchronization hooks.*

---

## 🚀 5. CI/CD Incremental Verification

For ongoing commits in `ONGOING` mode, the agent executes regression testing loops.

1. **Git Update Sync**: The repository webhook triggers `/api/git-sync`, updating the server's graph index in the background.
2. **Query Changes**: The agent requests changes for the current HEAD commit:
   ```http
   GET /api/changes?commit={git_commit_hash}
   ```
3. **Targeted Runs**: The agent retrieves context only for the returned list of `changed_functions` and writes/runs tests, ensuring rapid CI/CD execution times.
