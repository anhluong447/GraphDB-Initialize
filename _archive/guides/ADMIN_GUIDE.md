# Hướng dẫn Quản trị viên (Dành cho Bạn - Host Server) 🖥️

Tài liệu này hướng dẫn bạn cách thiết lập, cấu hình, mở tường lửa và vận hành hệ thống **GraphRAG Standalone API Server** trên máy tính của bạn để chia sẻ cho các đội ngũ phát triển khác.

---

## 1. Tìm địa chỉ IP máy tính của bạn (Host IP)
Để các máy tính khác trong cùng mạng nội bộ (LAN/Wi-Fi) có thể kết nối tới server của bạn, họ cần biết IP của bạn.

1. Nhấn tổ hợp phím `Windows + R`, gõ `cmd` và nhấn **Enter**.
2. Gõ lệnh:
   ```cmd
   ipconfig
   ```
3. Tìm dòng **IPv4 Address** dưới card mạng bạn đang dùng (ví dụ: `192.168.1.15`). Đây chính là địa chỉ IP bạn sẽ cung cấp cho các team khác.

---

## 2. Mở cổng trên Tường lửa Windows (Firewall)
Mặc định, Windows Defender Firewall sẽ chặn các kết nối bên ngoài đi vào máy bạn. Bạn cần mở cổng **8080** (và có thể cả **7474**, **7687** nếu muốn cho họ truy cập thẳng database).

### Cách mở cổng nhanh bằng PowerShell (Run as Administrator):
1. Nhấn phím `Windows`, tìm kiếm **PowerShell**, click chuột phải chọn **Run as Administrator**.
2. Chạy lệnh dưới đây để mở cổng **8080** cho API Server:
   ```powershell
   New-NetFirewallRule -DisplayName "GraphRAG API Server" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
   ```
3. (Tùy chọn) Chạy tiếp lệnh này nếu muốn mở cổng **7474 & 7687** cho phép họ vào trực tiếp Neo4j Browser:
   ```powershell
   New-NetFirewallRule -DisplayName "Neo4j Database Ports" -Direction Inbound -LocalPort 7474,7687 -Protocol TCP -Action Allow
   ```

---

## 3. Cấu hình file `.env` trên Server
Mở file `d:\GraphRAG\.env` trên máy của bạn và điều chỉnh các thông số server:

```env
# Kích hoạt chế độ server để gom dữ liệu vào thư mục trung tâm ./server_data/
SERVER_MODE=true

# Khóa bảo mật để xác thực các request.
# Nếu bạn nhập giá trị ở đây, các team khác BẮT BUỘC phải đính kèm header X-API-Key mới gọi được API.
# Nếu để trống, bất kỳ ai trong mạng cũng gọi được API của bạn (không khuyến khích).
API_KEY=your-secret-api-key-here

# Thư mục lưu trữ các bản clone khi team khác yêu cầu nạp code từ link Git remote
WORKSPACE_DIR=./workspace
```

---

## 4. Khởi chạy Server
Double-click vào file **`start_server.bat`** ở thư mục gốc của dự án hoặc chạy lệnh:
```bash
python start_server.py
```
*Hệ thống sẽ tự động khởi chạy Docker (Neo4j & ChromaDB) và bật FastAPI Server trên cổng `8080`.*

---

## 5. Hướng dẫn nạp Codebase của bạn hoặc của Team khác vào DB
Khi hệ thống mới bật hoặc khi có codebase mới, bạn (hoặc team khác) cần khởi chạy pipeline nạp dữ liệu (Ingestion Pipeline). 

### Cách nạp codebase nằm cục bộ trên máy bạn:
Gửi request POST tới `/api/repo/init` bằng Curl hoặc Postman:
```bash
curl -X POST http://localhost:8080/api/repo/init \
  -H "X-API-Key: your-secret-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "d:/demo_project/A20-App-083", "language": "python"}'
```

### Cách nạp codebase từ Git Remote (GitHub/GitLab):
Nếu codebase của họ nằm trên Git:
```bash
curl -X POST http://localhost:8080/api/repo/init \
  -H "X-API-Key: your-secret-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/my-team/project.git", "language": "typescript"}'
```
*Server sẽ tự động clone repo về thư mục `./workspace/` và chạy pipeline 9 bước trong background.*

---

## 6. Giám sát Trạng thái (State)
Bạn có thể kiểm tra trạng thái hoạt động hiện tại của server, kết nối DB và mode chạy bằng cách truy cập:
* **Giao diện quản lý trực quan (Swagger)**: `http://localhost:8080/docs`
* **API Health Check**: `http://localhost:8080/api/health`
* **Dữ liệu thô trên Neo4j Browser**: `http://localhost:7474` (User: `neo4j` / Pass: `graphrag123`)
