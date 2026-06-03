import os
from dotenv import load_dotenv

# Load .env from the current working directory first, and fall back to the config directory
load_dotenv()
config_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(config_dir, ".env"))

PROJECT_NAME = os.getenv("PROJECT_NAME", "GraphRAG-Project")

# Target project to index. By default, it is the parent folder of this tool.
CODEBASE_PATH = os.getenv("CODEBASE_PATH")
if not CODEBASE_PATH:
    CODEBASE_PATH = ".."

# If it's a relative path, resolve it relative to this config file's directory
if not os.path.isabs(CODEBASE_PATH):
    CODEBASE_PATH = os.path.abspath(os.path.join(config_dir, CODEBASE_PATH))

CODEBASE_PATH = CODEBASE_PATH.replace("\\", "/")

# GraphRAG data directory — stored inside the target codebase
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
}

# Directories to skip during parsing
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".cursor", ".claude", ".codex", ".gemini", ".ai-log"}

# OpenRouter API (used for both LLM and embeddings)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Model IDs on OpenRouter
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-large")

# Neo4j
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
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

# GitHub (optional)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")  # format: "owner/repo"
