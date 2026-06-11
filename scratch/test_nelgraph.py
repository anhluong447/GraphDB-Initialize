import nelgraph
import sys

print("Python version:", sys.version)
print("nelgraph version:", nelgraph.__version__)
print("nelgraph public API:", nelgraph.__all__)

# Test config setup
try:
    nelgraph.configure(
        codebase_path="D:/GraphRAG/demo_project/opensourcepos",
        openrouter_api_key="test-key"
    )
    print("Successfully configured codebase path and API key")
    
    # Try calling status() which shouldn't fail even if database is offline (it handles exception)
    status_info = nelgraph.status()
    print("nelgraph status info:", status_info)
    assert status_info["neo4j"] == "offline", "Expected offline status without running database"
    print("Status API check PASSED")
except Exception as e:
    print("Error during API check:", e)
    sys.exit(1)

print("All programmatic checks PASSED!")
