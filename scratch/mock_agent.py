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
        
    return {"status": "ok"}


def call_api(method, endpoint, json_data=None, params=None):
    """Helper to perform requests with error handling and offline fallback."""
    url = f"{API_BASE_URL}{endpoint}"
    offline_mode = False
    
    try:
        if method.upper() == "GET":
            r = requests.get(url, headers=headers, params=params, timeout=5)
        elif method.upper() == "POST":
            r = requests.post(url, headers=headers, json=json_data, timeout=5)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        if r.status_code == 404:
            offline_mode = True
        elif r.status_code == 401:
            print("❌ Authentication failed. Check your API_KEY in .env.")
            sys.exit(1)
        else:
            r.raise_for_status()
            return r.json()
            
    except requests.exceptions.RequestException:
        offline_mode = True
        
    if offline_mode:
        if endpoint == "/api/repo/init":
            print("⚠️  GraphRAG Server not responding or returned 404 at port 8080.")
            print("💡  Switching to OFFLINE MOCK SIMULATION MODE (no server required)...")
            print("--------------------------------------------------")
        return get_mock_response(method, endpoint, json_data, params)

# ─────────────────────────────────────────────────────────────
# Phase 1: Initialize Pipeline and Poll Status
# ─────────────────────────────────────────────────────────────
print("[Phase 1] Initializing codebase analysis...")
init_resp = call_api("POST", "/api/repo/init", {"repo_url": TARGET_REPO_URL})
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
test_queue.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

print(f"✔️ Identified {len(test_queue)} functions lacking tests. Top 5 priority queue:")
for i, f in enumerate(test_queue[:5]):
    print(f"  {i+1}. {f['name']} (File: {f['file']}, Score: {f['priority_score']}, Community: {f['community_name']})")
print("")

# ─────────────────────────────────────────────────────────────
# Phase 3: Retrieve Context and Simulate Test Generation
# ─────────────────────────────────────────────────────────────
print("[Phase 3] Starting mock test generation loop (simulating top 2 functions to save time)...")
processed_count = 0

for func in test_queue[:2]:
    name = func["name"]
    file_path = func["file"]
    print(f"--- Processing Function: {name} ({file_path}) ---")
    
    # Retrieve detailed context (source code, mocks, edge cases, class constructors)
    # Uses 'file' parameter to avoid duplicate namespace conflicts if supported
    params = {"file": file_path}
    context = call_api("GET", f"/api/context/{name}", params=params)
    
    func_detail = context.get("function", {})
    raw_code = func_detail.get("raw_code", "")
    edge_cases = func_detail.get("edge_cases", [])
    recommendations = func_detail.get("test_recommendations", [])
    class_context = context.get("class_context", None)
    
    print(f"  • Source lines: {len(raw_code.splitlines())} lines retrieved.")
    if class_context:
        print(f"  • Class constructor context found for: {class_context.get('class_name')}")
    
    # Analyze outgoing call nodes to identify mock targets
    calls_outside = context.get("calls_outside", [])
    mock_targets = [c["name"] for c in calls_outside]
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
print(f"✔️ First run complete! Server transitioned successfully.")
print(f"Status response: {complete_resp}")
print("\n==================================================")
print("🎉 MOCK AGENT SIMULATION RUN FINISHED SUCCESSFULLY")
print("==================================================")
