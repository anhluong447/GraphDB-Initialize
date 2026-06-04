# Integration Guide: How External Test Agents Consume GraphRAG

This guide describes the API protocols, data contracts, and status synchronization flows exposed by the GraphRAG Knowledge Base server. It is designed to help external testing agents integrate with and consume this project effectively.

---

## 🔄 1. Codebase Ingestion & Status Tracking

Before generating tests, the agent must trigger the ingestion pipeline and verify that database indexing is complete.

```text
[Step 1] POST /api/repo/init ──────► Triggers async parsing pipeline
  │
  ▼ (Loop/Poll)
[Step 2] GET /api/repo/status ────► Checks progress until status is "complete"
```

### A. Initiating Ingestion
Send a `POST` request to `/api/repo/init` to boot Neo4j and ChromaDB, clone the repository (if remote), and trigger the 9-step AST parsing and AI-enrichment pipeline:
* **Payload**:
  ```json
  {
    "repo_url": "/path/to/local/codebase",
    "language": "python"
  }
  ```
* **Response**: Returns a `job_id` to poll.

### B. Tracking Progress
Poll `GET /api/repo/status/{job_id}` to ensure the databases are fully synchronized before requesting context.
* **Key fields to monitor**:
  * `status`: Wait for `"success"` or `"complete"`.
  * `progress`: Integer representing progress percentage (`0` to `100`).
  * `step`: Tracks the current step of ingestion (e.g., `"8/9"`).

---

## 📊 2. Codebase Discovery & Test Prioritization

To map out a test-generation roadmap, the agent queries the codebase snapshot.

### Ingesting the Blueprint
Call `POST /api/repo/snapshot` to retrieve all parsed functions grouped by their semantic module (Community).

### How to use the Snapshot Payload:
* **Skip Completed Tests**: Filter the list to identify functions where `has_test == false`.
* **Prioritize High-Risk Code**: Use the `priority_score` attribute (provided for every function node) to sort your testing queue. This score is dynamically computed based on:
  $$\text{Priority Score} = (\text{Complexity} \times 0.3) + (\text{In-Degree Callers} \times 0.4) + (\text{Commit Churn} \times 0.3)$$
  Targeting functions with higher priority scores ensures that highly-coupled, complex, and active functions are tested first.

---

## 🔌 3. Consuming Context for Test Generation

For each function in the queue, call `GET /api/context/{function_name}` to fetch the context needed for test generation. If your server is configured with namespace collision support, always pass the query parameter `?file={file_path}` to isolate the exact function.

### A. The Context JSON Payload Schema (Current Release)
Below is the exact JSON structure returned by the server at runtime for `/api/context/{function_name}`.

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

> [!NOTE]
> **Proposed Schema Additions:** The `class_context` block (which contains constructor signatures and codes for object methods) is currently part of the **API Gap Fix Plan** and is not present in the default response payload.

---

### B. Detailed Field Mappings & Implementation Guidelines

#### 1. Code Target & Class Instantiation (`raw_code` & `class_name`)
* **Target Code**: The `function.raw_code` contains the exact source string of the function under test.
* **Instantiating the Class Instance**: 
  * If `function.class_name` is populated, the target function is a method on an object.
  * In the current release, constructor signatures (e.g. `__init__`) must be resolved by the agent querying the constructor code directly or matching files. Once the **Gap 2 API Fix** is deployed, constructor parameters will be served inside a root `class_context` object.
  * Once resolved, generate a class instantiation block (e.g. `service = PaymentService(mock_db)`) prior to calling the target method (`service.process_payment(...)`).

#### 2. Designing Mock Patches (`calls_outside` & `test_recommendations`)
* **Automatic Mock Discovery**: Combine the explicit call dependencies in `calls_outside` with `test_recommendations`.
* **Identifying Mock Targets**: 
  * Parse items in `calls_outside` where the `file` is `"external"` or a different internal path. These represent external integrations (e.g. Stripe, AWS S3) or separate services.
  * Check the `test_recommendations` list where `"type": "mock"`. This tells the agent exactly what path to mock (e.g., `stripe.Charge.create`) and the technical rationale (e.g., `"Prevent remote Stripe call"`).
* **Mock Context Application**: Use the mock targets to generate patch decorators (like `@patch('stripe.Charge.create')` in Python or `jest.mock(...)` in JavaScript) to ensure unit tests run in isolation without network hits.

#### 3. Happy and Exception Flow Assertions (`input_spec`, `output_spec`, & `raises`)
* **Happy Path**: Use the `inputs` signature and the `input_spec` ranges to feed valid, representative inputs to the function. Assert that the returned value matches the expectations detailed in `output_spec`.
* **Exception Testing**: Inspect the `raises` list (e.g. `["ValueError", "InsufficentFundsError"]`). Generate test cases designed to trigger these specific errors and assert that the expected exception is raised.

#### 4. Boundary Analysis (`edge_cases` & `test_recommendations`)
* **Scenarios to Cover**: The `edge_cases` array holds pre-analyzed high-risk states. The agent should write a dedicated test function for each element in this array.
* **Pre-structured Test Recommendations**: Inspect the `test_recommendations` array where `"type": "test_case"`. The agent can copy the `name` (e.g. `test_negative_amount`), classification `path` (e.g. `error` or `edge`), and standard behavior `description` directly into the test suite.

#### 5. Integration Verification (`called_by` & `community`)
* **Usage Inspiration**: The `called_by` list identifies real-world callers of the target function. The agent can use this to understand what parameters are normally passed and what return structures callers expect.
* **Architectural Context**: Use the `community.summary` to populate the agent's LLM system prompt. For instance, knowing that the class belongs to "Billing & Invoicing Services" helps the LLM generate realistic mock objects (e.g., invoices, transaction IDs) rather than generic strings.


---

## 💾 4. Synchronizing Test Coverage States

To keep the GraphRAG database in sync with your test suite, report results back to the server:

### A. Updating Coverage Status
Once the agent successfully writes and compiles a passing unit test for a function, send a `POST` request to `/api/test/done`.
* **Payload**:
  ```json
  {
    "function_name": "process_payment",
    "file": "services/payment.py",
    "status": "pass"
  }
  ```
This flags `has_test = true` on the Function node in Neo4j. In subsequent snapshot calls, this function will be excluded or marked as covered.

### B. Closing the Session
When the initial codebase coverage run is finished, trigger `POST /api/first_run/complete`.
* **Payload**:
  ```json
  {
    "generated_count": 14
  }
  ```
This transitions the GraphRAG database from `FIRST_RUN` mode to `ONGOING` mode, enabling automatic incremental syncs on new commits.

---

## 🚀 5. Ongoing Ingestion & Change Detection (CI/CD)

For ongoing test runs (e.g., triggered by PR checks or CI/CD pipelines), use the change detection endpoints.

### A. Automated Updates
Configure a webhook in your repository provider (GitHub/GitLab) pointing to `/api/git-sync`. Upon every push event, this endpoint automatically pulls the latest commits and updates AST structures in the background.

### B. Targeting Changed Code
To run regression testing, call `GET /api/changes?commit={git_commit_hash}`.
* **Returned Data**: A list of changed functions, their modified file paths, and their calculated `risk_level` (low, medium, high).
* **Usage**: Iterate only over the list of changed functions to update or write tests, keeping your PR verification run fast and targeted.
