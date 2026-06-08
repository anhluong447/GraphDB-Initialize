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

