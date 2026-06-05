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
