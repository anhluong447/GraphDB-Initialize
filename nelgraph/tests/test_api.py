import pytest
from unittest.mock import MagicMock

def test_log_frontend_event_info(client):
    payload = {
        "level": "info",
        "message": "User clicked on community node",
        "source": "frontend_navbar"
    }
    response = client.post("/log", json=payload)
    assert response.status_code == 200
    assert response.json() == {"success": True}

def test_log_frontend_event_error_with_stack(client):
    payload = {
        "level": "error",
        "message": "React rendering crash #31",
        "stack": "Error: React Error 31\n  at Render...",
        "componentStack": "  in DetailPanel\n  in ErrorBoundary",
        "source": "frontend_error_boundary",
        "selectedNode": {"name": "test_func", "type": "Function"}
    }
    response = client.post("/log", json=payload)
    assert response.status_code == 200
    assert response.json() == {"success": True}

def test_get_status_connected(client, mock_neo4j):
    # Mock Neo4j run to return counts
    mock_neo4j.run.return_value = [{
        "total_functions": 10,
        "total_classes": 5,
        "total_communities": 3,
        "tested_count": 2
    }]
    
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["total_functions"] == 10
    assert data["total_classes"] == 5
    assert data["total_communities"] == 3
    assert data["tested_count"] == 2
    assert data["neo4j"] == "connected"

def test_get_status_db_error(client, mock_neo4j):
    # Mock Neo4j run to raise an exception
    mock_neo4j.run.side_effect = Exception("Neo4j database down")
    
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["neo4j"] == "error"
    # Verify counts fall back to 0
    assert data["total_functions"] == 0

def test_mark_tested_success(client, mock_neo4j):
    # Mock successful update query
    mock_neo4j.run.return_value = [{"tested": True}]
    
    response = client.post("/node/calculate_salary/mark_tested")
    assert response.status_code == 200
    assert response.json() == {"success": True, "name": "calculate_salary"}
    
    # Verify Cypher query execution params
    mock_neo4j.run.assert_called_once()
    assert "calculate_salary" in mock_neo4j.run.call_args[0][1].values()

def test_mark_tested_not_found(client, mock_neo4j):
    # Mock empty result (not found)
    mock_neo4j.run.return_value = []
    
    response = client.post("/node/unknown_function/mark_tested")
    assert response.status_code == 200
    assert response.json() == {"success": False, "error": "Function not found"}

def test_node_detail_success(client, mock_neo4j):
    # Mock return values for node properties query
    mock_node_record = {
        "n": {
            "name": "auth_user",
            "how_it_works": "Validates credentials against DB",
            "inputs": '{"email": "str"}',
            "complexity": 4
        },
        "labels": ["Function"],
        "community_name": "Authentication",
        "outgoing": [{"type": "CALLS", "target": "db_insert"}],
        "incoming": [{"type": "CALLS", "source": "login_route"}]
    }
    mock_neo4j.run.return_value = [mock_node_record]
    
    response = client.get("/node/auth_user")
    assert response.status_code == 200
    data = response.json()
    
    # Verify properties
    node = data["node"]
    assert node["name"] == "auth_user"
    assert node["how_it_works"] == "Validates credentials against DB"
    assert node["inputs"] == '{"email": "str"}'
    
    # Verify defaulting of missing enriched fields
    assert node["raises"] is None
    assert node["edge_cases"] is None
    assert node["tested"] is None
    
    # Verify relations and metadata
    assert data["labels"] == ["Function"]
    assert data["community_name"] == "Authentication"
    assert data["outgoing"] == [{"type": "CALLS", "target": "db_insert"}]
    assert data["incoming"] == [{"type": "CALLS", "source": "login_route"}]

def test_node_detail_not_found(client, mock_neo4j):
    # Mock empty response
    mock_neo4j.run.return_value = []
    
    response = client.get("/node/nonexistent_node")
    assert response.status_code == 200
    assert response.json() == {}

def test_get_full_graph_filters_dangling_edges(client, mock_neo4j):
    # Mock nodes query results
    nodes = [
        {"id": "node1", "name": "main.py", "type": "File", "description": "Entry point"},
        {"id": "node2", "name": "run_job", "type": "Function", "description": "Worker job"}
    ]
    # Mock edges query results (one valid, one dangling pointing to nonexistent node3)
    edges = [
        {"source": "node1", "target": "node2", "label": "DEFINES"},
        {"source": "node2", "target": "node3", "label": "CALLS"}
    ]
    
    # Side effects to return nodes first, then edges
    mock_neo4j.run.side_effect = [nodes, edges]
    
    response = client.get("/graph/full")
    assert response.status_code == 200
    data = response.json()
    
    # Verify nodes are untouched
    assert len(data["nodes"]) == 2
    
    # Verify edge list only contains the valid, non-dangling connection
    assert len(data["edges"]) == 1
    assert data["edges"][0] == {"source": "node1", "target": "node2", "label": "DEFINES"}
