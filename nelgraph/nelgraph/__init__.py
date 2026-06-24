"""
GraphRAG Knowledge Base — Internal Python Module

Cách dùng nhanh nhất:

    import graphrag
    graphrag.configure(codebase_path="/path/to/project", openrouter_api_key="sk-...")
    graphrag.run_init()

    ctx = graphrag.get_function_context("processOrder")
    snap = graphrag.get_snapshot()
    changes = graphrag.get_changes("abc123f")
    graphrag.mark_tested("processOrder")
"""

# --- Public API ---
from nelgraph.knowledge_base import (
    get_function_context,
    get_snapshot,
    get_changes,
    mark_tested,
    search,
    run_init,
    run_sync,
    run_test_generation,
    get_class_context,
    dump_context_to_file,
)

__version__ = "1.0.8"

__all__ = [
    "configure",
    "get_function_context",
    "get_snapshot",
    "get_changes",
    "mark_tested",
    "search",
    "run_init",
    "run_sync",
    "run_test_generation",
    "get_class_context",
    "dump_context_to_file",
]


def configure(
    codebase_path: str = None,
    openrouter_api_key: str = None,
    neo4j_uri: str = None,
    neo4j_password: str = None,
    neo4j_user: str = None,
    llm_model: str = None,
    embedding_model: str = None,
    embedding_dimensions: int = None,
    env_file: str = None,
):
    """
    Cấu hình graphrag bằng code thay vì .env file.
    Gọi hàm này TRƯỚC khi dùng bất kỳ function nào khác.

    Args:
        codebase_path:        Đường dẫn tuyệt đối đến codebase cần analyze.
        openrouter_api_key:   API key của OpenRouter.
        neo4j_uri:            URI kết nối Neo4j (default: bolt://127.0.0.1:7687).
        neo4j_password:       Password Neo4j.
        neo4j_user:           Username Neo4j (default: neo4j).
        llm_model:            Model ID trên OpenRouter cho LLM enrichment.
        embedding_model:      Model ID trên OpenRouter cho embeddings.
        embedding_dimensions: Số chiều vector (default: 512).
        env_file:             Đường dẫn đến file .env cụ thể.

    Ví dụ:
        graphrag.configure(
            codebase_path="/home/user/opensourcepos",
            openrouter_api_key="sk-or-...",
        )
    """
    import os
    import nelgraph.config as _cfg

    if env_file:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=True)
        if os.getenv("CODEBASE_PATH"):
            codebase_path = os.getenv("CODEBASE_PATH")
        if os.getenv("OPENROUTER_API_KEY"):
            openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        if os.getenv("NEO4J_URI"):
            neo4j_uri = os.getenv("NEO4J_URI")
        if os.getenv("NEO4J_PASSWORD"):
            neo4j_password = os.getenv("NEO4J_PASSWORD")
        if os.getenv("NEO4J_USER"):
            neo4j_user = os.getenv("NEO4J_USER")
        if os.getenv("LLM_MODEL"):
            llm_model = os.getenv("LLM_MODEL")
        if os.getenv("EMBEDDING_MODEL"):
            embedding_model = os.getenv("EMBEDDING_MODEL")
        if os.getenv("EMBEDDING_DIMENSIONS"):
            try:
                embedding_dimensions = int(os.getenv("EMBEDDING_DIMENSIONS"))
            except ValueError:
                pass

    if codebase_path:
        import os as _os
        codebase_path = _os.path.abspath(codebase_path).replace("\\", "/")
        _cfg.CODEBASE_PATH = codebase_path
        os.environ["CODEBASE_PATH"] = codebase_path

        # Recalculate dependent paths
        _cfg.GRAPHRAG_DATA_DIR = _os.path.join(codebase_path, ".graphrag_data").replace("\\", "/")
        _cfg.NEO4J_DATA_DIR = _os.path.join(_cfg.GRAPHRAG_DATA_DIR, "neo4j", "data").replace("\\", "/")
        _cfg.NEO4J_LOGS_DIR = _os.path.join(_cfg.GRAPHRAG_DATA_DIR, "neo4j", "logs").replace("\\", "/")
        _cfg.CHROMA_PATH = _os.path.join(_cfg.GRAPHRAG_DATA_DIR, "chromadb").replace("\\", "/")
        _cfg.SYNC_STATE_PATH = _os.path.join(_cfg.GRAPHRAG_DATA_DIR, "sync_state.json").replace("\\", "/")

    if openrouter_api_key:
        _cfg.OPENROUTER_API_KEY = openrouter_api_key
        os.environ["OPENROUTER_API_KEY"] = openrouter_api_key
        # Reset lazy clients so they pick up the new key
        _reset_ai_clients()

    if neo4j_uri:
        _cfg.NEO4J_URI = neo4j_uri
        os.environ["NEO4J_URI"] = neo4j_uri

    if neo4j_password:
        _cfg.NEO4J_PASSWORD = neo4j_password
        os.environ["NEO4J_PASSWORD"] = neo4j_password
        # Reset Neo4j singleton
        import nelgraph.graph.neo4j_client as _nc
        _nc._client = None

    if neo4j_user:
        _cfg.NEO4J_USER = neo4j_user

    if llm_model:
        _cfg.LLM_MODEL = llm_model

    if embedding_model:
        _cfg.EMBEDDING_MODEL = embedding_model

    if embedding_dimensions:
        _cfg.EMBEDDING_DIMENSIONS = embedding_dimensions

    # Propagate changes to all imported modules to prevent stale imports
    import sys
    for mod_name, mod in list(sys.modules.items()):
        if mod and (mod_name.startswith("nelgraph.") or mod_name in ["initialize_graph", "knowledge_base", "core.init_pipeline", "core.sync_pipeline", "graph.builder", "graph.neo4j_client", "embeddings.chroma_client", "embeddings.embedder", "extractors.llm_extractor", "extractors.testing_enricher", "parsers.git_parser", "updater.git_hook"]):
            for key in ["CODEBASE_PATH", "GRAPHRAG_DATA_DIR", "NEO4J_DATA_DIR", "NEO4J_LOGS_DIR", "CHROMA_PATH", "SYNC_STATE_PATH", "TEST_REGISTRY_PATH", "OPENROUTER_API_KEY", "LLM_MODEL", "EMBEDDING_MODEL", "EMBEDDING_DIMENSIONS", "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "COMMANDER_MODEL", "WORKER_MODEL", "TEST_FRAMEWORK", "MAX_HEAL_RETRIES"]:
                if hasattr(_cfg, key):
                    val = getattr(_cfg, key)
                    if hasattr(mod, key):
                        setattr(mod, key, val)


def _reset_ai_clients():
    """Reset tất cả lazy OpenAI client singletons để pick up config mới."""
    try:
        import nelgraph.embeddings.embedder as _emb
        _emb._openai_client = None
    except Exception:
        pass
    try:
        import nelgraph.extractors.testing_enricher as _te
        _te._client_ai = None
    except Exception:
        pass
    try:
        import nelgraph.extractors.llm_extractor as _le
        _le._client = None
    except Exception:
        pass
    try:
        import nelgraph.community.summarizer as _sm
        _sm._client_ai = None
    except Exception:
        pass


def status() -> dict:
    """
    Trả về trạng thái hiện tại của graph.
    Không cần Neo4j đang chạy — nếu không kết nối được thì báo offline.

    Returns:
        {
            "neo4j": "connected" | "offline",
            "codebase_path": "...",
            "last_sync": "...",
            "total_functions": 0,
            "enriched_functions": 0,
        }
    """
    import nelgraph.config as _cfg
    from nelgraph.initialize_graph import _load_sync_state

    result = {
        "neo4j": "offline",
        "codebase_path": _cfg.CODEBASE_PATH,
        "last_sync": None,
        "total_functions": 0,
        "enriched_functions": 0,
    }

    sync_state = _load_sync_state()
    if sync_state:
        result["last_sync"] = sync_state.get("last_sync_time")

    try:
        from nelgraph.graph.neo4j_client import get_client
        client = get_client()
        stats = client.run("""
            OPTIONAL MATCH (f:Function) WITH count(f) as total
            OPTIONAL MATCH (f2:Function) WHERE f2.how_it_works IS NOT NULL
            RETURN total, count(f2) as enriched
        """)
        if stats:
            result["neo4j"] = "connected"
            result["total_functions"] = stats[0]["total"]
            result["enriched_functions"] = stats[0]["enriched"]
    except Exception:
        pass

    return result
