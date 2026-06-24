import sys
import os
import pytest
from unittest.mock import MagicMock

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def mock_neo4j(monkeypatch):
    mock_client = MagicMock()
    # Provide default return values for mock database operations
    mock_client.run.return_value = []
    mock_client.read_node_code.return_value = "def mock_code(): pass"
    
    # Overwrite get_client in all import locations to prevent any real DB activity
    monkeypatch.setattr("nelgraph.visualization.backend.api.get_client", lambda: mock_client)
    monkeypatch.setattr("nelgraph.query.engine.get_client", lambda: mock_client)
    monkeypatch.setattr("nelgraph.graph.neo4j_client.get_client", lambda: mock_client)
    
    return mock_client

@pytest.fixture
def client(mock_neo4j):
    # Import app after get_client is successfully patched
    from nelgraph.visualization.backend.api import app
    from fastapi.testclient import TestClient
    return TestClient(app)
