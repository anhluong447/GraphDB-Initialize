import nelgraph
import sys
import inspect

print("Python version:", sys.version)
print("nelgraph version:", nelgraph.__version__)
print("nelgraph public API:", nelgraph.__all__)

# Assert version is 1.0.6
assert nelgraph.__version__ == "1.0.6", f"Expected version 1.0.6, got {nelgraph.__version__}"

# Assert new functions are in public API
assert "get_class_context" in nelgraph.__all__, "get_class_context missing from __all__"
assert "dump_context_to_file" in nelgraph.__all__, "dump_context_to_file missing from __all__"
assert hasattr(nelgraph, "get_class_context"), "get_class_context missing attribute on nelgraph"
assert hasattr(nelgraph, "dump_context_to_file"), "dump_context_to_file missing attribute on nelgraph"

import nelgraph.config as n_cfg
print("TEST_NELGRAPH ACTIVE CONFIG:")
print("NEO4J_URI:", n_cfg.NEO4J_URI)
print("NEO4J_USER:", n_cfg.NEO4J_USER)
print("NEO4J_PASSWORD:", n_cfg.NEO4J_PASSWORD)


# Test signature of get_function_context
sig = inspect.signature(nelgraph.get_function_context)
print("get_function_context signature:", sig)
assert "class_name" in sig.parameters, "class_name parameter missing in get_function_context signature"
assert "file" in sig.parameters, "file parameter missing in get_function_context signature"

# Test config setup
try:
    import os
    from dotenv import load_dotenv
    load_dotenv("D:/GraphRAG/.env")
    api_key = os.getenv("OPENROUTER_API_KEY", "test-key")

    nelgraph.configure(
        codebase_path="D:/GraphRAG/demo_project/MockProject",
        openrouter_api_key=api_key
    )
    print("Successfully configured codebase path and API key")
    
    # Try calling status() which shouldn't fail even if database is offline (it handles exception)
    status_info = nelgraph.status()
    print("nelgraph status info:", status_info)
    assert status_info["neo4j"] in ("offline", "connected"), f"Expected offline or connected, got {status_info['neo4j']}"
    print("Status API check PASSED")

    if status_info["neo4j"] == "connected":
        # Let's perform a query on Class nodes
        from graph.neo4j_client import get_client
        client = get_client()
        classes = client.run("MATCH (c:Class) RETURN c.name as name LIMIT 5")
        print("Found classes in DB:", [c["name"] for c in classes])

        functions = client.run("MATCH (f:Function) RETURN f.name as name LIMIT 5")
        print("Found functions in DB:", [f["name"] for f in functions])

        if classes:
            class_name = classes[0]["name"]
            print(f"Testing get_class_context for: {class_name}")
            class_ctx = nelgraph.get_class_context(class_name)
            print("class_ctx keys:", class_ctx.keys())
            assert "class" in class_ctx, "Expected 'class' key in class context"
            assert "methods" in class_ctx, "Expected 'methods' key in class context"

            # Test dump_context_to_file
            import os
            dump_path = "D:/GraphRAG/scratch/test_class_dump.md"
            if os.path.exists(dump_path):
                os.remove(dump_path)
            success = nelgraph.dump_context_to_file(class_name, dump_path)
            assert success, "Expected dump_context_to_file to return True"
            assert os.path.exists(dump_path), "Expected dump file to exist"
            print("Successfully verified get_class_context and dump_context_to_file")

        if functions:
            func_name = functions[0]["name"]
            print(f"Testing get_function_context for: {func_name}")
            func_ctx = nelgraph.get_function_context(func_name)
            print("func_ctx keys:", func_ctx.keys())
            assert "function" in func_ctx, "Expected 'function' key in function context"

except Exception as e:
    print("Error during API check:", e)
    sys.exit(1)

print("All programmatic checks PASSED!")


