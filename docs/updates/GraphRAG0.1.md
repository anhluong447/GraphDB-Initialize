Đây là review chi tiết:

---

## Code Review — GraphDB-Initialize

### Điểm mạnh trước

Code sạch, có structure rõ ràng, error handling đầy đủ ở extractor, batch embedding dùng `embed_texts` thay vì loop từng cái — những thứ này đúng hướng. Label sanitization trong `build_semantic_nodes` cũng là một detail tốt để tránh Cypher injection.

---

### Vấn đề 1 — `embed_all_nodes` tốn N×2 query Neo4j cho mỗi node

**File:** `embeddings/embedder.py` — `build_node_text()`

Với mỗi node, hàm này gọi 2 query Neo4j riêng biệt để lấy outgoing và incoming relations. Nếu có 500 nodes thì pipeline chạy 1000 round-trips vào Neo4j. Đây là bottleneck lớn nhất về tốc độ.

```python
# Hiện tại: 2 query × N nodes = 1000 round-trips
result = client.run("MATCH (n)-[r]->(neighbor)...", {"name": name})
result2 = client.run("MATCH (neighbor)-[r]->(n)...", {"name": name})
```

**Fix:** Gộp cả hai query thành một, hoặc tốt hơn là query một lần lấy tất cả relations của tất cả nodes rồi group trong Python:

```python
# Một query lấy toàn bộ, group trong Python
all_relations = client.run("""
    MATCH (a)-[r]->(b)
    WHERE a.name IS NOT NULL AND b.name IS NOT NULL
    RETURN a.name as from_name, type(r) as rel, b.name as to_name
""")
# Build dict: name -> {outgoing: [...], incoming: [...]}
# Sau đó build_node_text chỉ cần lookup dict, không query nữa
```

---

### Vấn đề 2 — `main.py` hard-limit 50 files cho LLM extraction

**File:** `main.py` line 57

```python
for pf in parsed_files[:50]:  # limit 50 files to save API cost
```

Với dự án lớn hơn, bạn sẽ bị miss toàn bộ semantic graph của phần còn lại. Thay vì hard-limit theo số file, nên filter theo **độ phức tạp thực sự** của file:

```python
# Chỉ gửi LLM file có > 50 lines và chứa business logic
significant_files = [
    pf for pf in parsed_files
    if len(pf.get("nodes", [])) >= 3  # có ít nhất 3 function/class
    and len(pf.get("raw_code", "")) >= 300  # không phải file rỗng
]
```

---

### Vấn đề 3 — Watcher re-embed toàn bộ nodes khi 1 file thay đổi

**File:** `updater/watcher.py` — `_reindex_files()`

```python
def _reindex_files(self, files: list[str]):
    parsed = [parse_file(f) for f in files]
    build_file_nodes(parsed)
    embed_all_nodes()  # ← re-embed TẤT CẢ nodes trong DB
```

`embed_all_nodes()` re-embed toàn bộ graph, không chỉ nodes từ file vừa đổi. Với graph 500+ nodes, mỗi lần save file sẽ trigger hàng trăm embedding API calls.

**Fix:** Chỉ re-embed nodes thuộc file vừa thay đổi:

```python
def _reindex_files(self, files: list[str]):
    parsed = [p for p in [parse_file(f) for f in files] if p]
    if not parsed:
        return
    build_file_nodes(parsed)

    # Chỉ embed nodes của file vừa thay đổi
    changed_file_paths = [p["file"] for p in parsed]
    embed_nodes_for_files(changed_file_paths)  # hàm mới cần thêm vào chroma_client.py
```

---

### Vấn đề 4 — `/graph/full` limit edges bất đối xứng với nodes

**File:** `visualization/backend/api.py`

```python
nodes_result = client.run("... LIMIT $limit", {"limit": limit})          # 200 nodes
edges_result = client.run("... LIMIT $limit", {"limit": limit * 3})      # 600 edges
```

Nếu graph có 1000 nodes nhưng chỉ lấy 200, việc lấy 600 edges sẽ trả về nhiều edges trỏ đến nodes không tồn tại trong response — đây là nguyên nhân gây "dangling connections" trong visualization mà architecture.md đã nhắc đến. Cần filter edges chỉ giữ những cái có cả source và target đều nằm trong tập nodes đã lấy:

```python
@app.get("/graph/full")
def get_full_graph(limit: int = 200):
    nodes_result = client.run("MATCH (n) WHERE n.name IS NOT NULL RETURN id(n) as id, ... LIMIT $limit", {"limit": limit})
    node_ids = {str(n["id"]) for n in nodes_result}

    edges_result = client.run("MATCH (a)-[r]->(b) WHERE a.name IS NOT NULL AND b.name IS NOT NULL RETURN id(a) as source, id(b) as target, type(r) as label LIMIT $limit", {"limit": limit * 5})

    # Filter chỉ giữ edges có cả hai đầu trong tập nodes
    valid_edges = [e for e in edges_result if str(e["source"]) in node_ids and str(e["target"]) in node_ids]

    return {"nodes": list(nodes_result), "edges": valid_edges}
```

---

### Vấn đề 5 — `_expand_neighbors` dùng `r*1..2` không có giới hạn relation type

**File:** `query/engine.py`

```cypher
MATCH (n)-[r*1..2]-(neighbor)
```

Query này traverse theo **tất cả** relation types, kể cả `BELONGS_TO` (community membership). Kết quả là khi expand neighbors của một function, nó sẽ kéo theo cả community node và từ community đó kéo thêm tất cả members khác — graph explosion tiềm ẩn.

**Fix:** Whitelist relation types được phép traverse:

```cypher
MATCH (n)-[r:CALLS|IMPLEMENTS|DEPENDS_ON|RELATES_TO|CONTAINS*1..2]-(neighbor)
WHERE neighbor.name IS NOT NULL AND NOT neighbor:Community
RETURN DISTINCT neighbor.name as name, ...
LIMIT 10
```

---

### Vấn đề nhỏ — `infer_community_name` gọi LLM riêng

**File:** `community/summarizer.py`

Mỗi community gọi 2 LLM requests: một để summarize, một để đặt tên. Gộp lại thành một request tiết kiệm được ~50% LLM calls ở bước này:

```python
prompt = """...Summarize this community in 2-3 sentences.
Then on the last line, write: NAME: <2-4 word name>"""

# Parse response: tách summary và name từ một response
```

---

### Tóm tắt ưu tiên fix

|     | Vấn đề                         | Impact            |
| --- | ------------------------------ | ----------------- |
| 🔴   | Watcher re-embed toàn bộ       | Cost/tốc độ       |
| 🔴   | `build_node_text` 2 query/node | Tốc độ pipeline   |
| 🟡   | Hard-limit 50 files            | Chất lượng graph  |
| 🟡   | Dangling edges trong viz       | UI crash          |
| 🟡   | Graph explosion trong expand   | Query correctness |
| 🟢   | Gộp 2 LLM calls community      | Cost nhỏ          |