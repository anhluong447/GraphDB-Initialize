"""
GraphRAG Knowledge Base Server — Entry Point

Starts the FastAPI server with all API endpoints, ensures databases are running,
and prints server information banner.

Usage:
    python start_server.py                  # Start on default port 8080
    python start_server.py --port 9090      # Custom port
    python start_server.py --host 0.0.0.0   # Bind to all interfaces (default)
"""

import sys
import os
import argparse

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="GraphRAG Knowledge Base Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--skip-docker", action="store_true", help="Skip starting Docker databases")
    args = parser.parse_args()

    from config import API_KEY, WEBHOOK_URL, SERVER_MODE, GRAPHRAG_DATA_DIR

    # Banner
    print("=" * 60)
    print("   GraphRAG — Knowledge Base API Server")
    print("=" * 60)
    print(f"   Server Mode   : {'ON' if SERVER_MODE else 'OFF'}")
    print(f"   Data Directory: {GRAPHRAG_DATA_DIR}")
    print(f"   API Key Auth  : {'ENABLED' if API_KEY else 'DISABLED (dev mode)'}")
    print(f"   Webhook URL   : {WEBHOOK_URL or '(not configured)'}")
    print(f"   Host          : {args.host}")
    print(f"   Port          : {args.port}")
    print("=" * 60)

    # Ensure data directories exist
    os.makedirs(GRAPHRAG_DATA_DIR, exist_ok=True)

    # Start Docker databases
    if not args.skip_docker:
        print("\n[Server] Starting databases...")
        try:
            from initialize_graph import _start_docker
            _start_docker()
        except Exception as e:
            print(f"[Server] Warning: Could not start Docker: {e}")
            print("[Server] Make sure Neo4j is running manually.")

    # Start Uvicorn
    print(f"\n[Server] Starting API server on http://{args.host}:{args.port}")
    print(f"[Server] API docs available at http://localhost:{args.port}/docs")
    print()

    import uvicorn
    uvicorn.run(
        "server.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
