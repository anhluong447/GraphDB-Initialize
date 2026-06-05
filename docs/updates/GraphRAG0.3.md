# GraphDB Size Optimization — Fix Plan

> 3 thay đổi độc lập, implement theo thứ tự từ trên xuống.
> Mỗi thay đổi có thể test riêng trước khi làm cái tiếp theo.

---

## Fix 1 — Bỏ Document Text khỏi ChromaDB

### Vấn đề
`chroma_client.py` đang upsert với `documents=batch_docs` — lưu toàn bộ text gốc
của mỗi node vào ChromaDB. Đây là duplicate data vì Neo4j đã có rồi.
ChromaDB không cần lưu text để query, chỉ cần vector + metadata là đủ.

### Thay đổi trong `embeddings/chroma_client.py`

**Hàm `embed_nodes()` hoặc `embed_all_nodes()`:**

```python
# TRƯỚC
collection.upsert(
    ids=batch_ids,
    documents=batch_docs,     # ← xóa dòng này
    metadatas=batch_metas,
    embeddings=batch_embeds
)

# SAU
collection.upsert(
    ids=batch_ids,
    metadatas=batch_metas,
    embeddings=batch_embeds
)
```

**Hàm query (nếu có `include=["documents", ...]`):**

```python
# TRƯỚC
results = collection.query(
    query_embeddings=[query_vector],
    n_results=10,
    include=["documents", "metadatas", "distances"]
)

# SAU — bỏ "documents" khỏi include
results = collection.query(
    query_embeddings=[query_vector],
    n_results=10,
    include=["metadatas", "distances"]
)
```

Nếu code downstream cần text của node sau khi query Chroma, phải fetch lại từ
Neo4j bằng `name` trong metadata:

```python
# Sau khi query Chroma, lấy full node từ Neo4j nếu cần
for meta in results["metadatas"][0]:
    node = neo4j_client.run(
        "MATCH (n {name: $name}) RETURN n",
        {"name": meta["name"]}
    )[0]["n"]
```

### Verify
```python
# Chạy sau khi fix, collection.count() phải giữ nguyên
# nhưng dung lượng thư mục chroma_data/ phải giảm đáng kể
import os
print(f"Chroma data size: {get_dir_size('chroma_data')} MB")
```

---

## Fix 2 — Giảm Vector Dimensions từ 1536 xuống 512

### Vấn đề
`text-embedding-3-small` đang tạo vector 1536 chiều = 6KB/node.
Model này hỗ trợ Matryoshka — giảm xuống 512 chiều chỉ mất ~2% accuracy
nhưng tiết kiệm 66% storage cho vectors và HNSW index.

### Thay đổi trong `embeddings/embedder.py`

```python
# TRƯỚC
response = openai_client.embeddings.create(
    model="text-embedding-3-small",
    input=text[:8000]
)

# SAU
response = openai_client.embeddings.create(
    model="text-embedding-3-small",
    input=text[:8000],
    dimensions=512
)
```

### Thay đổi trong `embeddings/chroma_client.py`

Khi tạo collection, chỉ định đúng dimension để Chroma validate:

```python
# TRƯỚC
collection = chroma_client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}
)

# SAU
collection = chroma_client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={
        "hnsw:space": "cosine",
        "dimension": 512
    }
)
```

### Thay đổi trong `.env.example`

Thêm config để dễ điều chỉnh sau:
```env
EMBEDDING_DIMENSIONS=512
```

Và đọc trong `embedder.py`:
```python
EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMENSIONS", 512))
```

### Lưu ý quan trọng
**Phải xóa toàn bộ ChromaDB data cũ và re-embed lại từ đầu** vì vector cũ là
1536 chiều không compatible với collection mới 512 chiều.

```bash
# Trước khi chạy lại pipeline
docker compose down
rm -rf ./chroma_data/*   # hoặc path tương ứng trong docker volume
docker compose up -d
python main.py           # sẽ re-embed toàn bộ
```

---

## Fix 3 — Thay `raw_code` bằng File Position + Anchor

### Vấn đề
Mỗi Function/Class node đang lưu `raw_code` (tối đa 500-2000 chars) trực tiếp
trong Neo4j. Đây là dữ liệu nặng nhất và bị stale ngay khi có commit mới.
Thay vào đó chỉ lưu vị trí trong file + anchor signature để đọc on-demand.

---

### Bước 3a — Thay đổi schema trong `parsers/ast_parser.py`

Trong hàm parse function/class nodes, bỏ `raw_code`, thêm `start_line`,
`end_line`, và `anchor`:

```python
# TRƯỚC
def _extract_function(self, node, source_code, file_path):
    return {
        "name": ...,
        "file": file_path,
        "raw_code": source_code[node.start_byte:node.end_byte][:500],
        ...
    }

# SAU
def _extract_function(self, node, source_code, file_path):
    # Lấy dòng đầu tiên của function làm anchor
    first_line = source_code.split('\n')[node.start_point[0]].strip()

    return {
        "name": ...,
        "file": file_path,
        "start_line": node.start_point[0] + 1,   # 1-indexed
        "end_line": node.end_point[0] + 1,        # 1-indexed
        "anchor": first_line,                      # "def process_payment(card, amount):"
        # KHÔNG có raw_code
        ...
    }
```

`anchor` là dòng đầu tiên của function/class — đủ unique để tìm lại nếu
`start_line` bị stale.

---

### Bước 3b — Thêm helper `read_node_code()` trong `graph/neo4j_client.py`

Tạo hàm đọc code từ file theo position, với fallback về anchor nếu stale:

```python
def read_node_code(self, node: dict) -> str:
    """
    Đọc source code của một node từ file.
    Nếu start_line stale (anchor không khớp), tự tìm lại và update Neo4j.
    
    Args:
        node: dict chứa file, start_line, end_line, anchor, name
    Returns:
        Source code của node đó
    """
    file_path = node.get("file")
    start_line = node.get("start_line")
    end_line = node.get("end_line")
    anchor = node.get("anchor", "")
    
    if not file_path or not os.path.exists(file_path):
        return ""
    
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Kiểm tra anchor có khớp không
    actual_line = lines[start_line - 1].strip() if start_line <= len(lines) else ""
    
    if actual_line == anchor:
        # Line number còn đúng, đọc bình thường
        return "".join(lines[start_line - 1 : end_line])
    
    # Anchor không khớp — start_line đã stale, tìm lại
    new_start = None
    for i, line in enumerate(lines):
        if line.strip() == anchor:
            new_start = i + 1  # 1-indexed
            break
    
    if new_start is None:
        # Anchor không tìm thấy — function đã bị xóa hoặc rename
        return ""
    
    # Tính end_line mới dựa vào offset cũ
    offset = end_line - start_line
    new_end = new_start + offset
    
    # Update lại Neo4j
    self.run(
        """
        MATCH (n {name: $name, file: $file})
        SET n.start_line = $new_start, n.end_line = $new_end
        """,
        {
            "name": node.get("name"),
            "file": file_path,
            "new_start": new_start,
            "new_end": new_end
        }
    )
    
    return "".join(lines[new_start - 1 : new_end])
```

---

### Bước 3c — Thay đổi `graph/builder.py`

Trong hàm `build_function_nodes()` / `upsert_node()`, bỏ `raw_code` khỏi
Cypher và thêm các fields mới:

```cypher
-- TRƯỚC
MERGE (f:Function {name: $name, file: $file})
SET f.raw_code = $raw_code,
    f.inputs = $inputs,
    ...

-- SAU
MERGE (f:Function {name: $name, file: $file})
SET f.start_line = $start_line,
    f.end_line = $end_line,
    f.anchor = $anchor,
    f.inputs = $inputs,
    ...
-- KHÔNG SET raw_code
```

---

### Bước 3d — Cập nhật `embeddings/embedder.py`

`build_node_text()` cần đọc code từ file thay vì từ `raw_code` property.
Bỏ phần append raw_code vào document text (đã nói ở Fix 1):

```python
# TRƯỚC
def build_node_text(node: dict) -> str:
    text = f"{node_type}: {name}\n"
    text += f"Description: {description}\n"
    text += f"Code preview: {node.get('raw_code', '')}\n"  # ← xóa dòng này
    return text

# SAU — chỉ dùng semantic info để embed
def build_node_text(node: dict) -> str:
    text = f"{node_type}: {name}\n"
    text += f"Description: {node.get('description', '')}\n"
    text += f"How it works: {node.get('how_it_works', '')}\n"
    text += f"Inputs: {node.get('input_spec', '')}\n"
    text += f"Outputs: {node.get('output_spec', '')}\n"
    text += f"Relations: {', '.join(outgoing + incoming)}\n"
    return text
```

---

### Bước 3e — Đảm bảo re-parse khi có commit trong `updater/git_hook.py`

Đây là phần quan trọng nhất để giữ `start_line/end_line` luôn đúng.

Khi git hook detect file thay đổi, **re-parse toàn bộ file đó** (không phải
chỉ function bị sửa) vì bất kỳ thay đổi nào ở đầu file đều làm lệch line
number của tất cả functions bên dưới:

```python
def update_changed_files(changed_files: list[str]):
    """
    Re-parse và update start_line/end_line/anchor cho tất cả nodes
    trong các file bị thay đổi.
    
    Args:
        changed_files: list đường dẫn file bị thay đổi trong commit mới nhất
    """
    from parsers.ast_parser import ASTParser
    from graph.neo4j_client import get_client
    
    parser = ASTParser()
    client = get_client()
    
    for file_path in changed_files:
        if not os.path.exists(file_path):
            # File bị xóa — đánh dấu nodes là deleted thay vì xóa hẳn
            client.run(
                "MATCH (n {file: $file}) SET n.deleted = true",
                {"file": file_path}
            )
            continue
        
        # Re-parse toàn bộ file
        parsed = parser.parse_file(file_path)
        
        # Update start_line, end_line, anchor cho TẤT CẢ nodes trong file
        for fn in parsed.get("functions", []):
            client.run(
                """
                MATCH (f:Function {name: $name, file: $file})
                SET f.start_line = $start_line,
                    f.end_line = $end_line,
                    f.anchor = $anchor
                """,
                {
                    "name": fn["name"],
                    "file": file_path,
                    "start_line": fn["start_line"],
                    "end_line": fn["end_line"],
                    "anchor": fn["anchor"]
                }
            )
        
        for cls in parsed.get("classes", []):
            client.run(
                """
                MATCH (c:Class {name: $name, file: $file})
                SET c.start_line = $start_line,
                    c.end_line = $end_line,
                    c.anchor = $anchor
                """,
                {
                    "name": cls["name"],
                    "file": file_path,
                    "start_line": cls["start_line"],
                    "end_line": cls["end_line"],
                    "anchor": cls["anchor"]
                }
            )
        
        print(f"  Updated positions for {len(parsed.get('functions', []))} functions in {file_path}")
```

Gọi hàm này ngay sau bước detect changed files trong git hook:

```python
# Trong git_hook.py, sau khi lấy danh sách file thay đổi
changed_files = get_changed_files(repo, latest_commit)
update_changed_files(changed_files)  # ← thêm dòng này trước mọi thứ khác
```

---

## Thứ tự implement

```
Fix 1 (bỏ documents= trong Chroma)
    → Test: chroma_data/ size giảm
    → Không cần rebuild, chỉ cần xóa collection và re-embed

Fix 2 (giảm dims xuống 512)
    → Test: mỗi vector từ 6KB xuống 2KB
    → Cần xóa chroma_data/ và re-embed toàn bộ

Fix 3a + 3b + 3c (thay raw_code bằng position + anchor)
    → Test: Neo4j node không còn raw_code property
    → Cần chạy lại full pipeline để rebuild nodes

Fix 3d (update embedder không dùng raw_code)
    → Test: build_node_text() không còn "Code preview"

Fix 3e (re-parse khi có commit)
    → Test: thêm function vào đầu file, commit, kiểm tra
       start_line của functions bên dưới đã được update
```

---

## Verify sau khi hoàn tất

```python
# 1. Kiểm tra không còn raw_code trong Neo4j
MATCH (f:Function) WHERE f.raw_code IS NOT NULL RETURN count(f)
# Expected: 0

# 2. Kiểm tra tất cả nodes có đủ position fields
MATCH (f:Function) WHERE f.start_line IS NULL RETURN count(f)
# Expected: 0

# 3. Kiểm tra anchor hoạt động
# Lấy 1 node bất kỳ, đọc file, verify dòng start_line khớp anchor
MATCH (f:Function) RETURN f.file, f.start_line, f.anchor LIMIT 5
# Mở file, đọc dòng start_line, phải khớp với anchor

# 4. Kiểm tra ChromaDB không có documents
result = collection.get(limit=1, include=["documents"])
# Expected: result["documents"] là [[]] hoặc [None]

# 5. Kiểm tra vector dimension
result = collection.get(limit=1, include=["embeddings"])
# Expected: len(result["embeddings"][0]) == 512
```

---

## Notes cho AI agent implement

- Đọc kỹ `architecture.md` trước khi bắt đầu.
- Fix 1 và Fix 2 không liên quan đến Fix 3, có thể làm song song.
- Fix 3e phải đảm bảo unit of re-parse là **toàn bộ file**, không phải từng function.
- `anchor` phải là dòng đầu tiên stripped — không include indent, chỉ lấy `line.strip()`.
- Nếu một file có class method, `anchor` là dòng `def method(self, ...)` của method đó,
  không phải dòng class.
- Khi `read_node_code()` update Neo4j sau khi tìm lại anchor, chỉ update
  `start_line` và `end_line`, không update `anchor` (anchor là ground truth).
- Backward compatibility: trong quá trình migration, nếu node cũ vẫn còn
  `raw_code` mà chưa có `start_line`, log warning và skip — đừng crash.
