#!/usr/bin/env python3
"""
Mock Test Generation Agent Simulator
-------------------------------------
Simulates how a third-party autonomous test-generation agent integrates
with the GraphRAG REST API to perform test planning, context gathering,
test generation simulation, and coverage synchronization.
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv

# Reconfigure terminal stdout/stderr to UTF-8 on Windows to prevent encoding crashes
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Suppress noisy warnings and logger notifications from the neo4j driver
import logging
import warnings
logging.getLogger("neo4j").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

# Load env variables from root directory
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

# Server configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8080")
API_KEY = os.getenv("API_KEY", "")
TARGET_REPO_URL = os.getenv("CODEBASE_PATH", "../demo-project")

# Headers for API authentication
headers = {
    "Content-Type": "application/json"
}
if API_KEY:
    headers["X-API-Key"] = API_KEY

print("==================================================")
print("🚀 STARTING MOCK TEST GENERATION AGENT SIMULATOR")
print("==================================================")

def start_live_server_if_needed():
    global API_BASE_URL
    # If API_BASE_URL is configured to a remote server, bypass local startup
    if "localhost" not in API_BASE_URL and "127.0.0.1" not in API_BASE_URL:
        print(f"📡 API_BASE_URL is remote: {API_BASE_URL}. Connecting directly without starting local server.\n")
        return
        
    import socket
    import threading
    import time
    
    # Ensure root path is in sys.path
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
        
    # Check if Neo4j is running and has any functions
    cnt = 0
    try:
        from graph.neo4j_client import get_client
        neo4j_client = get_client()
        result = neo4j_client.run("MATCH (f:Function) RETURN count(f) as cnt")
        cnt = result[0]["cnt"] if result else 0
    except Exception as e:
        print(f"ℹ️  Could not query Neo4j database: {e}")
        
    if cnt == 0:
        print("ℹ️  Neo4j database is empty or offline. Falling back to offline simulation.")
        return
        
    print(f"🟢 Found {cnt} pre-indexed functions in the real Neo4j graph database!")
    
    # Check if a server is already listening on port 8080 or if it's occupied
    def find_free_port(start_port=8081):
        port = start_port
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', port)) != 0:
                    return port
                port += 1
                
    port = find_free_port(8081)
    print(f"⚙️  Starting real FastAPI GraphRAG server in a background thread on port {port}...")
    
    # Inject override to skip full LLM processing since the graph is already built
    try:
        import server.pipeline
        import server.state
        
        def mock_run_pipeline_async(repo_url, language=""):
            state = server.state.get_state()
            job_id = "job_real_graph_fast_track"
            state.current_job = {
                "job_id": job_id,
                "status": "success",
                "progress": 100,
                "step": 9,
                "total_steps": 9,
                "message": f"Pipeline complete (fast-tracked: found {cnt} pre-indexed functions)."
            }
            state.set_first_run(total_functions=cnt, codebase_path=repo_url)
            return job_id
            
        server.pipeline.run_pipeline_async = mock_run_pipeline_async
        print("💡  Successfully injected pipeline fast-track (skipping re-indexing since graph exists).")
        
        # Monkeypatch get_client to automatically translate queries
        import graph.neo4j_client
        original_get_client = graph.neo4j_client.get_client
        
        class QueryTranslatingClient:
            def __init__(self, original_client):
                self.original_client = original_client
                
            def run(self, query, params=None):
                # Translate CHANGED to MODIFIED for schema compatibility
                translated_query = query.replace("[:CHANGED]", "[:MODIFIED]")
                return self.original_client.run(translated_query, params)
                
            def __getattr__(self, name):
                return getattr(self.original_client, name)
                
        def wrapped_get_client():
            client = original_get_client()
            return QueryTranslatingClient(client)
            
        graph.neo4j_client.get_client = wrapped_get_client
        print("💡  Successfully injected query translation (mapping :CHANGED to :MODIFIED relationships).")
    except Exception as e:
        print(f"⚠️  Failed to override pipeline/client: {e}")
        
    # Start uvicorn
    def run_uvicorn():
        try:
            import uvicorn
            from server.api import app as server_app
            uvicorn.run(server_app, host="127.0.0.1", port=port, log_level="warning")
        except Exception as e:
            print(f"❌ Background server failed to start: {e}")
            
    t = threading.Thread(target=run_uvicorn, daemon=True)
    t.start()
    
    # Wait for the server to spin up
    print("⏳ Waiting for background API server to start responding...")
    server_ready = False
    for _ in range(30):
        try:
            r = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=0.5, proxies={"http": None, "https": None})
            if r.status_code == 200:
                server_ready = True
                break
        except Exception:
            pass
        time.sleep(0.5)
        
    # Update API_BASE_URL to point to our live local server
    API_BASE_URL = f"http://127.0.0.1:{port}"
    if server_ready:
        print(f"🟢 Real API server is up and responding! API URL updated to: {API_BASE_URL}\n")
    else:
        print(f"⚠️  Real API server did not respond. API URL set to: {API_BASE_URL}\n")

start_live_server_if_needed()

print(f"API Base URL: {API_BASE_URL}")
print(f"Target Repo:  {TARGET_REPO_URL}")
print("==================================================\n")

# Global state for simulating stateful polling in offline mode
_poll_count = 0

def get_mock_response(method, endpoint, json_data=None, params=None):
    """Generates mock JSON responses representing the verified GraphRAG schema."""
    global _poll_count
    
    if endpoint == "/api/repo/init":
        return {"job_id": "job_mock_12345", "status": "queued"}
        
    elif endpoint.startswith("/api/repo/status/"):
        _poll_count += 1
        if _poll_count == 1:
            return {"status": "running", "progress": 25, "step": "2/9", "message": "Parsing AST..."}
        elif _poll_count == 2:
            return {"status": "running", "progress": 65, "step": "6/9", "message": "Enriching with AI..."}
        else:
            return {"status": "success", "progress": 100, "step": "9/9", "message": "Indexing complete."}
            
    elif endpoint == "/api/repo/snapshot":
        return {
            "total": 3,
            "communities": [
                {
                    "id": 4,
                    "name": "Billing & Invoicing Services",
                    "functions": [
                        {
                            "name": "process_payment",
                            "file": "services/payment.py",
                            "has_test": False,
                            "priority_score": 8.5
                        },
                        {
                            "name": "get_user",
                            "file": "db/users.py",
                            "has_test": True,
                            "priority_score": 4.1
                        }
                    ]
                },
                {
                    "id": 5,
                    "name": "Tax Calculations",
                    "functions": [
                        {
                            "name": "calculate_tax",
                            "file": "utils/tax.py",
                            "has_test": False,
                            "priority_score": 6.2
                        }
                    ]
                }
            ]
        }
        
    elif endpoint.startswith("/api/context/"):
        func_name = endpoint.split("/")[-1]
        if func_name == "process_payment":
            return {
                "function": {
                    "name": "process_payment",
                    "file": "services/payment.py",
                    "class_name": "PaymentService",
                    "visibility": "public",
                    "is_async": True,
                    "complexity": 6,
                    "inputs": [
                        {"name": "user_id", "type": "str"},
                        {"name": "amount", "type": "float"}
                    ],
                    "output": "bool",
                    "raises": ["ValueError", "InsufficentFundsError"],
                    "annotations": ["@transactional"],
                    "docstring": "Executes payments for registered users.",
                    "raw_code": "async def process_payment(self, user_id, amount):\n    # Core payment logic\n    pass",
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
        else:  # calculate_tax
            return {
                "function": {
                    "name": "calculate_tax",
                    "file": "utils/tax.py",
                    "class_name": None,
                    "visibility": "public",
                    "is_async": False,
                    "complexity": 3,
                    "inputs": [
                        {"name": "amount", "type": "float"},
                        {"name": "state", "type": "str"}
                    ],
                    "output": "float",
                    "raises": ["ValueError"],
                    "annotations": [],
                    "docstring": "Calculates sales tax based on state jurisdiction.",
                    "raw_code": "def calculate_tax(amount, state):\n    # Tax computation logic\n    pass",
                    "how_it_works": "Applies percentage matching the state lookup table.",
                    "input_spec": "amount: positive float. state: two-letter state code.",
                    "output_spec": "returns tax rate amount as float.",
                    "edge_cases": [
                        "Invalid state code",
                        "Negative amount"
                    ],
                    "test_recommendations": [
                        {"type": "test_case", "name": "test_invalid_state", "path": "error", "description": "Verify ValueError on invalid state code"}
                    ]
                },
                "community": {
                    "id": 5,
                    "name": "Tax Calculations",
                    "summary": "Calculates sales tax and jurisdiction overrides."
                },
                "calls_outside": [
                    {"name": "get_state_tax_rate", "file": "db/tax_rates.py", "type": "Function"}
                ],
                "called_by": [
                    {"name": "process_payment", "file": "services/payment.py", "type": "Function"}
                ]
            }
            
    elif endpoint == "/api/test/done":
        return {"status": "updated", "has_test": True}
        
    elif endpoint == "/api/first_run/complete":
        return {"status": "transitioned", "mode": "ONGOING"}

    elif endpoint == "/api/git-sync":
        return {"status": "sync_started", "codebase_path": TARGET_REPO_URL}

    elif endpoint.startswith("/api/changes"):
        return {
            "commit": "a1b2c3d",
            "changed_functions": [
                {
                    "name": "calculate_tax",
                    "file": "utils/tax.py",
                    "class_name": None,
                    "complexity": 3,
                    "has_test": False
                }
            ],
            "affected_services": [
                {"id": 5, "name": "Tax Calculations"}
            ],
            "risk_level": "high"
        }
        
    return {"status": "ok"}


def get_valid_commit_hash(repo_path):
    """Retrieves the actual HEAD commit hash of the target repository if available."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception:
        return "a1b2c3d"


_offline_mode = None

def call_api(method, endpoint, json_data=None, params=None):
    """Helper to perform requests with error handling, retries, and offline fallback."""
    global _offline_mode
    url = f"{API_BASE_URL}{endpoint}"
    
    # If already determined to be offline, return mock response directly
    if _offline_mode is True:
        return get_mock_response(method, endpoint, json_data, params)
        
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if method.upper() == "GET":
                r = requests.get(url, headers=headers, params=params, timeout=10)
            elif method.upper() == "POST":
                r = requests.post(url, headers=headers, json=json_data, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # Check authorization failure first
            if r.status_code == 401:
                print("❌ Authentication failed. Check your API_KEY in .env.")
                sys.exit(1)
                
            if r.status_code == 409:
                return {"status": "conflict", "detail": "A pipeline job is already running."}
                
            if r.status_code == 400:
                try:
                    err_data = r.json()
                    if "not in FIRST_RUN mode" in err_data.get("detail", ""):
                        return {"status": "already_completed", "detail": err_data.get("detail")}
                except Exception:
                    pass

            # Determine mode on the first call to the server
            if _offline_mode is None:
                if r.status_code == 404:
                    _offline_mode = True
                    print("⚠️  GraphRAG Server returned 404 on init. Visualizer backend might be running on this port.")
                    print("💡  Switching to OFFLINE MOCK SIMULATION MODE (no server required)...")
                    print("--------------------------------------------------")
                    return get_mock_response(method, endpoint, json_data, params)
                else:
                    _offline_mode = False
                    print("🟢 Connected to live GraphRAG Server. Running in ONLINE mode.")
                    print("--------------------------------------------------")
                    
            r.raise_for_status()
            return r.json()
            
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            # If we haven't determined the mode yet, fallback to offline on the first failure
            if _offline_mode is None:
                _offline_mode = True
                print(f"⚠️  GraphRAG Server not responding. Error details: {e}")
                print("💡  Switching to OFFLINE MOCK SIMULATION MODE (no server required)...")
                print("--------------------------------------------------")
                return get_mock_response(method, endpoint, json_data, params)
            
            # Otherwise, if we are in online mode, retry on transient network errors
            if attempt < max_retries - 1:
                print(f"⚠️  Transient network error on {endpoint}: {e}. Retrying in 3 seconds (attempt {attempt + 2}/{max_retries})...")
                time.sleep(3)
            else:
                print(f"❌ API Call to {endpoint} failed after {max_retries} attempts: {e}")
                sys.exit(1)
        except requests.exceptions.RequestException as e:
            # For other HTTP/Request errors, fail immediately or fallback
            if _offline_mode is None:
                _offline_mode = True
                print(f"⚠️  GraphRAG Server not responding. Error details: {e}")
                print("💡  Switching to OFFLINE MOCK SIMULATION MODE (no server required)...")
                print("--------------------------------------------------")
                return get_mock_response(method, endpoint, json_data, params)
            else:
                print(f"❌ API Call to {endpoint} failed: {e}")
                sys.exit(1)

# ─────────────────────────────────────────────────────────────
# Phase 1: Initialize Pipeline and Poll Status
# ─────────────────────────────────────────────────────────────
print("[Phase 1] Initializing codebase analysis...")
init_resp = call_api("POST", "/api/repo/init", {"repo_url": TARGET_REPO_URL})
if isinstance(init_resp, dict) and init_resp.get("status") == "conflict":
    print("⚠️  A codebase analysis pipeline is already running on the server.")
    print("📡 Querying server health to find the active job...")
    health_resp = call_api("GET", "/api/health")
    current_job = health_resp.get("current_job")
    if current_job and current_job.get("job_id"):
        job_id = current_job["job_id"]
        print(f"✔️ Connected to active job: {job_id}")
    else:
        print("❌ Could not retrieve active job ID. Exiting.")
        sys.exit(1)
else:
    job_id = init_resp.get("job_id")
    print(f"✔️ Analysis job queued successfully. Job ID: {job_id}")

print("Polling analysis status...")
while True:
    status_resp = call_api("GET", f"/api/repo/status/{job_id}")
    progress = status_resp.get("progress", 0)
    step = status_resp.get("step", "?/?")
    msg = status_resp.get("message", "")
    status = status_resp.get("status", "running")
    
    print(f"  └─► Progress: {progress}% | Step: {step} | Current: {msg}")
    
    if status in ("success", "done", "complete"):
        print("✔️ Codebase analysis complete!\n")
        break
    elif status == "failed":
        print("❌ Codebase analysis pipeline failed.")
        sys.exit(1)
    
    time.sleep(3)

# ─────────────────────────────────────────────────────────────
# Phase 2: Fetch Codebase Snapshot and Build Queue
# ─────────────────────────────────────────────────────────────
print("[Phase 2] Fetching codebase snapshot for test planning...")
snapshot = call_api("POST", "/api/repo/snapshot")
total_functions = snapshot.get("total", 0)
communities = snapshot.get("communities", [])

print(f"✔️ Found {total_functions} functions across {len(communities)} communities.")

# Build testing queue: find functions that do not have tests yet, sorted by priority_score
test_queue = []
for comm in communities:
    comm_name = comm.get("name", "Uncategorized")
    for func in comm.get("functions", []):
        if not func.get("has_test", False):
            # Keep track of community context along with function data
            func["community_name"] = comm_name
            test_queue.append(func)

# Sort queue globally by priority_score descending (highest risk/coupling first)
test_queue.sort(key=lambda x: x.get("priority_score") if x.get("priority_score") is not None else 0, reverse=True)

print(f"✔️ Identified {len(test_queue)} functions lacking tests queue:")
for i, f in enumerate(test_queue):
    score_val = f.get('priority_score')
    score_display = score_val if score_val is not None else 0
    print(f"  {i+1}. {f['name']} (File: {f['file']}, Score: {score_display}, Community: {f['community_name']})")
print("")

# ─────────────────────────────────────────────────────────────
# Phase 3: Retrieve Context and Simulate Test Generation
# ─────────────────────────────────────────────────────────────
print("[Phase 3] Starting mock test generation loop...")
processed_count = 0

for func in test_queue[:2]:
    name = func["name"]
    file_path = func["file"]
    print(f"--- Processing Function: {name} ({file_path}) ---")
    
    # Retrieve detailed context (source code, mocks, edge cases, class constructors)
    # Uses 'file' parameter to avoid duplicate namespace conflicts if supported
    params = {"file": file_path}
    context = call_api("GET", f"/api/context/{name}", params=params)
    
    func_detail = context.get("function", {}) or {}
    raw_code = func_detail.get("raw_code", "") or ""
    edge_cases = func_detail.get("edge_cases", []) or []
    recommendations = func_detail.get("test_recommendations", []) or []
    class_context = context.get("class_context", None)
    
    print(f"  • Source lines: {len(raw_code.splitlines())} lines retrieved.")
    if class_context:
        print(f"  • Class constructor context found for: {class_context.get('class_name')}")
    
    # Analyze outgoing call nodes to identify mock targets
    calls_outside = context.get("calls_outside", []) or []
    mock_targets = [c.get("name") for c in calls_outside if isinstance(c, dict) and c.get("name")]
    print(f"  • Dependencies to mock: {mock_targets or 'None'}")
    
    # Simulate LLM test design
    print("  • Designing mock assertions for edge cases:")
    for case in edge_cases[:2]:
         print(f"    ├─► Scenario: {case}")
         
    # Mocking recommendations
    for rec in recommendations[:2]:
        if rec.get("type") == "mock":
            print(f"    ├─► Mock Action: Mock {rec.get('target')} - Reason: {rec.get('reason')}")
        elif rec.get("type") == "test_case":
            print(f"    ├─► Test Scenario: {rec.get('name')} ({rec.get('path')} path)")
            
    print("  ⚙️ Simulating unit test compilation...")
    time.sleep(1) # Simulating code generation delay
    
    # Simulated Generated Python Unit Test Case
    mock_generated_test = f"""
import unittest
from unittest.mock import patch
from {file_path.replace('.py', '').replace('/', '.')} import {name}

class Test{name.title()}(unittest.TestCase):
    def test_happy_path(self):
        # Simulated test case based on GraphRAG edge cases and specs
        pass
"""
    print("  ✔️ Test case generated successfully.")
    
    # Simulate executing the test suite locally
    print("  🧪 Running test suite in local sandbox...")
    time.sleep(1)
    print("  ✔️ Test Execution: PASS (100% assertions satisfied)")
    
    # Update GraphRAG database of completed status
    done_payload = {
        "function_name": name,
        "file": file_path,
        "status": "pass"
    }
    call_api("POST", "/api/test/done", done_payload)
    print(f"  ✔️ Sent /api/test/done confirmation to server.")
    processed_count += 1
    print("--------------------------------------------------\n")

# ─────────────────────────────────────────────────────────────
# Phase 4: Finalize Run and Transition Server Mode
# ─────────────────────────────────────────────────────────────
print("[Phase 4] Finalizing the mock agent test run...")
complete_payload = {
    "generated_count": processed_count
}
complete_resp = call_api("POST", "/api/first_run/complete", complete_payload)
if isinstance(complete_resp, dict) and complete_resp.get("status") == "already_completed":
    print("💡  Server is already in ONGOING mode (transition previously completed).\n")
else:
    print(f"✔️ First run complete! Server transitioned successfully.")
    print(f"Status response: {complete_resp}\n")

# ─────────────────────────────────────────────────────────────
# Phase 5: Ongoing Sync and Change Detection (CI/CD Webhook & Regression Testing)
# ─────────────────────────────────────────────────────────────
print("[Phase 5] Simulating ongoing git-sync updates and impact analysis (CI/CD)...")

# 1. Trigger Git push sync webhook
print("  • Simulating repo git-sync push webhook trigger...")
sync_payload = {
    "ref": "refs/heads/main",
    "after": "a1b2c3d4e5f6g7h8i9j0"
}
sync_resp = call_api("POST", "/api/git-sync", sync_payload)
print(f"  ✔️ Webhook sync status: {sync_resp.get('status')}")

# 2. Query changes for specific commit hash
commit_hash = get_valid_commit_hash(TARGET_REPO_URL) if not _offline_mode else "a1b2c3d"
print(f"  • Retrieving impacted functions for commit: {commit_hash}...")
changes_resp = call_api("GET", "/api/changes", params={"commit": commit_hash})
changes = changes_resp.get("changed_functions", [])
risk_level = changes_resp.get("risk_level", "low")
print(f"  ✔️ Commit Risk Level: {risk_level.upper()}")
print(f"  ✔️ Found {len(changes)} modified function(s) in this commit.")

if not changes and not _offline_mode:
    print("  💡 (Skipping regression test loop since no functions were modified in the live HEAD commit.)")

# 3. Process changed functions (impact analysis regression testing)
for change in changes:
    name = change["name"]
    file_path = change["file"]
    ctype = "modified"
    
    print(f"    ├─► Impacted Function: {name} | File: {file_path} | Change: {ctype} | Risk: {risk_level.upper()}")
    
    # Query updated context
    print(f"    │   └─► Fetching updated context for: {name}...")
    context = call_api("GET", f"/api/context/{name}", params={"file": file_path})
    func_detail = context.get("function", {})
    
    # Simulate test regeneration / rerun
    print("    │   └─► Running updated regression test suite...")
    time.sleep(1)
    print("    │   └─► Regression Test Execution: PASS")
    
    # Sync status
    done_payload = {
        "function_name": name,
        "file": file_path,
        "status": "pass"
    }
    call_api("POST", "/api/test/done", done_payload)
    print("    │   └─► /api/test/done synced successfully.")

print("\n==================================================")
print("🎉 MOCK AGENT SIMULATION RUN FINISHED SUCCESSFULLY")
print("==================================================")
