import os
from dotenv import load_dotenv

# Load .env files with fallback paths
load_dotenv(os.path.join(os.getcwd(), ".env"), override=False)
load_dotenv(os.path.expanduser("~/.nelgraph/.env"), override=False)

config_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(config_dir, ".env"), override=False)

# Discover from CODEBASE_PATH if set
codebase_env_path = os.getenv("CODEBASE_PATH")
if codebase_env_path:
    if not os.path.isabs(codebase_env_path):
        codebase_env_path = os.path.abspath(os.path.join(config_dir, codebase_env_path))
    load_dotenv(os.path.join(codebase_env_path, ".env"), override=False)
    load_dotenv(os.path.join(codebase_env_path, ".nelgraph.env"), override=False)


PROJECT_NAME = os.getenv("PROJECT_NAME", "GraphRAG-Project")



# Target project to index. By default, it is the parent folder of this tool.
CODEBASE_PATH = os.getenv("CODEBASE_PATH")
if not CODEBASE_PATH:
    CODEBASE_PATH = ".."

# If it's a relative path, resolve it relative to this config file's directory
if not os.path.isabs(CODEBASE_PATH):
    CODEBASE_PATH = os.path.abspath(os.path.join(config_dir, CODEBASE_PATH))

CODEBASE_PATH = CODEBASE_PATH.replace("\\", "/")

# GraphRAG data directory — stored inside the target codebase's .graphrag_data/
GRAPHRAG_DATA_DIR = os.getenv("GRAPHRAG_DATA_DIR")
if not GRAPHRAG_DATA_DIR:
    GRAPHRAG_DATA_DIR = os.path.join(CODEBASE_PATH, ".graphrag_data")
GRAPHRAG_DATA_DIR = GRAPHRAG_DATA_DIR.replace("\\", "/")

# Supported languages for AST parsing
SUPPORTED_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".php": "php",
}

# Directories to skip during parsing
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".cursor", ".claude", ".codex", ".gemini", ".ai-log", ".agent"}
tool_dir_name = os.path.basename(config_dir)
if tool_dir_name and os.path.abspath(CODEBASE_PATH) != os.path.abspath(config_dir):
    IGNORE_DIRS.add(tool_dir_name)

# OpenRouter API (used for both LLM and embeddings)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Model IDs on OpenRouter
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-large")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "512"))
ENRICH_MIN_COMPLEXITY = int(os.getenv("ENRICH_MIN_COMPLEXITY", "2"))

# TestAgent — 3-layer autonomous test generation
COMMANDER_MODEL = os.getenv("COMMANDER_MODEL", "deepseek/deepseek-r1")
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "deepseek/deepseek-v4-flash")
WORKER_MODEL = os.getenv("WORKER_MODEL", "qwen/qwen3-coder-next")

# Fallback models (comma-separated lists) for resilience
COMMANDER_FALLBACKS = [m.strip() for m in os.getenv("COMMANDER_FALLBACKS", "").split(",") if m.strip()]
PLANNER_FALLBACKS = [m.strip() for m in os.getenv("PLANNER_FALLBACKS", "").split(",") if m.strip()]
WORKER_FALLBACKS = [m.strip() for m in os.getenv("WORKER_FALLBACKS", "").split(",") if m.strip()]

TEST_FRAMEWORK = os.getenv("TEST_FRAMEWORK", "pytest")  # pytest | jest | vitest
PYTEST_PATH = os.getenv("PYTEST_PATH", "")
MAX_HEAL_RETRIES = int(os.getenv("MAX_HEAL_RETRIES", "3"))
MAX_BULK_WORKERS = int(os.getenv("MAX_BULK_WORKERS", "5"))

# Neo4j
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
import sys
if sys.platform == "win32" and "localhost" in NEO4J_URI:
    NEO4J_URI = NEO4J_URI.replace("localhost", "127.0.0.1")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "graphrag123")

# Neo4j data directories (for Docker volume mounts)
NEO4J_DATA_DIR = os.path.join(GRAPHRAG_DATA_DIR, "neo4j", "data").replace("\\", "/")
NEO4J_LOGS_DIR = os.path.join(GRAPHRAG_DATA_DIR, "neo4j", "logs").replace("\\", "/")

# ChromaDB
CHROMA_PATH = os.getenv("CHROMA_PATH")
if not CHROMA_PATH:
    CHROMA_PATH = os.path.join(GRAPHRAG_DATA_DIR, "chromadb")
CHROMA_PATH = CHROMA_PATH.replace("\\", "/")

# Sync state file for incremental updates
SYNC_STATE_PATH = os.path.join(GRAPHRAG_DATA_DIR, "sync_state.json").replace("\\", "/")
TEST_REGISTRY_PATH = os.path.join(GRAPHRAG_DATA_DIR, "test_registry.json").replace("\\", "/")

LOCK_PATH = os.path.join(GRAPHRAG_DATA_DIR, ".nelgraph.lock").replace("\\", "/")


# GitHub (optional)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")  # format: "owner/repo"

VIZ_API_URL = os.environ.get("NELGRAPH_VIZ_API_URL", "http://localhost:8080")
