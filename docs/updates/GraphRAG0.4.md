# Fix Plan — PHP Parser + Loại bỏ API Server

> 2 fix độc lập. Implement Fix 1 trước, test xong rồi làm Fix 2.

---

## FIX 1 — Thay PHP Regex Parser bằng Tree-Sitter + Filter noise

### Vấn đề hiện tại

`_parse_php_file_regex()` trong `parsers/ast_parser.py` dùng regex để parse PHP.
Kết quả là lấy vào graph cả những function không có giá trị test như:
- `getRow`, `setName`, `getId` — getter/setter 1-2 dòng
- `formatDate`, `toArray` — utility đơn giản, complexity = 1
- `__toString`, `__get` — PHP magic methods không cần test

Nguyên nhân: regex không hiểu cấu trúc code, không tính được complexity thật sự,
không biết function nào trivial.

---

### Bước 1 — Thêm dependency

Trong `requirements.txt`, thêm dòng:

```
tree-sitter-php
```

---

### Bước 2 — Thêm PHP Language vào LANGUAGE_MAP trong `parsers/ast_parser.py`

Tìm đoạn khai báo các language ở đầu file (chỗ có `PY_LANGUAGE`, `JS_LANGUAGE`,
`TS_LANGUAGE`) và thêm vào:

```python
import tree_sitter_php as tsphp
PHP_LANGUAGE = Language(tsphp.language_php())
```

Trong dict `LANGUAGE_MAP`, thêm:

```python
LANGUAGE_MAP = {
    "python": PY_LANGUAGE,
    "javascript": JS_LANGUAGE,
    "typescript": TS_LANGUAGE,
    "php": PHP_LANGUAGE,       # THÊM DÒNG NÀY
}
```

---

### Bước 3 — Thêm hàm helper tính complexity cho PHP AST node

Thêm hàm này vào `parsers/ast_parser.py`, đặt trước hàm `_parse_php_file_regex`:

```python
# Node types trong PHP AST làm tăng complexity
_PHP_COMPLEXITY_NODES = {
    "if_statement",
    "elseif_clause",
    "else_clause",
    "foreach_statement",
    "for_statement",
    "while_statement",
    "do_statement",
    "switch_statement",
    "case_statement",
    "catch_clause",
    "conditional_expression",   # ternary operator
    "match_expression",
    "null_safe_member_access_expression",
}

def _calc_php_complexity(node) -> int:
    """
    Tính cyclomatic complexity của 1 PHP AST node.
    Đếm số nhánh logic (if, foreach, while, catch...) + 1.
    """
    count = 1
    def traverse(n):
        if n.type in _PHP_COMPLEXITY_NODES:
            nonlocal count
            count += 1
        for child in n.children:
            traverse(child)
    traverse(node)
    return count
```

---

### Bước 4 — Thêm hàm `_parse_php_file_treesitter()` mới

Thêm hàm này vào `parsers/ast_parser.py`, đặt ngay sau hàm
`_calc_php_complexity()` vừa thêm:

```python
# PHP function/method names bị skip dù có complexity cao
# (magic methods không cần test, hoặc quá generic)
_PHP_SKIP_NAMES = {
    "__construct", "__destruct", "__clone",
    "__sleep", "__wakeup", "__serialize", "__unserialize",
    "__invoke", "__debugInfo",
    # generic getters/setters — thường trivial
    "getRow", "getRows", "getResult",
}


def _parse_php_file_treesitter(file_path: str, source_bytes: bytes) -> dict:
    """
    Parse PHP file using Tree-Sitter for accurate AST.
    Filters out trivial functions (complexity=1, line_count<4).
    """
    try:
        PHP_LANGUAGE = LANGUAGE_MAP["php"]
    except KeyError:
        # Fallback nếu PHP_LANGUAGE chưa được khởi tạo
        import tree_sitter_php as tsphp
        PHP_LANGUAGE = Language(tsphp.language_php())

    parser = Parser(PHP_LANGUAGE)
    tree = parser.parse(source_bytes)
    code = source_bytes.decode("utf-8", errors="ignore")
    lines = code.splitlines()

    nodes = []
    imports = []
    current_class = None

    # --- FILTER THRESHOLDS ---
    MIN_LINES = 4         # function phải có ít nhất 4 dòng
    MIN_COMPLEXITY = 2    # phải có ít nhất 1 nhánh logic (if/foreach/...)

    def get_line(node_obj):
        return node_obj.start_point[0] + 1  # 1-indexed

    def get_text(node_obj):
        return node_obj.text.decode("utf-8", errors="ignore").strip()

    def extract_params(params_node):
        """Extract parameter list từ AST node."""
        inputs = []
        if params_node is None:
            return inputs
        for child in params_node.children:
            if child.type in ("simple_parameter", "variadic_parameter",
                              "property_promotion_parameter"):
                param_name = ""
                param_type = ""
                for sub in child.children:
                    if sub.type == "variable_name":
                        param_name = get_text(sub)
                    elif sub.type in ("named_type", "union_type",
                                      "nullable_type", "intersection_type"):
                        param_type = get_text(sub)
                if param_name:
                    inputs.append({"name": param_name, "type": param_type})
        return inputs

    def extract_calls(func_node):
        """Extract function/method calls bên trong body của function."""
        calls = set()
        def walk(n):
            if n.type in ("function_call_expression", "method_call_expression",
                          "static_method_call_expression"):
                for child in n.children:
                    if child.type == "name":
                        calls.add(get_text(child))
            for c in n.children:
                walk(c)
        walk(func_node)
        return list(calls)

    def extract_imports_from_use(node_obj):
        """Extract use statements (imports)."""
        for child in node_obj.children:
            if child.type == "namespace_use_declaration":
                for clause in child.children:
                    if clause.type == "namespace_use_clause":
                        full_path = get_text(clause)
                        parts = full_path.split("\\")
                        root_mod = parts[0] if parts else ""
                        imports.append({
                            "module": root_mod,
                            "full_path": full_path,
                            "alias": "",
                            "names": [parts[-1]] if parts else [],
                            "is_external": True,
                            "is_stdlib": False,
                            "source_file": file_path,
                        })

    def process_function(func_node, class_name=None):
        """Process 1 function/method node, apply filters, add to nodes list."""
        func_name = ""
        params_node = None
        visibility = "public"
        is_static = False
        return_type = ""

        for child in func_node.children:
            if child.type == "name":
                func_name = get_text(child)
            elif child.type == "formal_parameters":
                params_node = child
            elif child.type in ("public", "protected", "private"):
                visibility = child.type
            elif child.type == "static":
                is_static = True
            elif child.type == "named_type":
                return_type = get_text(child)

        if not func_name:
            return

        # Skip nếu trong danh sách đen
        if func_name in _PHP_SKIP_NAMES:
            return

        start_line = get_line(func_node)
        end_line = func_node.end_point[0] + 1
        line_count = end_line - start_line + 1
        complexity = _calc_php_complexity(func_node)

        # FILTER: bỏ qua function quá đơn giản
        if line_count < MIN_LINES or complexity < MIN_COMPLEXITY:
            return

        # Build anchor (dòng đầu tiên của function)
        anchor = lines[start_line - 1].strip() if start_line <= len(lines) else ""

        # Parse inputs
        inputs = extract_params(params_node)

        # Extract calls
        calls = extract_calls(func_node)

        nodes.append({
            "type": "method_definition" if class_name else "function_definition",
            "name": func_name,
            "file": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "anchor": anchor,
            "calls": calls,
            "parent": class_name,
            "is_async": False,
            "visibility": visibility,
            "class_name": class_name,
            "docstring": "",
            "inputs": json.dumps(inputs),
            "output": return_type,
            "raises": "[]",
            "complexity": complexity,
            "annotations": "[]",
        })

    def walk_tree(node_obj, class_ctx=None):
        nonlocal current_class

        if node_obj.type == "class_declaration":
            # Extract class name
            cls_name = ""
            for child in node_obj.children:
                if child.type == "name":
                    cls_name = get_text(child)
                    break
            if cls_name:
                # Add class node (không filter class)
                start_line = get_line(node_obj)
                end_line = node_obj.end_point[0] + 1
                anchor = lines[start_line - 1].strip() if start_line <= len(lines) else ""
                nodes.append({
                    "type": "class_definition",
                    "name": cls_name,
                    "file": file_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "anchor": anchor,
                    "calls": [],
                    "parent": None,
                    "is_async": False,
                    "visibility": "public",
                    "class_name": None,
                    "docstring": "",
                    "inputs": "[]",
                    "output": "",
                    "raises": "[]",
                    "complexity": 1,
                    "annotations": "[]",
                })
                current_class = cls_name
                for child in node_obj.children:
                    walk_tree(child, class_ctx=cls_name)
                current_class = None
                return

        elif node_obj.type in ("function_definition", "method_declaration"):
            process_function(node_obj, class_name=class_ctx)
            return  # Không walk sâu vào bên trong function

        elif node_obj.type == "namespace_use_declaration":
            extract_imports_from_use(node_obj.parent or node_obj)

        for child in node_obj.children:
            walk_tree(child, class_ctx=class_ctx)

    walk_tree(tree.root_node)

    return {
        "file": file_path,
        "language": "php",
        "nodes": nodes,
        "imports": imports,
        "raw_code": code,
    }
```

---

### Bước 5 — Đổi routing trong `parse_file()`

Tìm đoạn sau trong hàm `parse_file()`:

```python
# Handle PHP via Regex parser fallback
if lang_name == "php":
    return _parse_php_file_regex(file_path, source_bytes)
```

Thay bằng:

```python
# Handle PHP via Tree-Sitter (accurate AST + noise filtering)
if lang_name == "php":
    return _parse_php_file_treesitter(file_path, source_bytes)
```

---

### Bước 6 — Giữ nguyên `_parse_php_file_regex()` (không xóa)

Đổi tên thành `_parse_php_file_regex_DEPRECATED()` để tham khảo,
không xóa vì có thể cần rollback.

---

### Verify Fix 1

Chạy lệnh sau trên 1 PHP file thật trong codebase target:

```python
from parsers.ast_parser import parse_file

result = parse_file("path/to/SomeController.php")
print(f"Functions found: {len(result['nodes'])}")
for n in result['nodes']:
    print(f"  {n['name']} — complexity={n['complexity']}, lines={n['end_line']-n['start_line']}")
```

Kết quả mong đợi:
- Không còn `getRow`, `setName`, `getId`, `toArray` trong danh sách
- Chỉ còn functions có logic thật (if/foreach/try-catch...)
- Số nodes giảm 40-60% so với regex parser

---

---

## FIX 2 — Loại bỏ API Server, thay bằng Python Module Interface

### Vấn đề hiện tại

Hệ thống đang expose REST API qua FastAPI + ngrok để team test gen gọi vào.
Đây là over-engineering khi cả 2 systems sẽ chạy cùng nhau trên 1 server cloud.
Gọi HTTP giữa 2 process trên cùng máy là không cần thiết.

---

### Bước 1 — Xóa các file API server

Xóa hoàn toàn các file sau:

```
server/api.py           ← toàn bộ REST API endpoints
server/pipeline.py      ← async pipeline runner cho API
server/state.py         ← state manager cho API (FIRST_RUN/ONGOING)
server/__init__.py
start_server.py         ← uvicorn entry point
guides/ADMIN_GUIDE.md   ← hướng dẫn setup server
guides/CLIENT_API_GUIDE.md  ← hướng dẫn gọi API
```

Nếu muốn giữ lại để tham khảo sau, move vào folder `_archive/` thay vì xóa.

---

### Bước 2 — Xóa dependencies không cần thiết trong `requirements.txt`

Xóa các dòng sau:

```
fastapi          ← không cần nữa
uvicorn          ← không cần nữa
```

Giữ lại tất cả các dòng khác.

---

### Bước 3 — Dọn dẹp config trong `config.py`

Tìm và xóa các config liên quan đến server:

```python
# Xóa các dòng này trong config.py:
API_KEY = os.getenv("API_KEY", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
SERVER_MODE = os.getenv("SERVER_MODE", "false").lower() == "true"
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "./workspace")
API_BASE_URL = os.getenv("API_BASE_URL", "")
```

---

### Bước 4 — Dọn dẹp `.env.example`

Xóa các dòng sau trong `.env.example`:

```env
SERVER_MODE=false
API_KEY=
WEBHOOK_URL=
WORKSPACE_DIR=./workspace
API_BASE_URL=https://...ngrok...
```

---

### Bước 5 — Tạo file `knowledge_base.py` ở root

Đây là Python interface thay thế cho REST API.
Team test gen import trực tiếp từ file này, không cần HTTP gì cả.

Tạo file `/knowledge_base.py`:

```python
"""
GraphRAG Knowledge Base — Python Interface

Team test gen dùng file này để truy cập graph trực tiếp.
Không cần HTTP, không cần server, không cần port.

Usage:
    from knowledge_base import get_function_context, get_snapshot, get_changes, mark_tested
"""

import json
from graph.neo4j_client import get_client


def get_function_context(function_name: str) -> dict:
    """
    Lấy full context của 1 function để gen test.

    Returns:
        {
            "function": { name, file, how_it_works, input_spec, output_spec,
                          edge_cases, test_recommendations, complexity,
                          source_code },
            "community": { id, name, summary },
            "calls_outside": [ {name, file} ],   # functions được gọi
            "called_by":    [ {name, file} ],   # functions gọi vào đây
        }
    """
    client = get_client()

    result = client.run("""
        MATCH (f:Function {name: $name})
        OPTIONAL MATCH (f)-[:BELONGS_TO]->(c:Community)
        RETURN f, c.id as cid, c.name as cname, c.summary as csummary
        LIMIT 1
    """, {"name": function_name})

    if not result:
        return {}

    record = result[0]
    func_data = dict(record["f"])

    # Đọc source code từ file thật (dùng start_line/end_line/anchor)
    func_data["source_code"] = client.read_node_code(func_data)

    # Parse JSON fields
    for field in ["test_recommendations", "inputs", "raises", "edge_cases", "annotations"]:
        val = func_data.get(field)
        if isinstance(val, str):
            try:
                func_data[field] = json.loads(val)
            except Exception:
                pass

    community = None
    if record["cid"] is not None:
        community = {
            "id": record["cid"],
            "name": record["cname"],
            "summary": record["csummary"],
        }

    calls_outside = client.run("""
        MATCH (f:Function {name: $name})-[:CALLS]->(callee)
        WHERE callee.name IS NOT NULL
        RETURN callee.name as name, callee.file as file
    """, {"name": function_name})

    called_by = client.run("""
        MATCH (caller)-[:CALLS]->(f:Function {name: $name})
        WHERE caller.name IS NOT NULL
        RETURN caller.name as name, caller.file as file
    """, {"name": function_name})

    return {
        "function": func_data,
        "community": community,
        "calls_outside": [dict(r) for r in calls_outside],
        "called_by": [dict(r) for r in called_by],
    }


def get_snapshot() -> dict:
    """
    Lấy toàn bộ functions hiện tại, nhóm theo community, kèm priority score.
    Dùng cho first run — biết toàn bộ codebase cần gen test gì.

    priority_score = complexity*0.3 + in_degree*0.4 + commit_count*0.3
    """
    client = get_client()

    functions = client.run("""
        MATCH (f:Function)
        WHERE f.file IS NOT NULL AND f.name IS NOT NULL
        OPTIONAL MATCH (f)-[:BELONGS_TO]->(c:Community)
        WITH f, c,
             size([(caller:Function)-[:CALLS]->(f) | caller]) as in_degree,
             size([(commit:Commit)-[:CHANGED]->(f) | commit]) as commit_count
        RETURN f.name as name,
               f.file as file,
               f.class_name as class_name,
               coalesce(f.complexity, 1) as complexity,
               in_degree,
               commit_count,
               coalesce(f.has_test, false) as has_test,
               c.id as community_id,
               c.name as community_name,
               c.summary as community_summary
        ORDER BY community_id, name
    """)

    communities_map = {}
    uncategorized = {"id": -1, "name": "Uncategorized", "summary": "", "functions": []}

    for r in functions:
        complexity = r["complexity"] or 1
        in_degree = r["in_degree"] or 0
        commit_count = r["commit_count"] or 0
        priority_score = round(complexity * 0.3 + in_degree * 0.4 + commit_count * 0.3, 1)

        func_data = {
            "name": r["name"],
            "file": r["file"],
            "class_name": r["class_name"],
            "complexity": complexity,
            "priority_score": priority_score,
            "has_test": r["has_test"] or False,
        }

        cid = r["community_id"]
        if cid is not None:
            if cid not in communities_map:
                communities_map[cid] = {
                    "id": cid,
                    "name": r["community_name"] or f"Community {cid}",
                    "summary": r["community_summary"] or "",
                    "functions": [],
                }
            communities_map[cid]["functions"].append(func_data)
        else:
            uncategorized["functions"].append(func_data)

    for comm in communities_map.values():
        comm["functions"].sort(key=lambda f: f["priority_score"], reverse=True)

    communities_list = sorted(communities_map.values(), key=lambda c: c["id"])
    if uncategorized["functions"]:
        communities_list.append(uncategorized)

    return {
        "total": sum(len(c["functions"]) for c in communities_list),
        "communities": communities_list,
    }


def get_changes(commit_hash: str) -> dict:
    """
    Lấy danh sách functions bị thay đổi trong 1 commit.
    Dùng cho ongoing mode sau mỗi git push.

    Returns:
        {
            "commit": "abc123",
            "changed_functions": [ {name, file, complexity, has_test} ],
            "affected_services": [ {id, name} ],
            "risk_level": "low|medium|high"
        }
    """
    client = get_client()

    result = client.run("""
        MATCH (c:Commit)-[:CHANGED]->(f:Function)
        WHERE c.hash STARTS WITH $hash
        RETURN f.name as name,
               f.file as file,
               coalesce(f.complexity, 1) as complexity,
               coalesce(f.has_test, false) as has_test
    """, {"hash": commit_hash})

    changed = [dict(r) for r in result]

    max_complexity = max((f["complexity"] for f in changed), default=1)
    risk_level = "high" if max_complexity >= 10 else "medium" if max_complexity >= 5 else "low"

    affected = []
    if changed:
        names = [f["name"] for f in changed]
        comm_result = client.run("""
            MATCH (f:Function)-[:BELONGS_TO]->(c:Community)
            WHERE f.name IN $names
            RETURN DISTINCT c.id as id, c.name as name
        """, {"names": names})
        affected = [dict(r) for r in comm_result]

    return {
        "commit": commit_hash,
        "changed_functions": changed,
        "affected_services": affected,
        "risk_level": risk_level,
    }


def mark_tested(function_name: str, file: str = None) -> bool:
    """
    Đánh dấu function đã có test (has_test = true).
    Gọi sau khi gen test xong và test pass.

    Returns: True nếu thành công, False nếu không tìm thấy function.
    """
    client = get_client()

    if file:
        result = client.run("""
            MATCH (f:Function {name: $name, file: $file})
            SET f.has_test = true
            RETURN f.name
        """, {"name": function_name, "file": file})
    else:
        result = client.run("""
            MATCH (f:Function {name: $name})
            SET f.has_test = true
            RETURN f.name
        """, {"name": function_name})

    return len(result) > 0


def search(query_text: str, top_k: int = 10) -> list[dict]:
    """
    Semantic search trong graph.
    Tìm functions/nodes liên quan đến query bằng vector similarity.

    Returns: list of { name, file, type, score, description }
    """
    from embeddings.chroma_client import semantic_search
    return semantic_search(query_text, top_k=top_k)


def run_init(codebase_path: str = None):
    """
    Chạy full initialization pipeline.
    Nếu không truyền path, dùng CODEBASE_PATH trong .env.
    """
    if codebase_path:
        import os
        os.environ["CODEBASE_PATH"] = codebase_path
    from initialize_graph import run_full_init
    run_full_init()


def run_sync():
    """Chạy incremental sync dựa trên git diff."""
    from initialize_graph import run_incremental_sync
    run_incremental_sync()
```

---

### Bước 6 — Cập nhật `guides/` thành 1 file duy nhất

Xóa `ADMIN_GUIDE.md` và `CLIENT_API_GUIDE.md`.
Tạo `guides/USAGE.md`:

```markdown
# GraphRAG Knowledge Base — Hướng dẫn sử dụng

## Setup

1. Copy `.env.example` → `.env`, điền `OPENROUTER_API_KEY`
2. Đảm bảo Docker đang chạy (Neo4j + ChromaDB)
3. Cài dependencies: `pip install -r requirements.txt`

## Khởi tạo lần đầu

```python
from knowledge_base import run_init
run_init()  # hoặc: run_init("/path/to/codebase")
```

Hoặc chạy trực tiếp:
```bash
python initialize_graph.py
```

## Dùng trong code

```python
from knowledge_base import get_function_context, get_snapshot, get_changes, mark_tested

# Lấy context để gen test
ctx = get_function_context("processOrder")
print(ctx["function"]["how_it_works"])
print(ctx["function"]["test_recommendations"])

# Lấy toàn bộ codebase (first run)
snapshot = get_snapshot()
for community in snapshot["communities"]:
    for func in community["functions"]:
        ctx = get_function_context(func["name"])
        # ... gen test ...
        mark_tested(func["name"])

# Lấy functions thay đổi sau commit (ongoing)
changes = get_changes("abc123f")
for func in changes["changed_functions"]:
    ctx = get_function_context(func["name"])
    # ... gen/update test ...
```

## Update khi có code mới

```python
from knowledge_base import run_sync
run_sync()
```
```

---

### Verify Fix 2

```python
# Test import hoạt động không
from knowledge_base import get_snapshot, get_function_context, get_changes, mark_tested

# Test get_snapshot
snap = get_snapshot()
print(f"Total functions: {snap['total']}")

# Test get_function_context
ctx = get_function_context("somePhpFunction")
print(ctx["function"].get("how_it_works", "not enriched yet"))

# Đảm bảo không còn import fastapi hay uvicorn ở đâu
import subprocess
result = subprocess.run(
    ["grep", "-r", "fastapi\|uvicorn\|start_server", "--include=*.py", "."],
    capture_output=True, text=True
)
print("Remaining references:", result.stdout)  # Phải trống
```

---

## Thứ tự implement

```
1. Fix 1 — Bước 1-4: Thêm tree-sitter-php, hàm helper, hàm parser mới
2. Fix 1 — Bước 5-6: Đổi routing, deprecated hàm cũ
3. Verify Fix 1 trên PHP file thật
4. Fix 2 — Bước 1-2: Xóa server files và dependencies
5. Fix 2 — Bước 3-4: Dọn config và .env.example
6. Fix 2 — Bước 5: Tạo knowledge_base.py
7. Fix 2 — Bước 6: Viết lại guides
8. Verify Fix 2
```

---

## Notes cho AI agent

- Fix 1 và Fix 2 hoàn toàn độc lập, không ảnh hưởng nhau.
- Khi implement Fix 1, KHÔNG đụng vào Python/JS/TS parsers hiện tại.
- Khi implement Fix 2, KHÔNG xóa `visualization/` folder — giữ lại cho Neo4j browser UI.
- `knowledge_base.py` chỉ là thin wrapper — logic thật vẫn nằm trong
  `graph/neo4j_client.py`, `query/engine.py`, `embeddings/chroma_client.py`.
- Sau Fix 2, `server/` folder có thể giữ lại trong `_archive/` phòng khi cần API lại sau.
