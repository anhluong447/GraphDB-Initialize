# GraphDB-Initialize — Fix Plan

> Tài liệu này mô tả các thay đổi cần thực hiện trên repo `anhluong447/GraphDB-Initialize`.
> Implement theo thứ tự ưu tiên từ trên xuống.

---

## Ưu tiên 1 — IMPORTS Relationship (Blocker cho test gen)

### Vấn đề
`parsers/ast_parser.py` hiện tại chỉ extract `CALLS` relationships (function A gọi function B trong
cùng project). Không có thông tin về external imports (`stripe`, `requests`, third-party libs).
Khi team gen test không biết mock cái gì → test gen ra không chạy được.

### Yêu cầu
Trong `parsers/ast_parser.py`, bổ sung hàm `_extract_imports()` sử dụng Tree-Sitter để extract
toàn bộ import statements từ mỗi file. Kết quả trả thêm field `imports` vào mỗi parsed file dict.

**Cấu trúc mỗi import item:**
```python
{
    "module": "stripe",           # tên module gốc (phần đầu tiên)
    "full_path": "stripe.charge", # full import path nếu có
    "alias": "st",                # alias nếu có (import stripe as st)
    "names": ["charge", "Stripe"],# tên cụ thể nếu dùng from...import
    "is_external": True,          # True nếu không phải relative import (./) và không có trong codebase
    "source_file": "payments/processor.py"
}
```

**Logic phân biệt internal vs external:**
- Relative imports (bắt đầu bằng `.`) → `is_external = False`
- Module name trùng với folder/file trong `CODEBASE_PATH` → `is_external = False`
- Còn lại → `is_external = True`

**Hỗ trợ các dạng import:**
- Python: `import stripe`, `from stripe import Charge`, `import stripe as st`, `from . import utils`
- JavaScript/TypeScript: `import stripe from 'stripe'`, `import { Charge } from 'stripe'`,
  `const stripe = require('stripe')`

### Thay đổi trong `graph/builder.py`
Trong hàm `build_file_nodes()`, sau khi tạo Function nodes, thêm đoạn tạo `IMPORTS` relationships:

```cypher
// Với mỗi import trong parsed file:
MERGE (m:Module {name: $module_name})
SET m.is_external = $is_external
WITH m
MATCH (f:File {path: $file_path})
MERGE (f)-[:IMPORTS {full_path: $full_path, alias: $alias, names: $names}]->(m)
```

Ngoài ra tạo `USES_EXTERNAL` edge trực tiếp từ Function đến Module nếu function body
chứa tên module đó trong `calls` list:

```cypher
MATCH (fn:Function {file: $file_path})
WHERE any(call IN fn.calls WHERE call STARTS WITH $module_name)
MATCH (m:Module {name: $module_name})
MERGE (fn)-[:USES_EXTERNAL]->(m)
```

### Thay đổi trong `graph/neo4j_client.py`
Thêm index cho Module nodes vào `create_indexes()`:
```python
"CREATE INDEX node_name IF NOT EXISTS FOR (n:Module) ON (n.name)"
```

### Kết quả mong đợi
Query sau phải trả về kết quả sau khi fix:
```cypher
MATCH (f:Function {name: "process_payment"})-[:USES_EXTERNAL]->(m:Module)
RETURN m.name, m.is_external
// Expected: [{name: "stripe", is_external: true}, {name: "db", is_external: false}]
```

---

## Ưu tiên 2 — Commit → Function Changed Relationship (Blocker cho CI/CD)

### Vấn đề
`parsers/git_parser.py` và `graph/builder.py` tạo `Commit -[:MODIFIED]-> File` nhưng không
map xuống Function level. CI/CD pipeline của team test không thể biết commit nào touch function
nào → phải gen test lại toàn bộ mỗi lần có commit, rất tốn kém.

### Yêu cầu trong `parsers/git_parser.py`
Bổ sung hàm `parse_commit_diff(repo, commit)` để extract line ranges bị thay đổi trong mỗi commit.

**Output thêm vào mỗi commit dict:**
```python
{
    # ... các fields hiện tại ...
    "changed_ranges": {
        "payments/processor.py": [(45, 67), (102, 115)],  # list (start_line, end_line) bị thay đổi
        "utils/validator.py": [(12, 20)]
    }
}
```

**Logic:** Dùng `commit.diff(commit.parents[0])` để lấy unified diff, parse `@@ -x,y +a,b @@`
hunk headers để extract line ranges của phần được thêm (`+`) trong file mới.
Với initial commit (không có parent) thì lấy toàn bộ file là changed.

### Yêu cầu trong `graph/builder.py`
Bổ sung hàm `link_commits_to_functions(commits, parsed_files)` chạy sau `build_git_nodes()`:

**Logic:**
1. Với mỗi commit, với mỗi file trong `changed_ranges`:
2. Query Neo4j tìm tất cả Function/Class nodes trong file đó
3. Với mỗi node, kiểm tra nếu `node.start_line` đến `node.end_line` overlap với bất kỳ range nào trong `changed_ranges[file]`
4. Nếu overlap → tạo relationship:

```cypher
MATCH (c:Commit {hash: $hash})
MATCH (f:Function {name: $func_name, file: $file_path})
MERGE (c)-[:CHANGED {
    lines_added: $lines_added,
    lines_removed: $lines_removed,
    date: $date
}]->(f)
```

**Overlap condition:** `not (node.end_line < range_start or node.start_line > range_end)`

### Thay đổi trong `main.py`
Trong `run_full_pipeline()`, sau `build_git_nodes(commits)`, thêm:
```python
from graph.builder import link_commits_to_functions
link_commits_to_functions(commits, parsed_files)
```

### Thay đổi trong `updater/git_hook.py`
Sau khi `build_git_nodes(commits)`, gọi thêm `link_commits_to_functions()` với commit mới nhất
và parsed files của những file bị thay đổi.

### Kết quả mong đợi
Query sau phải hoạt động:
```cypher
MATCH (c:Commit {hash: "abc123"})-[:CHANGED]->(f:Function)
RETURN f.name, f.file
// CI/CD pipeline của team test dùng query này để biết gen test cho function nào
```

---

## Ưu tiên 3 — Structured `test_recommendations` Schema (Blocker cho CI/CD)

### Vấn đề
`extractors/testing_enricher.py` lưu `test_recommendations` vào Neo4j nhưng không enforce schema.
LLM đôi khi trả về JSON array, đôi khi plain string. CI/CD pipeline parse field này sẽ crash
không báo trước.

### Yêu cầu trong `extractors/testing_enricher.py`
Thêm hàm `_parse_test_recommendations(raw)` để normalize output về schema chuẩn trước khi lưu:

**Target schema (luôn là JSON array):**
```json
[
  {
    "type": "mock",
    "target": "stripe.charge.create",
    "reason": "External payment API, must not call in tests"
  },
  {
    "type": "test_case",
    "name": "valid_payment_success",
    "path": "happy",
    "description": "Card valid, amount positive, expect charge object returned"
  },
  {
    "type": "test_case",
    "name": "invalid_card_number",
    "path": "error",
    "description": "Card number fails validation, expect ValueError raised"
  }
]
```

**Logic normalize:**
- Nếu `raw` là valid JSON array với đúng schema → giữ nguyên
- Nếu `raw` là plain string → wrap thành `[{"type": "note", "description": raw}]`
- Nếu `raw` là JSON object (không phải array) → wrap thành array `[raw]`
- Nếu parse fail → trả về `[]`

Sau khi normalize, serialize thành JSON string trước khi lưu vào Neo4j (vì Neo4j không store
native arrays of objects).

### Thay đổi prompt trong testing_enricher.py
Cập nhật system prompt để LLM luôn trả về đúng schema. Thêm vào prompt:

```
CRITICAL: test_recommendations MUST be a JSON array. Each item must have:
- "type": either "mock" or "test_case"
- If "mock": fields "target" (exact import path) and "reason"
- If "test_case": fields "name", "path" (happy/error/edge), "description"
Never return a plain string for test_recommendations.
```

### Thêm validation helper trong `graph/neo4j_client.py`
Bổ sung method `get_functions_for_testing(file_path=None)` trả về enriched functions
với `test_recommendations` đã được parse lại thành Python list:

```python
def get_functions_for_testing(self, file_path=None):
    query = """
        MATCH (f:Function)
        WHERE f.how_it_works IS NOT NULL
        {}
        RETURN f
    """.format("AND f.file = $file_path" if file_path else "")
    
    results = self.run(query, {"file_path": file_path} if file_path else {})
    functions = []
    for r in results:
        fn = dict(r["f"])
        # Parse test_recommendations về list
        try:
            recs = json.loads(fn.get("test_recommendations", "[]"))
            fn["test_recommendations"] = recs if isinstance(recs, list) else [recs]
        except:
            fn["test_recommendations"] = []
        functions.append(fn)
    return functions
```

---

## Ưu tiên 4 — Pipeline Resumable & Sync Check

### Vấn đề
Nếu `main.py` crash ở bước 6/9, các bước trước đó phải chạy lại từ đầu. Neo4j và ChromaDB
có thể bị lệch nhau nếu một bên update còn bên kia chưa.

### Yêu cầu: Progress Tracking
Tạo file `graph/progress.py` để track pipeline state:

```python
import json, os

PROGRESS_FILE = ".graphrag_progress.json"

def get_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {}

def mark_done(step: str, metadata: dict = None):
    progress = get_progress()
    progress[step] = {"done": True, "timestamp": ..., **(metadata or {})}
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)

def is_done(step: str):
    return get_progress().get(step, {}).get("done", False)

def reset_progress():
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
```

Trong `main.py`, wrap mỗi bước:
```python
if not is_done("step_3_parse"):
    parsed_files = parse_codebase(CODEBASE_PATH)
    # ...
    mark_done("step_3_parse", {"file_count": len(parsed_files)})
else:
    print("[3/9] Skipping parse (already done). To re-run: delete .graphrag_progress.json")
```

### Yêu cầu: Neo4j + ChromaDB Sync Check
Thêm hàm `check_sync()` trong `embeddings/chroma_client.py`:

```python
def check_sync():
    """Kiểm tra xem ChromaDB có bị lệch với Neo4j không."""
    from graph.neo4j_client import get_client
    neo4j_client = get_client()
    
    neo4j_count = neo4j_client.run("MATCH (n:Function) RETURN count(n) as c")[0]["c"]
    chroma_count = collection.count()
    
    if abs(neo4j_count - chroma_count) > neo4j_count * 0.1:  # lệch > 10%
        print(f"WARNING: Neo4j has {neo4j_count} functions but ChromaDB has {chroma_count} embeddings.")
        print("Run embed_all_nodes() to re-sync.")
        return False
    return True
```

Gọi `check_sync()` khi FastAPI server khởi động.

---

## Ưu tiên 5 — Health Check Endpoint

### Vấn đề
Team test không có cách biết graph đang ở version nào, khi nào được update lần cuối,
có đang consistent không.

### Yêu cầu trong `visualization/backend/api.py`
Thêm endpoint `GET /health`:

```python
@app.get("/health")
def health_check():
    from graph.neo4j_client import get_client
    from embeddings.chroma_client import collection, check_sync
    import json
    from datetime import datetime
    
    client = get_client()
    
    stats = client.run("""
        MATCH (f:Function) WITH count(f) as total_functions
        MATCH (f2:Function) WHERE f2.how_it_works IS NOT NULL
        WITH total_functions, count(f2) as enriched_functions
        MATCH (c:Commit) WITH total_functions, enriched_functions, max(c.date) as last_commit
        RETURN total_functions, enriched_functions, last_commit
    """)[0]
    
    # Đọc version từ progress file
    try:
        with open(".graphrag_progress.json") as f:
            progress = json.load(f)
        last_updated = progress.get("step_9_done", {}).get("timestamp", "unknown")
    except:
        last_updated = "unknown"
    
    return {
        "status": "ok",
        "last_updated": last_updated,
        "last_commit_indexed": stats["last_commit"],
        "total_functions": stats["total_functions"],
        "enriched_functions": stats["enriched_functions"],
        "enrichment_coverage": f"{stats['enriched_functions'] / max(stats['total_functions'], 1) * 100:.1f}%",
        "chroma_synced": check_sync(),
        "neo4j_connected": True,
    }
```

---

## Ưu tiên 6 — Fix Hardcode & Credentials

### Fix hardcode path trong `main.py`
Dòng 113-114 đang hardcode `D:\\GraphRAG`. Thay bằng:
```python
project_root = os.path.dirname(os.path.abspath(__file__))
print(f" cd {project_root}")
```

### Fix credentials
Trong `.env.example`, thêm comment rõ ràng:
```env
# QUAN TRỌNG: Đổi password mặc định trước khi share với team
NEO4J_PASSWORD=your_strong_password_here
# Không commit file .env thật lên git
```

Trong `docker-compose.yml`, đổi thành đọc từ env variable:
```yaml
environment:
  NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-changeme}
```

---

## Ưu tiên 7 — README.md

Tạo file `README.md` ở root với các sections:

1. **What is this** — 2-3 câu mô tả GraphRAG system
2. **Prerequisites** — Docker, Python 3.10+, Node.js 18+
3. **Quick Start** — copy `.env.example`, điền key, chạy `python main.py`
4. **Architecture** — link đến `architecture.md`
5. **Team Usage** — hướng dẫn trỏ `.env` vào shared server
6. **Updating the Graph** — ai có quyền chạy lại pipeline, workflow khi merge vào main

---

## Checklist sau khi implement

Sau mỗi fix, verify bằng các Cypher queries sau:

```cypher
-- Fix 1: IMPORTS
MATCH (f:Function)-[:USES_EXTERNAL]->(m:Module {is_external: true})
RETURN f.name, m.name LIMIT 10
-- Phải có kết quả

-- Fix 2: Commit → Function  
MATCH (c:Commit)-[:CHANGED]->(f:Function)
RETURN c.hash, f.name, f.file LIMIT 10
-- Phải có kết quả

-- Fix 3: test_recommendations schema
MATCH (f:Function) WHERE f.test_recommendations IS NOT NULL
RETURN f.name, f.test_recommendations LIMIT 5
-- test_recommendations phải parse được thành JSON array

-- Fix 5: Health check
-- GET http://localhost:8080/health
-- Phải trả về JSON với tất cả fields
```

---

## Notes cho AI agent implement

- Đọc kỹ `architecture.md` và `graphrag-level3-guide.md` trong repo trước khi bắt đầu.
- Tree-Sitter đã được import sẵn trong `ast_parser.py`, không cần cài thêm.
- `_normalize_property()` trong `testing_enricher.py` đã xử lý serialization an toàn, dùng lại hàm đó.
- Tất cả changes phải backward compatible — không xóa fields hiện có trong Neo4j schema.
- Với Fix 2, cẩn thận với commit không có parent (initial commit) — handle `IndexError`.
- Implement Fix 1 và Fix 2 trước, test chạy được, rồi mới làm Fix 3 trở đi.
