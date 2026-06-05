# Fix Plan — Fix 3: Đóng gói thành Internal Module

> Thực hiện sau khi Fix 1 (PHP parser) và Fix 2 (bỏ API) đã xong.
> Mục tiêu: team test gen chỉ cần `import graphrag` là dùng được ngay,
> không cần biết gì về cấu trúc bên trong.

---

## Bước 1 — Fix Lazy Init (4 files)

### Vấn đề
4 files tạo OpenAI client ở module level → crash khi import nếu `OPENROUTER_API_KEY` trống.
Đây là blocker cho mọi thứ bên dưới.

---

### `embeddings/embedder.py`

Tìm đoạn ở đầu file:
```python
openai_client = openai.OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
)
```

Thay bằng:
```python
_openai_client = None

def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
        )
    return _openai_client
```

Trong hàm `embed_text()`, thay `openai_client.embeddings.create` bằng
`_get_openai_client().embeddings.create`.

Trong hàm `embed_texts()`, thay `openai_client.embeddings.create` bằng
`_get_openai_client().embeddings.create`.

---

### `extractors/testing_enricher.py`

Tìm đoạn ở đầu file:
```python
client_ai = openai.OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
)
```

Thay bằng:
```python
_client_ai = None

def _get_client_ai():
    global _client_ai
    if _client_ai is None:
        _client_ai = openai.OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
        )
    return _client_ai
```

Tìm TẤT CẢ chỗ dùng `client_ai.chat.completions.create(...)` trong file này,
thay bằng `_get_client_ai().chat.completions.create(...)`.

---

### `extractors/llm_extractor.py`

Tìm đoạn ở đầu file:
```python
client = openai.OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
)
```

Thay bằng:
```python
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = openai.OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
        )
    return _client
```

Tìm tất cả `client.chat.completions.create(...)` trong file, thay bằng
`_get_client().chat.completions.create(...)`.

---

### `community/summarizer.py`

Tìm đoạn ở đầu file:
```python
client_ai = openai.OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
)
```

Thay bằng:
```python
_client_ai = None

def _get_client_ai():
    global _client_ai
    if _client_ai is None:
        _client_ai = openai.OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
        )
    return _client_ai
```

Tìm tất cả `client_ai.chat.completions.create(...)` trong file, thay bằng
`_get_client_ai().chat.completions.create(...)`.

---

### Verify Bước 1

Chạy lệnh sau — phải không có lỗi gì:
```python
# Không có .env, không có API key → vẫn import được
import sys
sys.path.insert(0, ".")
import graph.neo4j_client
import embeddings.embedder
import extractors.testing_enricher
import extractors.llm_extractor
import community.summarizer
print("All imports OK")
```

---

## Bước 2 — Tạo root `__init__.py`

Tạo file `__init__.py` ở thư mục gốc của project (cùng cấp với `config.py`):

```python
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
from knowledge_base import (
    get_function_context,
    get_snapshot,
    get_changes,
    mark_tested,
    search,
    run_init,
    run_sync,
)

__version__ = "1.0.0"

__all__ = [
    "configure",
    "get_function_context",
    "get_snapshot",
    "get_changes",
    "mark_tested",
    "search",
    "run_init",
    "run_sync",
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

    Ví dụ:
        graphrag.configure(
            codebase_path="/home/user/opensourcepos",
            openrouter_api_key="sk-or-...",
        )
    """
    import os
    import config as _cfg

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
        import graph.neo4j_client as _nc
        _nc._client = None

    if neo4j_user:
        _cfg.NEO4J_USER = neo4j_user

    if llm_model:
        _cfg.LLM_MODEL = llm_model

    if embedding_model:
        _cfg.EMBEDDING_MODEL = embedding_model

    if embedding_dimensions:
        _cfg.EMBEDDING_DIMENSIONS = embedding_dimensions


def _reset_ai_clients():
    """Reset tất cả lazy OpenAI client singletons để pick up config mới."""
    try:
        import embeddings.embedder as _emb
        _emb._openai_client = None
    except Exception:
        pass
    try:
        import extractors.testing_enricher as _te
        _te._client_ai = None
    except Exception:
        pass
    try:
        import extractors.llm_extractor as _le
        _le._client = None
    except Exception:
        pass
    try:
        import community.summarizer as _sm
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
    import config as _cfg
    from initialize_graph import _load_sync_state

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
        from graph.neo4j_client import get_client
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
```

---

## Bước 3 — Cập nhật `docker-compose.yml`

Hiện tại `chromadb` service trong docker-compose expose port `8000` ra ngoài
nhưng không cần thiết vì ChromaDB được dùng qua `PersistentClient` (local file),
không qua network. Xóa service `chromadb` khỏi docker-compose:

```yaml
# docker-compose.yml sau khi chỉnh
version: "3.8"
services:
  neo4j:
    image: neo4j:5.15-community
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-graphrag123}
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
      NEO4J_dbms_security_procedures_unrestricted: "apoc.*,gds.*"
      NEO4J_db_tx__log_rotation_size: "10M"
      NEO4J_db_tx__log_rotation_retention__policy: "1 files"
      NEO4J_server_memory_heap_initial__size: "128M"
      NEO4J_server_memory_heap_max__size: "512M"
      NEO4J_server_memory_pagecache_size: "128M"
    volumes:
      - ${NEO4J_DATA_DIR:-./.graphrag_data/neo4j/data}:/data
      - ${NEO4J_LOGS_DIR:-./.graphrag_data/neo4j/logs}:/logs
    tmpfs:
      - /var/lib/neo4j/run
# chromadb service đã xóa — dùng PersistentClient local, không cần container
```

---

## Bước 4 — Thêm hướng dẫn git submodule vào `USAGE.md`

Append phần sau vào cuối file `guides/USAGE.md`:

```markdown
---

## Tích hợp vào project khác (Git Submodule)

### Thêm graphrag vào project test gen

```bash
# Trong repo project test gen
git submodule add https://github.com/anhluong447/GraphDB-Initialize graphrag
git submodule update --init
pip install -r graphrag/requirements.txt
```

### Dùng trong code

```python
import sys
sys.path.insert(0, "./graphrag")

import graphrag

# Cấu hình (hoặc dùng .env trong thư mục graphrag/)
graphrag.configure(
    codebase_path="/path/to/target-project",
    openrouter_api_key="sk-or-...",
    neo4j_password="yourpassword",
)

# Kiểm tra trạng thái
print(graphrag.status())

# First run
graphrag.run_init()
snapshot = graphrag.get_snapshot()

for community in snapshot["communities"]:
    for func in community["functions"]:
        ctx = graphrag.get_function_context(func["name"])
        # ... team test gen xử lý ctx ...
        graphrag.mark_tested(func["name"])

# Ongoing — gọi sau mỗi git commit mới
graphrag.run_sync()
changes = graphrag.get_changes("abc123f")
for func in changes["changed_functions"]:
    ctx = graphrag.get_function_context(func["name"])
    # ... update test ...
    graphrag.mark_tested(func["name"])
```

### Cập nhật submodule khi có thay đổi

```bash
cd graphrag
git pull origin main
cd ..
git add graphrag
git commit -m "chore: update graphrag submodule"
```
```

---

## Thứ tự implement

```
Bước 1 — Fix lazy init
    → embeddings/embedder.py
    → extractors/testing_enricher.py
    → extractors/llm_extractor.py
    → community/summarizer.py
    → Verify: import tất cả không crash

Bước 2 — Tạo root __init__.py
    → Verify: import graphrag không crash
    → Verify: graphrag.status() chạy được khi Neo4j offline

Bước 3 — Cập nhật docker-compose.yml
    → Xóa chromadb service
    → Verify: docker compose up -d chạy được

Bước 4 — Cập nhật USAGE.md
    → Append git submodule instructions
```

---

## Notes cho AI agent implement

- Bước 1 là prerequisite cho tất cả — làm trước, verify xong rồi mới tiếp.
- Khi fix lazy init, tên biến global phải có prefix `_` để phân biệt private.
- `configure()` phải recalculate các dependent paths khi `codebase_path` thay đổi
  vì `GRAPHRAG_DATA_DIR`, `CHROMA_PATH`, `SYNC_STATE_PATH` đều derive từ nó.
- `_reset_ai_clients()` phải dùng try/except cho từng module vì có thể chưa import.
- `status()` KHÔNG được crash nếu Neo4j offline — dùng try/except bao toàn bộ
  phần query Neo4j.
- Không xóa `graph/__init__.py`, `embeddings/__init__.py` etc. — giữ nguyên.
- Bước 3 chỉ xóa `chromadb` service trong docker-compose, không đụng vào
  `embeddings/chroma_client.py` — ChromaDB vẫn dùng PersistentClient (local file).
