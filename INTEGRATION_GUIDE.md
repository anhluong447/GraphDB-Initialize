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

## 2. Các Bước Cài Đặt Ban Đầu

Thực hiện các lệnh dưới đây bên trong thư mục con `graphrag/`:

### Bước 2.1: Tạo môi trường ảo Python & cài đặt thư viện
```bash
# Di chuyển vào thư mục con graphrag
cd graphrag

# Tạo Virtual Environment
python -m venv venv

# Kích hoạt venv (Windows)
.\venv\Scripts\activate

# Kích hoạt venv (Linux/macOS)
source venv/bin/activate

# Cài đặt thư viện
pip install -r requirements.txt
```

### Bước 2.2: Cấu hình file `.env`
Sao chép `.env.example` thành `.env` nằm trong thư mục `graphrag/` và cấu hình các trường sau:

```env
# 1. API Key của OpenRouter để dùng DeepSeek V4-Flash & OpenAI Embedding
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx...

# 2. Định danh dự án (giúp phân biệt nếu bạn có nhiều dự án chạy chung một máy)
PROJECT_NAME=my_automation_app

# 3. Đường dẫn dự án cần phân tích (Đặt là '..' để trỏ ra ngoài thư mục gốc dự án cha)
CODEBASE_PATH=..

# 4. Các tham số truy cập Neo4j (Mặc định giữ nguyên)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=graphrag123
```

---

## 3. Khởi Chạy & Tự Động Đồng Bộ Đồ Thị

Chạy lệnh sau tại thư mục `graphrag/` (với venv đã kích hoạt):

```bash
python initialize_graph.py
```

### Cơ chế hoạt động tự động:
*   **Lần chạy đầu tiên:** Hệ thống tự khởi chạy Neo4j Docker, phân tích cú pháp AST toàn bộ mã nguồn của dự án cha, gọi LLM trích xuất ngữ nghĩa và làm giàu (enrichment) tài liệu kiểm thử. File trạng thái `.graphrag_data/sync_state.json` sẽ được tạo tại dự án cha để lưu lại mã commit hiện tại.
*   **Các lần chạy sau:** Hệ thống tự động so sánh git diff (bao gồm cả thay đổi chưa commit). Nó sẽ **chỉ xử lý các tệp đã chỉnh sửa, thêm mới hoặc xóa bỏ**, dọn dẹp các node cũ trong Neo4j và ChromaDB, sau đó chọc LLM làm giàu tài liệu kiểm thử riêng cho các hàm thay đổi đó. Quá trình này diễn ra rất nhanh và tiết kiệm token tối đa.

> [!TIP]
> **Buộc khởi tạo lại từ đầu:** Nếu bạn muốn xóa toàn bộ đồ thị cũ và chạy phân tích lại toàn bộ dự án từ con số không, hãy chạy:
> ```bash
> python initialize_graph.py --force-init
> ```

---

## 4. Cách Gọi Local Python API (Không cần bật FastAPI Server)

Dự án kiểm thử tự động của bạn có thể sử dụng GraphRAG trực tiếp như một thư viện Python cục bộ để tìm kiếm thông tin ngữ cảnh hoặc đọc các tài liệu kiểm thử của hàm (`edge_cases`, `test_recommendations`).

### Ví dụ code Python trong dự án chính:

```python
import sys
import os

# 1. Thêm đường dẫn thư mục graphrag vào sys.path để import
GRAPHRAG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "graphrag"))
sys.path.insert(0, GRAPHRAG_DIR)

# 2. Import các API truy vấn cục bộ
from query.engine import query, get_node_detail

# ─────────────────────────────────────────────────────────────
# Kịch bản 1: Tìm kiếm ngữ cảnh nâng cao (Hybrid Query)
# ─────────────────────────────────────────────────────────────
question = "Hàm login_user hoạt động thế nào và có các lỗi tiềm ẩn nào?"
result = query(question)

print("--- KẾT QUẢ TRUY VẤN NGỮ CẢNH ---")
print(result["summary"])  # Trả về tóm tắt phân cụm, quan hệ hàm, và các điểm quan trọng

# ─────────────────────────────────────────────────────────────
# Kịch bản 2: Lấy thẳng tài liệu kiểm thử của một hàm cụ thể để tự động sinh test case
# ─────────────────────────────────────────────────────────────
function_name = "login_user"
detail = get_node_detail(function_name)

if detail and "node" in detail:
    node_data = detail["node"]
    
    print(f"\nTài liệu kiểm thử chi tiết cho hàm: {function_name}")
    print("--------------------------------------------------")
    print("1. Cách thức hoạt động:")
    print(node_data.get("how_it_works"))
    
    print("\n2. Ràng buộc Inputs:")
    print(node_data.get("input_spec"))
    
    print("\n3. Các Edge Cases cần lưu ý:")
    import json
    edge_cases = json.loads(node_data.get("edge_cases", "[]"))
    for ec in edge_cases:
        print(f"  - {ec}")
        
    print("\n4. Gợi ý viết test case & Mocking:")
    recommendations = json.loads(node_data.get("test_recommendations", "[]"))
    for rec in recommendations:
        print(f"  - {rec}")
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
