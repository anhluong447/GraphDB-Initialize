import sys
import os

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from graph.neo4j_client import get_client
from query.engine import query, get_node_detail, list_open_tasks

app = FastAPI(title="GraphRAG Visualization API")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/graph/full")
def get_full_graph(limit: int = 200):
    """Return full graph data for visualization."""
    client = get_client()

    nodes_result = client.run("""
        MATCH (n) WHERE n.name IS NOT NULL
        RETURN id(n) as id, labels(n)[0] as type, n.name as name,
               n.description as description, n.community_id as community_id,
               n.raw_code as raw_code
        LIMIT $limit
    """, {"limit": limit})

    node_ids = {n["id"] for n in nodes_result}

    edges_result = client.run("""
        MATCH (a)-[r]->(b) WHERE a.name IS NOT NULL AND b.name IS NOT NULL
        RETURN id(a) as source, id(b) as target, type(r) as label
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
        RETURN id(n) as id, labels(n)[0] as type, n.name as name,
               n.description as description
    """, {"cid": community_id})

    node_ids = {n["id"] for n in nodes}

    edges = client.run("""
        MATCH (a)-[r]->(b)
        WHERE a.community_id = $cid AND b.community_id = $cid
        RETURN id(a) as source, id(b) as target, type(r) as label
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
            RETURN c.id as id, c.name as name, c.summary as summary
            LIMIT 1
        """, {"id": int(id_or_name)})
    else:
        result = client.run("""
            MATCH (c:Community) WHERE toLower(c.name) CONTAINS toLower($name)
            RETURN c.id as id, c.name as name, c.summary as summary
            LIMIT 1
        """, {"name": id_or_name.lower()})

    if not result:
        return {"error": "Community not found"}

    return dict(result[0])


@app.get("/query")
def search_query(q: str):
    return query(q)


@app.get("/node/{name}")
def node_detail(name: str):
    return get_node_detail(name)


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
        RETURN id(n) as id, labels(n)[0] as type, n.name as name,
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
