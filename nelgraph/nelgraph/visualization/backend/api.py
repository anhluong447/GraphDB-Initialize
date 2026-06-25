import sys
import os
import json
import threading

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from nelgraph.graph.neo4j_client import get_client
from nelgraph.query.engine import query, get_node_detail, list_open_tasks
from nelgraph.config import PROJECT_NAME, CODEBASE_PATH, SYNC_STATE_PATH, GRAPHRAG_DATA_DIR

# Set up logging to file in .graphrag_data and standard output
os.makedirs(GRAPHRAG_DATA_DIR, exist_ok=True)
log_file = os.path.join(GRAPHRAG_DATA_DIR, "viz.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("nelgraph.viz")
logger.info(f"Starting visualization API for project '{PROJECT_NAME}' at '{CODEBASE_PATH}'")
logger.info(f"Session logs will be saved to '{log_file}'")

app = FastAPI(title="GraphRAG Visualization API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class FrontendLog(BaseModel):
    level: str
    message: str
    stack: Optional[str] = None
    componentStack: Optional[str] = None
    source: Optional[str] = None
    selectedNode: Optional[Dict[str, Any]] = None

@app.post("/log")
def log_frontend_event(event: FrontendLog):
    log_msg = f"Frontend [{event.level.upper()}] from {event.source or 'unknown'}: {event.message}"
    if event.selectedNode:
        log_msg += f" (selectedNode: {event.selectedNode})"
    if event.stack:
        log_msg += f"\nStack trace:\n{event.stack}"
    if event.componentStack:
        log_msg += f"\nComponent stack:\n{event.componentStack}"
    
    if event.level.lower() == "error":
        logger.error(log_msg)
    elif event.level.lower() == "warning":
        logger.warning(log_msg)
    else:
        logger.info(log_msg)
        
    return {"success": True}


# ─────────────────────────────────────────────────────────────
# TestAgent — Autonomous test generation endpoints
# ─────────────────────────────────────────────────────────────
import uuid

_test_tasks = {}  # In-memory task store: {task_id: {status, result, ...}}

class TestGenRequest(BaseModel):
    target: str
    mode: str = "unit"
    file: Optional[str] = None
    class_name: Optional[str] = None

@app.post("/generate_tests")
def generate_tests(req: TestGenRequest):
    """Trigger autonomous test generation in background. Returns a task_id to poll."""
    task_id = str(uuid.uuid4())[:8]
    _test_tasks[task_id] = {"status": "running", "result": None, "started_at": time.strftime("%H:%M:%S")}

    def _run():
        try:
            from nelgraph.core.test_agent import TestAgent
            agent = TestAgent(target=req.target, mode=req.mode, file=req.file, class_name=req.class_name)
            result = agent.run()
            _test_tasks[task_id] = {"status": "done", "result": result}
        except Exception as e:
            logger.error(f"TestAgent error: {e}", exc_info=True)
            _test_tasks[task_id] = {"status": "error", "result": {"error": str(e), "log": []}}

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    logger.info(f"TestAgent task {task_id} started: target={req.target}, mode={req.mode}")
    return {"task_id": task_id, "status": "running"}


class BulkGenRequest(BaseModel):
    mode: str = "unit"

@app.post("/generate_tests/all")
def generate_tests_all(req: BulkGenRequest):
    """Trigger bulk test generation for all untested functions in the background."""
    client = get_client()
    try:
        result = client.run("""
            MATCH (f:Function)
            WHERE f.tested IS NULL OR f.tested = false
            OPTIONAL MATCH (f)-[:BELONGS_TO]->(c:Community)
            RETURN f.name as name, f.file as file, f.class_name as class_name,
                   f.complexity as complexity, c.id as community_id
            ORDER BY f.complexity DESC
        """)
        rows = [dict(r) for r in result]
    except Exception as e:
        logger.error(f"Error querying untested functions from Neo4j: {e}", exc_info=True)
        return {"error": f"Failed to retrieve functions: {e}"}

    if not rows:
        return {"status": "done", "message": "All functions are already tested."}

    task_id = str(uuid.uuid4())[:8]
    _test_tasks[task_id] = {
        "status": "running",
        "progress": {"done": 0, "total": len(rows), "current": "Commander planning batch..."},
        "results": [],
        "bugs_found": [],
        "started_at": time.strftime("%H:%M:%S")
    }

    def _run():
        try:
            from nelgraph.core.bulk_orchestrator import BulkTestOrchestrator
            orchestrator = BulkTestOrchestrator(functions=rows, mode=req.mode)
            
            def update_progress(progress, results, bugs_found):
                _test_tasks[task_id]["progress"] = progress
                _test_tasks[task_id]["results"] = results
                _test_tasks[task_id]["bugs_found"] = bugs_found

            report = orchestrator.run(progress_callback=update_progress)
            _test_tasks[task_id]["status"] = "done"
            _test_tasks[task_id]["result"] = report

            # Save report to disk
            try:
                reports_dir = os.path.join(GRAPHRAG_DATA_DIR, "reports")
                os.makedirs(reports_dir, exist_ok=True)
                report_path = os.path.join(reports_dir, f"bulk_report_{task_id}.json")
                latest_path = os.path.join(GRAPHRAG_DATA_DIR, "bulk_report_latest.json")
                
                with open(report_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
                with open(latest_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved bulk test report to {report_path} and bulk_report_latest.json")
            except Exception as re:
                logger.error(f"Failed to save bulk test report to disk: {re}", exc_info=True)

        except Exception as e:
            logger.error(f"BulkTestOrchestrator error: {e}", exc_info=True)
            _test_tasks[task_id]["status"] = "error"
            _test_tasks[task_id]["result"] = {"error": str(e), "log": []}

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    logger.info(f"Bulk test gen task {task_id} started for {len(rows)} functions, mode={req.mode}")
    return {"task_id": task_id, "status": "running"}


class IncrementalGenRequest(BaseModel):
    changed_files: List[str]
    mode: str = "unit"

@app.post("/generate_tests/incremental")
def generate_tests_incremental(req: IncrementalGenRequest):
    """Trigger incremental test generation for changed files and their blast radius."""
    client = get_client()
    files = [f.replace("\\", "/") for f in req.changed_files]
    
    try:
        # 1. Query functions belonging to changed files
        result_fns = client.run("""
            MATCH (fn:Function)
            WHERE fn.file IN $files
            OPTIONAL MATCH (fn)-[:BELONGS_TO]->(c:Community)
            RETURN fn.name as name, fn.file as file, fn.class_name as class_name,
                   fn.complexity as complexity, c.id as community_id
        """, {"files": files})
        fns = [dict(r) for r in result_fns]
        
        # 2. Query blast radius (callers of these functions)
        result_callers = client.run("""
            MATCH (caller:Function)-[:CALLS]->(fn:Function)
            WHERE fn.file IN $files
            OPTIONAL MATCH (caller)-[:BELONGS_TO]->(c:Community)
            RETURN caller.name as name, caller.file as file, caller.class_name as class_name,
                   caller.complexity as complexity, c.id as community_id
        """, {"files": files})
        callers = [dict(r) for r in result_callers]
    except Exception as e:
        logger.error(f"Error querying changed/blast-radius functions from Neo4j: {e}", exc_info=True)
        return {"error": f"Failed to retrieve functions: {e}"}

    # 3. Merge & Deduplicate functions
    seen = set()
    unique_fns = []
    for f in fns + callers:
        key = (f["name"], f.get("file"))
        if key not in seen:
            seen.add(key)
            unique_fns.append(f)
            
    if not unique_fns:
        return {"status": "done", "message": "No functions found to test for these files."}

    task_id = str(uuid.uuid4())[:8]
    _test_tasks[task_id] = {
        "status": "running",
        "progress": {"done": 0, "total": len(unique_fns), "current": "Commander planning batch..."},
        "results": [],
        "bugs_found": [],
        "started_at": time.strftime("%H:%M:%S")
    }

    def _run():
        try:
            from nelgraph.core.bulk_orchestrator import BulkTestOrchestrator
            orchestrator = BulkTestOrchestrator(functions=unique_fns, mode=req.mode)
            
            def update_progress(progress, results, bugs_found):
                _test_tasks[task_id]["progress"] = progress
                _test_tasks[task_id]["results"] = results
                _test_tasks[task_id]["bugs_found"] = bugs_found

            report = orchestrator.run(progress_callback=update_progress)
            _test_tasks[task_id]["status"] = "done"
            _test_tasks[task_id]["result"] = report
        except Exception as e:
            logger.error(f"Incremental BulkTestOrchestrator error: {e}", exc_info=True)
            _test_tasks[task_id]["status"] = "error"
            _test_tasks[task_id]["result"] = {"error": str(e), "log": []}

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    logger.info(f"Incremental test gen task {task_id} started for {len(unique_fns)} functions, mode={req.mode}")
    return {"task_id": task_id, "status": "running"}


@app.get("/task/{task_id}/status")
def get_task_status(task_id: str):
    """Poll the status of a test generation task."""
    task = _test_tasks.get(task_id)
    if not task:
        return {"error": "Task not found"}
    return task


class TestRunRequest(BaseModel):
    file_path: str

@app.post("/test/run")
def run_single_test(req: TestRunRequest):
    """Run a single test file and return results."""
    import subprocess, sys
    abs_path = os.path.join(CODEBASE_PATH, req.file_path).replace("\\", "/")
    if not os.path.exists(abs_path):
        return {"status": "error", "output": f"File not found: {abs_path}"}

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", abs_path, "-v", "--tb=short", "--no-header", "-q"],
            cwd=CODEBASE_PATH,
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return {"status": "passed" if proc.returncode == 0 else "failed", "output": output, "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"status": "failed", "output": "Timed out (60s)", "returncode": -1}
    except Exception as e:
        return {"status": "failed", "output": str(e), "returncode": -1}


import time

# ─────────────────────────────────────────────────────────────
# NEW: GET /status — Project overview
# ─────────────────────────────────────────────────────────────
@app.get("/status")
def get_status():
    """Return project overview: name, path, sync info, counts, neo4j status."""
    result = {
        "project_name": PROJECT_NAME,
        "codebase_path": CODEBASE_PATH,
        "last_sync": None,
        "last_commit": None,
        "total_functions": 0,
        "total_classes": 0,
        "total_communities": 0,
        "tested_count": 0,
        "neo4j": "error",
    }

    # Load sync state
    try:
        if os.path.exists(SYNC_STATE_PATH):
            with open(SYNC_STATE_PATH, "r", encoding="utf-8") as f:
                sync_state = json.load(f)
            result["last_sync"] = sync_state.get("last_sync_time")
            commit = sync_state.get("last_synced_commit")
            result["last_commit"] = commit[:8] if commit else None
    except Exception:
        pass

    # Query Neo4j for counts
    try:
        client = get_client()
        counts = client.run("""
            OPTIONAL MATCH (f:Function)
            WITH count(f) as total_functions
            OPTIONAL MATCH (c:Class)
            WITH total_functions, count(c) as total_classes
            OPTIONAL MATCH (com:Community)
            WITH total_functions, total_classes, count(com) as total_communities
            OPTIONAL MATCH (ft:Function) WHERE ft.tested = true
            RETURN total_functions, total_classes, total_communities, count(ft) as tested_count
        """)
        if counts:
            row = counts[0]
            result["total_functions"] = row["total_functions"]
            result["total_classes"] = row["total_classes"]
            result["total_communities"] = row["total_communities"]
            result["tested_count"] = row["tested_count"]
        result["neo4j"] = "connected"
    except Exception:
        pass

    return result


# ─────────────────────────────────────────────────────────────
# NEW: GET /functions — Paginated function list with filters
# ─────────────────────────────────────────────────────────────
@app.get("/functions")
def get_functions(
    tested: bool = None,
    community_id: int = None,
    high_complexity: bool = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return paginated list of Function nodes with optional filters."""
    client = get_client()

    where_clauses = []
    params = {"limit": limit, "offset": offset}

    if tested is not None:
        where_clauses.append("f.tested = $tested")
        params["tested"] = tested
    if community_id is not None:
        where_clauses.append("f.community_id = $community_id")
        params["community_id"] = community_id
    if high_complexity:
        where_clauses.append("f.complexity >= 5")

    where_str = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    cypher = f"""
        MATCH (f:Function)
        OPTIONAL MATCH (f)-[:BELONGS_TO]->(c:Community)
        {where_str}
        RETURN f.name as name, f.file as file, f.class_name as class_name,
               f.complexity as complexity, f.is_async as is_async, f.tested as tested,
               f.community_id as community_id, c.name as community_name,
               f.start_line as start_line, f.end_line as end_line
        ORDER BY f.complexity DESC
        SKIP $offset LIMIT $limit
    """

    rows = client.run(cypher, params)

    # Get total count for pagination
    count_cypher = f"MATCH (f:Function) {where_str} RETURN count(f) as total"
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    total_result = client.run(count_cypher, count_params)
    total = total_result[0]["total"] if total_result else 0

    return {
        "data": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ─────────────────────────────────────────────────────────────
# NEW: POST /node/{name}/mark_tested
# ─────────────────────────────────────────────────────────────
@app.post("/node/{name}/mark_tested")
def mark_tested(name: str):
    """Mark a Function node as tested."""
    client = get_client()
    result = client.run("""
        MATCH (f:Function {name: $name})
        SET f.tested = true
        RETURN f.tested as tested
    """, {"name": name})

    if not result:
        return {"success": False, "error": "Function not found"}
    return {"success": True, "name": name}


# ─────────────────────────────────────────────────────────────
# NEW: GET /commits — Timeline of commits
# ─────────────────────────────────────────────────────────────
@app.get("/commits")
def get_commits(limit: int = Query(default=20, le=100)):
    """Return list of Commit nodes with affected functions."""
    client = get_client()
    result = client.run("""
        MATCH (c:Commit)
        OPTIONAL MATCH (c)-[:MODIFIED]->(f:File)<-[:DEFINED_IN]-(fn:Function)
        RETURN c.hash as hash, c.message as message, c.author as author,
               c.timestamp as timestamp, c.files_changed as files_changed,
               collect(DISTINCT fn.name) as functions_affected
        ORDER BY c.timestamp DESC
        LIMIT $limit
    """, {"limit": limit})
    return [dict(r) for r in result]


# ─────────────────────────────────────────────────────────────
# NEW: GET /sync — Trigger incremental sync in background
# ─────────────────────────────────────────────────────────────
@app.get("/sync")
def trigger_sync():
    """Trigger incremental sync in a background thread."""
    try:
        from nelgraph.core.sync_pipeline import run_incremental_sync
        t = threading.Thread(target=run_incremental_sync)
        t.daemon = True
        t.start()
        return {"success": True, "message": "Sync started in background"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# EXISTING ENDPOINTS (preserved)
# ─────────────────────────────────────────────────────────────

@app.get("/graph/full")
def get_full_graph(limit: int = 200):
    """Return full graph data for visualization."""
    client = get_client()

    nodes_result = client.run("""
        MATCH (n) WHERE n.name IS NOT NULL
        RETURN elementId(n) as id, labels(n)[0] as type, n.name as name,
               n.description as description, n.community_id as community_id,
               n.raw_code as raw_code
        LIMIT $limit
    """, {"limit": limit})

    node_ids = {n["id"] for n in nodes_result}

    edges_result = client.run("""
        MATCH (a)-[r]->(b) WHERE a.name IS NOT NULL AND b.name IS NOT NULL
        RETURN elementId(a) as source, elementId(b) as target, type(r) as label
        LIMIT $limit
    """, {"limit": limit * 5})

    # Filter out dangling edges (where source or target node is not present in nodes list)
    valid_edges = [
        dict(e) for e in edges_result
        if e["source"] in node_ids and e["target"] in node_ids
    ]

    return {
        "nodes": [dict(n) for n in nodes_result],
        "edges": valid_edges,
    }


@app.get("/graph/community/{community_id}")
def get_community_subgraph(community_id: int):
    """Return subgraph of a community."""
    client = get_client()

    nodes = client.run("""
        MATCH (n) WHERE n.community_id = $cid AND n.name IS NOT NULL
        RETURN elementId(n) as id, labels(n)[0] as type, n.name as name,
               n.description as description
    """, {"cid": community_id})

    node_ids = {n["id"] for n in nodes}

    edges = client.run("""
        MATCH (a)-[r]->(b)
        WHERE a.community_id = $cid AND b.community_id = $cid
        RETURN elementId(a) as source, elementId(b) as target, type(r) as label
    """, {"cid": community_id})

    # Filter community edges to guarantee no dangling connections
    valid_edges = [
        dict(e) for e in edges
        if e["source"] in node_ids and e["target"] in node_ids
    ]

    return {
        "nodes": [dict(n) for n in nodes],
        "edges": valid_edges,
    }


@app.get("/communities")
def get_communities():
    """List all communities."""
    client = get_client()
    result = client.run("""
        MATCH (c:Community)
        OPTIONAL MATCH (n)-[:BELONGS_TO]->(c)
        RETURN c.id as id, c.name as name, c.summary as summary,
               count(n) as member_count
        ORDER BY member_count DESC
    """)
    return [dict(r) for r in result]


@app.get("/community/{id_or_name}")
def get_community_detail(id_or_name: str):
    """Get name and summary of a specific community by ID or name."""
    client = get_client()
    # Check if id_or_name is numeric (ID) or name
    if id_or_name.isdigit():
        result = client.run("""
            MATCH (c:Community) WHERE c.id = $id
            OPTIONAL MATCH (n)-[:BELONGS_TO]->(c)
            RETURN c.id as id, c.name as name, c.summary as summary,
                   collect(DISTINCT {name: n.name, type: labels(n)[0]}) as members,
                   count(n) as member_count
            LIMIT 1
        """, {"id": int(id_or_name)})
    else:
        result = client.run("""
            MATCH (c:Community) WHERE toLower(c.name) CONTAINS toLower($name)
            OPTIONAL MATCH (n)-[:BELONGS_TO]->(c)
            RETURN c.id as id, c.name as name, c.summary as summary,
                   collect(DISTINCT {name: n.name, type: labels(n)[0]}) as members,
                   count(n) as member_count
            LIMIT 1
        """, {"name": id_or_name.lower()})

    if not result:
        return {"error": "Community not found"}

    return dict(result[0])


@app.get("/query")
def search_query(q: str):
    return query(q)


# ─────────────────────────────────────────────────────────────
# ENHANCED: GET /node/{name} — Full detail with community_name
# ─────────────────────────────────────────────────────────────
@app.get("/node/{name}")
def node_detail(name: str):
    """Get full info about a specific node, including enriched fields and community."""
    logger.info(f"API Request: GET /node/{name}")
    client = get_client()
    try:
        result = client.run("""
            MATCH (n) WHERE n.name = $name
            OPTIONAL MATCH (n)-[:BELONGS_TO]->(c:Community)
            OPTIONAL MATCH (n)-[r_out]->(neighbor)
            OPTIONAL MATCH (caller)-[r_in]->(n)
            RETURN n,
                   labels(n) as labels,
                   c.name as community_name,
                   collect(DISTINCT {type: type(r_out), target: neighbor.name}) as outgoing,
                   collect(DISTINCT {type: type(r_in), source: caller.name}) as incoming
            LIMIT 1
        """, {"name": name})

        if not result:
            logger.warning(f"Node '{name}' not found in DB")
            return {}

        record = result[0]
        node_dict = dict(record["n"])
        labels = record.get("labels", [])

        # Read raw code for Function/Class nodes
        if any(l in ["Function", "Class"] for l in labels):
            try:
                node_dict["raw_code"] = client.read_node_code(node_dict)
            except Exception as code_ex:
                logger.warning(f"Failed to read raw code for '{name}': {code_ex}")
                pass

        # Ensure all enriched fields are present
        enriched_fields = [
            "how_it_works", "inputs", "output", "raises",
            "edge_cases", "test_recommendations",
            "complexity", "is_async", "visibility",
            "start_line", "end_line", "tested",
            "docstring", "class_name", "community_id", "file"
        ]
        for field in enriched_fields:
            if field not in node_dict:
                node_dict[field] = None

        # Log node detail values to help diagnose frontend crashes
        logger.info(
            f"Node '{name}' loaded. Type: {labels[0] if labels else 'None'}. "
            f"Inputs: {node_dict.get('inputs')} (type: {type(node_dict.get('inputs'))}). "
            f"Edge cases: {node_dict.get('edge_cases')} (type: {type(node_dict.get('edge_cases'))}). "
            f"Test recs: {node_dict.get('test_recommendations')} (type: {type(node_dict.get('test_recommendations'))})."
        )

        return {
            "node": node_dict,
            "labels": labels,
            "community_name": record.get("community_name"),
            "outgoing": record["outgoing"],
            "incoming": record["incoming"],
        }
    except Exception as ex:
        logger.error(f"Error fetching node detail for '{name}': {ex}", exc_info=True)
        raise ex


@app.get("/tasks")
def tasks(filter: str = None):
    all_tasks = list_open_tasks()
    if filter:
        all_tasks = [t for t in all_tasks if filter.lower() in t.get("name", "").lower()]
    return all_tasks


@app.get("/graph/search")
def search_nodes(q: str, limit: int = 20):
    """Full-text search in graph."""
    client = get_client()
    result = client.run("""
        MATCH (n) WHERE n.name IS NOT NULL
        AND (toLower(n.name) CONTAINS toLower($q)
             OR toLower(coalesce(n.description, '')) CONTAINS toLower($q))
        RETURN elementId(n) as id, labels(n)[0] as type, n.name as name,
               n.description as description, n.community_id as community_id
        LIMIT $limit
    """, {"q": q, "limit": limit})
    return [dict(r) for r in result]


@app.get("/owner")
def find_owner(q: str):
    """Find who has contributed most to a part of the code."""
    client = get_client()
    result = client.run("""
        MATCH (n) WHERE toLower(n.name) CONTAINS toLower($q)
        OPTIONAL MATCH (c:Commit)-[:MODIFIED]->(f:File)
        WHERE f.path CONTAINS n.name OR n.file IS NOT NULL AND f.path = n.file
        OPTIONAL MATCH (c)-[:AUTHORED_BY]->(p:Person)
        RETURN p.name as author, count(c) as commits
        ORDER BY commits DESC
        LIMIT 5
    """, {"q": q})
    return [dict(r) for r in result]


# ─────────────────────────────────────────────────────────────
# Static files mount (for production mode via --viz)
# Must be LAST, after all API routes.
# ─────────────────────────────────────────────────────────────
_dist_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "dist"
)
if os.path.isdir(_dist_path):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_dist_path, html=True), name="static")
