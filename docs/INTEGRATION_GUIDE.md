# Hướng Dẫn Tích Hợp & Sử Dụng GraphRAG (Từ A Đến Z)

Tài liệu này hướng dẫn cách nhúng toàn bộ thư mục **GraphRAG** này làm một thư mục con (sub-component) của dự án kiểm thử tự động, cách cấu hình, chạy cập nhật đồ thị và truy vấn dữ liệu đồ thị (qua Python API cục bộ hoặc giao diện trực quan Neo4j).

---

## 1. Cấu Trúc Thư Mục Sau Khi Tích Hợp

Đầu tiên, hãy clone hoặc copy thư mục `GraphRAG` vào làm thư mục con trong dự án của bạn (đặt tên là `graphrag` hoặc giữ nguyên). 

Cấu trúc dự án sẽ trông tương tự như thế này:

```text
parent-project/                   ← Thư mục gốc của dự án chính (cần kiểm thử)
├── src/                          ← Source code của dự án chính
│   ├── auth.py
│   └── payment.py
├── .graphrag_data/               ← Thư mục ẩn chứa cơ sở dữ liệu đồ thị (tự sinh)
│   ├── neo4j/                    ← Dữ liệu đồ thị Neo4j
│   └── chromadb/                 ← Cơ sở dữ liệu Vector SQLite
└── graphrag/                     ← Thư mục công cụ GraphRAG này
    ├── initialize_graph.py       ← CLI chạy khởi tạo & đồng bộ tăng dần
    ├── config.py                 ← Cấu hình đường dẫn
    ├── requirements.txt          ← Các gói thư viện Python cần dùng
    ├── docker-compose.yml        ← File cấu hình Neo4j Docker
    └── query/
        └── engine.py             ← Local API để gọi tìm kiếm/truy vấn từ code Python
```

---

## 2. Các Bước Thiết Lập Ban Đầu (Chỉ Cần Làm 1 Lần)

### Bước 2.1: Cấu hình file `.env`
Vào thư mục con `graphrag/` (hoặc tên thư mục bạn clone về), sao chép file `.env.example` thành `.env` và điền khóa của bạn:

```env
# API Key của OpenRouter để dùng DeepSeek V4-Flash
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx...

# Tên nhận dạng dự án của bạn
PROJECT_NAME=my_project_name

# Đường dẫn dự án cần phân tích (Đặt là '..' để trỏ ra ngoài thư mục gốc dự án cha)
CODEBASE_PATH=..
```

### Bước 2.2: Chạy khởi tạo lần đầu tiên
Tại thư mục gốc của dự án chính (parent-project), bạn chạy file khởi tạo bằng lệnh Python bình thường:

```bash
# Chạy trực tiếp từ thư mục gốc của dự án cha (Không cần cd)
python graphrag/initialize_graph.py
```

**Ngay khi chạy lệnh này, GraphRAG sẽ TỰ ĐỘNG làm 3 việc:**
1.  **Tự động cập nhật `.gitignore` của dự án cha:** Thêm các thư mục `.graphrag_data/`, `venv/` của thư mục con, và file `.env` để tránh bị commit lên git.
2.  **Tự động tạo File khởi chạy nhanh tại thư mục gốc dự án cha:** Tạo ra 2 file `run_graphrag.bat` (Windows) và `run_graphrag.sh` (Linux/macOS) ở ngay thư mục ngoài cùng.
3.  **Tải và khởi chạy Neo4j & ChromaDB:** Chạy Docker Neo4j và tiến hành phân tích toàn bộ codebase từ đầu.

---

## 3. Chạy Khởi Chạy Và Đồng Bộ Tăng Dần (Mỗi Ngày)

Sau lần chạy đầu tiên, bạn **không cần gõ lệnh dài dòng và không cần cd vào thư mục con nữa**. Khi muốn cập nhật code mới sửa đổi vào database đồ thị, bạn chỉ cần mở terminal tại thư mục gốc dự án cha và chạy:

### Trên Windows:
```cmd
.\run_graphrag.bat
```

### Trên Linux / macOS:
```bash
./run_graphrag.sh
```

**Cơ chế của file script khởi chạy nhanh này:**
*   Nó sẽ tự động kiểm tra xem môi trường ảo `venv` của GraphRAG đã được tạo chưa. Nếu chưa có (ví dụ khi mới clone từ git về), nó **tự động tạo `venv` và cài đặt toàn bộ requirements** từ `requirements.txt`.
*   Tự động kích hoạt môi trường ảo và chạy đồng bộ.
*   Cập nhật dữ liệu đồ thị cực nhanh nhờ cơ chế đọc Git Diff để chỉ nạp và làm giàu dữ liệu những file bạn vừa thay đổi.

> [!TIP]
> **Buộc khởi tạo lại toàn bộ:** Nếu bạn muốn xóa toàn bộ đồ thị cũ để phân tích lại toàn bộ dự án từ con số không, bạn có thể truyền thêm tham số trực tiếp:
> ```bash
> .\run_graphrag.bat --force-init
> ```

---

## 4. Cách Gọi Local Python API (Không cần bật FastAPI Server)

Dự án kiểm thử tự động của bạn có thể sử dụng GraphRAG trực tiếp như một thư viện Python cục bộ bằng cách import module `knowledge_base`.

### Ví dụ code Python trong dự án chính:

```python
import sys
import os

# 1. Thêm đường dẫn thư mục graphrag vào sys.path để import
GRAPHRAG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "graphrag"))
sys.path.insert(0, GRAPHRAG_DIR)

# 2. Import các API truy vấn trực tiếp từ knowledge_base
from knowledge_base import get_snapshot, get_function_context, get_changes, mark_tested

# ─────────────────────────────────────────────────────────────
# Kịch bản 1: Lấy snapshot toàn bộ codebase (Lần đầu chạy - First Run)
# ─────────────────────────────────────────────────────────────
snapshot = get_snapshot()
print(f"Tổng số hàm cần test: {snapshot['total']}")
for comm in snapshot['communities']:
    print(f"Community: {comm['name']} (ID: {comm['id']})")
    for func in comm['functions']:
        print(f"  - {func['name']} (File: {func['file']}, Complexity: {func['complexity']})")

# ─────────────────────────────────────────────────────────────
# Kịch bản 2: Lấy thông tin ngữ cảnh để tự động sinh test case
# ─────────────────────────────────────────────────────────────
function_name = "login_user"
ctx = get_function_context(function_name)

if ctx and "function" in ctx:
    func_data = ctx["function"]
    
    print(f"\nTài liệu kiểm thử chi tiết cho hàm: {function_name}")
    print("--------------------------------------------------")
    print("1. Cách thức hoạt động:")
    print(func_data.get("how_it_works"))
    
    print("\n2. Ràng buộc Inputs:")
    print(func_data.get("input_spec"))
    
    print("\n3. Các Edge Cases cần lưu ý:")
    import json
    edge_cases = json.loads(func_data.get("edge_cases", "[]"))
    for ec in edge_cases:
        print(f"  - {ec}")
        
    print("\n4. Gợi ý viết test case & Mocking:")
    recommendations = json.loads(func_data.get("test_recommendations", "[]"))
    for rec in recommendations:
        print(f"  - {rec}")
        
    # Đánh dấu đã kiểm thử xong
    mark_tested(function_name)
else:
    print(f"Không tìm thấy thông tin hàm {function_name} trong đồ thị.")
```

---

## 5. Xem Và Inspect Mối Quan Hệ Trực Tiếp Trên Neo4j

Bạn có thể quan sát đồ thị trực quan và thực hiện các câu lệnh Cypher để kiểm tra các mối quan hệ thông qua Neo4j Browser:

### Bước 5.1: Truy cập Neo4j Browser
Mở trình duyệt web của bạn và đi tới đường dẫn:
👉 **`http://localhost:7474`**

### Bước 5.2: Đăng nhập
*   **Connection URI:** `bolt://localhost:7687`
*   **Authentication type:** `Username/Password`
*   **Username:** `neo4j`
*   **Password:** `graphrag123` (hoặc mật khẩu bạn đổi trong `.env`)

### Bước 5.3: Các câu lệnh Cypher inspect hữu ích
Nhập các lệnh sau vào ô gõ lệnh ở đầu trang và nhấn nút Run:

*   **Hiển thị toàn bộ cấu trúc file và hàm (Các file chứa các hàm nào):**
    ```cypher
    MATCH (f:File)-[r:CONTAINS]->(func:Function)
    RETURN f, r, func LIMIT 50
    ```
*   **Hiển thị các mối quan hệ gọi nhau giữa các hàm (Hàm A gọi hàm B):**
    ```cypher
    MATCH (a:Function)-[r:CALLS]->(b:Function)
    RETURN a, r, b LIMIT 50
    ```
*   **Kiểm tra lịch sử git commit ảnh hưởng đến các file nào:**
    ```cypher
    MATCH (c:Commit)-[r:MODIFIED]->(f:File)
    RETURN c, r, f LIMIT 30
    ```
*   **Xem các Concept ngữ nghĩa hoặc Task/Risk mà AI tự động trích xuất:**
    ```cypher
    MATCH (n) WHERE n:Concept OR n:Feature OR n:Risk OR n:Task
    RETURN n LIMIT 30
    ```
*   **Truy vấn mọi liên kết của một hàm cụ thể:**
    ```cypher
    MATCH (n {name: "tên_hàm_cần_tìm"})-[r]-(neighbor)
    RETURN n, r, neighbor
    ```
