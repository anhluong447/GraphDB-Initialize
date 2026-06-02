import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_NAME = os.getenv("PROJECT_NAME", "A20-App-083")
CODEBASE_BASE_DIR = os.getenv("CODEBASE_BASE_DIR", "D:/GraphRAG/demo_project")

# Target project to index
CODEBASE_PATH = os.getenv("CODEBASE_PATH")
if not CODEBASE_PATH:
    CODEBASE_PATH = os.path.join(CODEBASE_BASE_DIR, PROJECT_NAME)
CODEBASE_PATH = CODEBASE_PATH.replace("\\", "/")

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

# ChromaDB
CHROMA_PATH = os.getenv("CHROMA_PATH")
if not CHROMA_PATH:
    CHROMA_PATH = f"./data/{PROJECT_NAME}/chroma_db"
CHROMA_PATH = CHROMA_PATH.replace("\\", "/")

# GitHub (optional)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")  # format: "owner/repo"
