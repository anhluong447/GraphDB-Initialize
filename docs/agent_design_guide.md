# Integration Guide: How External Test Agents Consume GraphRAG (Python API)

This guide details the integration architecture, programmatic APIs, and status synchronization flows exposed by the GraphRAG Python module interface (`knowledge_base.py`). It is designed to assist external autonomous test agents in integrating with and consuming the GraphRAG pipeline from separate codebase projects.

---

## 🏗️ 1. Architecture Overview (Direct Python Integration)

The GraphRAG Knowledge Base operates on a direct local import model:
* **GraphRAG Subsystem (Local)**: Housed in the target repository under `graphrag/`. It boots up the dockerized database (Neo4j) and coordinates the AST extraction, LLM semantic enrichment, and community division (ChromaDB runs locally in-process).
* **Test Agent (Client)**: The agent runs locally or in CI/CD within the target project codebase. It imports the python module interface `knowledge_base.py` directly, analyzes the codebase blueprint, and designs/saves tests directly inside the local project files.

```text
  ┌─────────────────────────────────┐
  │         Target Project          │
  │      (Separate Workspace)       │
  │                                 │
  │  Imports knowledge_base.py ───┐ │
  │                               │ │
  │  1. run_init() ◄──────────────┘ │◄── Boots up Docker & runs parsing
  │  2. get_snapshot() ───────────► │◄── Retrieves communities & prioritized functions
  │  3. get_function_context() ───► │◄── Fetches function code, dependencies, & test specs
  │  4. mark_tested() ────────────► │◄── Marks function as tested in Neo4j
  │  5. get_changes() ────────────► │◄── Fetches changed functions for incremental tests
  └─────────────────────────────────┘
```

---

## 🔄 2. Connection, Discovery & Ingestion Flow

When the agent starts up inside a codebase, it must ensure the databases are online and the project has been indexed.

### Step A: Bootstrapping and Ingestion
The agent initializes the GraphRAG pipeline using the python helper `run_init()`:
```python
from knowledge_base import run_init

# Boots up Neo4j container and runs the parsing/enrichment pipeline
run_init()
```
This runs the background thread parser, connects to the local dockerized services, and populates the graph database.

---

### Step B: Fetching Snapshot & Analyzing Existing Test Coverage
Once the codebase is indexed, retrieve the snapshot to review the codebase architecture and check for existing test coverage:
```python
from knowledge_base import get_snapshot

snapshot = get_snapshot()
print(f"Total functions: {snapshot['total']}")
```

#### Response Structure:
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
          "priority_score": 8.5,
          "complexity": 6
        },
        {
          "name": "get_user",
          "file": "db/users.py",
          "has_test": true,
          "priority_score": 4.1,
          "complexity": 2
        }
      ]
    }
  ]
}
```

#### How the Agent Builds the Test Backlog:
1. **Filter Out Existing Tests**: Exclude any functions where `has_test == true` to avoid duplicating existing test suites.
2. **Sort by Priority**: Sort remaining functions (`has_test == false`) by `priority_score` descending.

---

## 🔌 3. Consuming Context for Test Generation

For each target function in the backlog queue, retrieve the full semantic context required to design high-value mocks and assert edge cases.

### Requesting Context
```python
from knowledge_base import get_function_context

ctx = get_function_context("process_payment")
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

To maintain database alignment as the agent creates tests in the local project workspace, synchronize progress back to the graph.

### Marking a Function as Tested
On writing and successfully verifying a test in the local suite, flag the function as covered:
```python
from knowledge_base import mark_tested

mark_tested("process_payment")
```
*This updates the Neo4j graph, setting `has_test = true` on the target function node.*

---

## 🚀 5. CI/CD Incremental Verification

For ongoing commits, the agent executes regression testing loops.

1. **Git Update Sync**: The agent triggers `run_sync()` in its workflow, which runs a quick incremental sync:
   ```python
   from knowledge_base import run_sync
   run_sync()
   ```
2. **Query Changes**: The agent requests changes for the current HEAD commit:
   ```python
   from knowledge_base import get_changes
   
   changes = get_changes("git_commit_hash")
   # Returns lists of changed_functions, affected_services (communities) and risk_level
   ```
3. **Targeted Runs**: The agent retrieves context only for the returned list of `changed_functions` and writes/runs tests, ensuring rapid CI/CD execution times.
