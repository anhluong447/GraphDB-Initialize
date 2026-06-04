"""
Knowledge Base API Server — REST API endpoints per DA01 Workflow Design.

Exposes all endpoints for Auto-Test Agent integration:
- Repo initialization and pipeline status tracking
- Codebase snapshot with priority scoring
- Function context retrieval with full subgraph
- Git sync webhook for incremental updates
- Test result tracking (has_test flag)

API Key authentication is enforced via X-API-Key header when API_KEY is set.
"""

import sys
import os
import json
import threading

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from config import API_KEY
from server.state import get_state, MODE_IDLE, MODE_FIRST_RUN, MODE_ONGOING


# ═══════════════════════════════════════════════════════════
# App & Middleware
# ═══════════════════════════════════════════════════════════

app = FastAPI(
    title="GraphRAG Knowledge Base Server",
    description="REST API server exposing GraphDB for Auto-Test Agents",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════
# API Key Authentication Middleware
# ═══════════════════════════════════════════════════════════

@app.middleware("http")
async def authenticate(request: Request, call_next):
    """Check X-API-Key header on all endpoints except /api/health."""
    # Skip auth for health check and docs
    if request.url.path in ("/api/health", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)

    # Skip auth if no API_KEY configured (dev mode)
    if not API_KEY:
        return await call_next(request)

    # Validate API key
    provided_key = request.headers.get("X-API-Key", "")
    if provided_key != API_KEY:
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized. Provide a valid X-API-Key header."},
        )

    return await call_next(request)


# ═══════════════════════════════════════════════════════════
# Request/Response Models
# ═══════════════════════════════════════════════════════════

class RepoInitRequest(BaseModel):
    repo_url: str
    language: Optional[str] = ""

class FirstRunCompleteRequest(BaseModel):
    generated_count: int

class TestDoneRequest(BaseModel):
    function_name: str
    file: Optional[str] = None
    status: Optional[str] = "pass"


# ═══════════════════════════════════════════════════════════
# FIRST_RUN Endpoints
# ═══════════════════════════════════════════════════════════

@app.post("/api/repo/init")
def repo_init(req: RepoInitRequest):
    """
    Initialize the pipeline for a codebase.
    Clones repo (if remote URL) and starts the 9-step pipeline asynchronously.
    Returns a job_id for status polling.
    """
    from server.pipeline import run_pipeline_async

    try:
        job_id = run_pipeline_async(repo_url=req.repo_url, language=req.language or "")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"job_id": job_id, "status": "queued"}


@app.get("/api/repo/status/{job_id}")
def repo_status(job_id: str):
    """
    Poll pipeline progress.
    Returns step number, progress percentage, and current message.
    """
    state = get_state()
    job = state.get_job_status(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job["job_id"],
        "step": f"{job['step']}/{job['total_steps']}",
        "progress": job["progress"],
        "status": job["status"],
        "message": job["message"],
    }


@app.post("/api/repo/snapshot")
def repo_snapshot():
    """
    Return the full codebase snapshot grouped by community with priority scores.
    Each function includes a priority_score computed from:
    - complexity (weight 0.3)
    - in_degree: how many other functions call it (weight 0.4)
    - commit_count: how often it's been changed (weight 0.3)
    """
    from graph.neo4j_client import get_client
    client = get_client()

    # Fetch all functions with their community info
    functions = client.run("""
        MATCH (f:Function)
        WHERE f.file IS NOT NULL AND f.name IS NOT NULL
        OPTIONAL MATCH (f)-[:BELONGS_TO]->(c:Community)
        OPTIONAL MATCH ()-[:CALLS]->(f)
        WITH f, c,
             count(DISTINCT c) as _,
             f.complexity as complexity
        OPTIONAL MATCH (caller:Function)-[:CALLS]->(f)
        WITH f, c, complexity, count(DISTINCT caller) as in_degree
        OPTIONAL MATCH (commit:Commit)-[:CHANGED]->(f)
        WITH f, c, complexity, in_degree, count(DISTINCT commit) as commit_count
        RETURN f.name as name,
               f.file as file,
               f.class_name as class_name,
               coalesce(f.complexity, 1) as complexity,
               in_degree,
               commit_count,
               coalesce(f.has_test, false) as has_test,
               c.id as community_id,
               c.name as community_name,
               c.summary as community_summary
        ORDER BY community_id, name
    """)

    # Group by community and compute priority scores
    communities_map = {}
    uncategorized = {"id": -1, "name": "Uncategorized", "summary": "", "functions": []}

    for r in functions:
        complexity = r["complexity"] or 1
        in_degree = r["in_degree"] or 0
        commit_count = r["commit_count"] or 0
        priority_score = round(complexity * 0.3 + in_degree * 0.4 + commit_count * 0.3, 1)

        func_data = {
            "name": r["name"],
            "file": r["file"],
            "class_name": r["class_name"],
            "complexity": complexity,
            "priority_score": priority_score,
            "has_test": r["has_test"] or False,
        }

        cid = r["community_id"]
        if cid is not None:
            if cid not in communities_map:
                communities_map[cid] = {
                    "id": cid,
                    "name": r["community_name"] or f"Community {cid}",
                    "summary": r["community_summary"] or "",
                    "functions": [],
                }
            communities_map[cid]["functions"].append(func_data)
        else:
            uncategorized["functions"].append(func_data)

    # Sort functions by priority within each community
    for comm in communities_map.values():
        comm["functions"].sort(key=lambda f: f["priority_score"], reverse=True)
    uncategorized["functions"].sort(key=lambda f: f["priority_score"], reverse=True)

    communities_list = sorted(communities_map.values(), key=lambda c: c["id"])
    if uncategorized["functions"]:
        communities_list.append(uncategorized)

    total = sum(len(c["functions"]) for c in communities_list)

    return {
        "total": total,
        "communities": communities_list,
    }


# ═══════════════════════════════════════════════════════════
# Transition Endpoint
# ═══════════════════════════════════════════════════════════

@app.post("/api/first_run/complete")
def first_run_complete(req: FirstRunCompleteRequest):
    """
    Signal that the Auto-Test Agent has finished generating tests
    for all functions. Transitions server from FIRST_RUN → ONGOING
    and flushes any queued commit webhooks.
    """
    state = get_state()

    if state.mode != MODE_FIRST_RUN:
        raise HTTPException(
            status_code=400,
            detail=f"Server is not in FIRST_RUN mode (current: {state.mode}). "
                   f"This endpoint is only valid during FIRST_RUN.",
        )

    result = state.complete_first_run(generated_count=req.generated_count)
    return result


# ═══════════════════════════════════════════════════════════
# ONGOING Endpoints
# ═══════════════════════════════════════════════════════════

@app.get("/api/changes")
def get_changes(commit: str):
    """
    Get the list of functions changed by a specific commit.
    Returns function names, files, and the commit's risk level.
    """
    from graph.neo4j_client import get_client
    client = get_client()

    # Find functions changed by this commit
    result = client.run("""
        MATCH (c:Commit)-[:CHANGED]->(f:Function)
        WHERE c.hash STARTS WITH $hash
        RETURN f.name as name,
               f.file as file,
               f.class_name as class_name,
               coalesce(f.complexity, 1) as complexity,
               coalesce(f.has_test, false) as has_test
    """, {"hash": commit})

    if not result:
        # Try matching commit by full hash
        result = client.run("""
            MATCH (c:Commit)-[:CHANGED]->(f:Function)
            WHERE c.hash = $hash
            RETURN f.name as name,
                   f.file as file,
                   f.class_name as class_name,
                   coalesce(f.complexity, 1) as complexity,
                   coalesce(f.has_test, false) as has_test
        """, {"hash": commit})

    changed_functions = [dict(r) for r in result]

    # Compute risk level
    max_complexity = max((f["complexity"] for f in changed_functions), default=1)
    risk_level = "low"
    if max_complexity >= 10:
        risk_level = "high"
    elif max_complexity >= 5:
        risk_level = "medium"

    # Get affected services/communities
    affected_communities = []
    if changed_functions:
        names = [f["name"] for f in changed_functions]
        comm_result = client.run("""
            MATCH (f:Function)-[:BELONGS_TO]->(c:Community)
            WHERE f.name IN $names
            RETURN DISTINCT c.id as id, c.name as name
        """, {"names": names})
        affected_communities = [dict(r) for r in comm_result]

    return {
        "commit": commit,
        "changed_functions": changed_functions,
        "affected_services": affected_communities,
        "risk_level": risk_level,
    }


# ═══════════════════════════════════════════════════════════
# Shared Endpoints (BOTH modes)
# ═══════════════════════════════════════════════════════════

@app.get("/api/context/{name}")
def get_context(name: str):
    """
    Get full subgraph context for a single function.
    Returns: function details (with source code and test specs),
    community info, outgoing calls, and incoming callers.
    """
    from graph.neo4j_client import get_client
    client = get_client()

    # Get function node
    result = client.run("""
        MATCH (f:Function {name: $name})
        OPTIONAL MATCH (f)-[:BELONGS_TO]->(c:Community)
        RETURN f, c.id as community_id, c.name as community_name, c.summary as community_summary
        LIMIT 1
    """, {"name": name})

    if not result:
        raise HTTPException(status_code=404, detail=f"Function '{name}' not found")

    record = result[0]
    func_data = dict(record["f"])

    # Read source code dynamically
    func_data["raw_code"] = client.read_node_code(func_data)

    # Parse JSON fields for cleaner output
    for json_field in ["edge_cases", "test_recommendations", "inputs", "raises", "annotations"]:
        val = func_data.get(json_field)
        if isinstance(val, str):
            try:
                func_data[json_field] = json.loads(val)
            except Exception:
                pass

    # Community info
    community = None
    if record["community_id"] is not None:
        community = {
            "id": record["community_id"],
            "name": record["community_name"],
            "summary": record["community_summary"],
        }

    # Outgoing calls (functions this function calls)
    calls_outside = client.run("""
        MATCH (f:Function {name: $name})-[:CALLS]->(callee)
        WHERE callee.name IS NOT NULL
        RETURN callee.name as name,
               callee.file as file,
               labels(callee)[0] as type
    """, {"name": name})

    # Incoming callers (functions that call this function)
    called_by = client.run("""
        MATCH (caller)-[:CALLS]->(f:Function {name: $name})
        WHERE caller.name IS NOT NULL
        RETURN caller.name as name,
               caller.file as file,
               labels(caller)[0] as type
    """, {"name": name})

    return {
        "function": func_data,
        "community": community,
        "calls_outside": [dict(r) for r in calls_outside],
        "called_by": [dict(r) for r in called_by],
    }


@app.get("/api/functions")
def list_functions(has_test: Optional[bool] = None, limit: int = 500):
    """
    List all indexed functions with optional filtering.
    """
    from graph.neo4j_client import get_client
    client = get_client()

    where_clause = ""
    if has_test is True:
        where_clause = "AND f.has_test = true"
    elif has_test is False:
        where_clause = "AND (f.has_test IS NULL OR f.has_test = false)"

    result = client.run(f"""
        MATCH (f:Function)
        WHERE f.file IS NOT NULL {where_clause}
        RETURN f.name as name,
               f.file as file,
               f.class_name as class_name,
               coalesce(f.complexity, 1) as complexity,
               coalesce(f.has_test, false) as has_test,
               f.how_it_works as how_it_works
        ORDER BY f.name
        LIMIT $limit
    """, {"limit": limit})

    return [dict(r) for r in result]


@app.get("/api/health")
def health_check():
    """
    Server health check — no auth required.
    Returns server mode, DB connectivity, and job status.
    """
    state = get_state()
    health = state.get_health()

    # Check Neo4j connectivity (with timeout to avoid hanging)
    neo4j_status = {"result": "timeout"}
    def _check_neo4j():
        try:
            from neo4j import GraphDatabase
            from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                session.run("RETURN 1").single()
            driver.close()
            neo4j_status["result"] = "connected"
        except Exception as e:
            neo4j_status["result"] = f"error: {str(e)}"

    check_thread = threading.Thread(target=_check_neo4j, daemon=True)
    check_thread.start()
    check_thread.join(timeout=3)
    health["neo4j"] = neo4j_status["result"]

    return health


@app.post("/api/test/done")
def test_done(req: TestDoneRequest):
    """
    Mark a function as tested (has_test = true) in Neo4j.
    Called by Auto-Test Agent after successfully generating and passing tests.
    """
    from graph.neo4j_client import get_client
    client = get_client()

    if req.file:
        result = client.run("""
            MATCH (f:Function {name: $name, file: $file})
            SET f.has_test = true
            RETURN f.name as name
        """, {"name": req.function_name, "file": req.file})
    else:
        result = client.run("""
            MATCH (f:Function {name: $name})
            SET f.has_test = true
            RETURN f.name as name
        """, {"name": req.function_name})

    if not result:
        raise HTTPException(status_code=404, detail=f"Function '{req.function_name}' not found")

    return {"status": "ok", "function": req.function_name, "has_test": True}


# ═══════════════════════════════════════════════════════════
# Git Sync Webhook
# ═══════════════════════════════════════════════════════════

@app.post("/api/git-sync")
def git_sync(background_tasks: BackgroundTasks):
    """
    Webhook endpoint for GitHub/GitLab push events.
    Triggers an incremental sync in the background.
    """
    state = get_state()

    if not state.codebase_path:
        raise HTTPException(
            status_code=400,
            detail="No codebase has been initialized yet. Use /api/repo/init first.",
        )

    # Run sync in background to not block the webhook response
    from server.pipeline import run_git_sync
    background_tasks.add_task(run_git_sync, state.codebase_path)

    return {"status": "sync_started", "codebase_path": state.codebase_path}


# ═══════════════════════════════════════════════════════════
# Visualization API (backward-compatible mount)
# ═══════════════════════════════════════════════════════════

# Import and mount the existing visualization API under /viz prefix
try:
    from visualization.backend.api import app as viz_app

    @app.get("/viz/graph/full")
    def viz_graph_full(limit: int = 200):
        """Proxy to visualization full graph."""
        from visualization.backend.api import get_full_graph
        return get_full_graph(limit)

    @app.get("/viz/communities")
    def viz_communities():
        """Proxy to visualization communities."""
        from visualization.backend.api import get_communities
        return get_communities()

    @app.get("/viz/graph/search")
    def viz_search(q: str, limit: int = 20):
        """Proxy to visualization search."""
        from visualization.backend.api import search_nodes
        return search_nodes(q, limit)

except ImportError:
    pass  # Visualization module not available
