---
name: testing-backend
description: >
  Skill kiểm thử backend chuyên nghiệp cho bất kỳ dự án server-side nào —
  REST API, GraphQL, microservice, CLI tool, database layer, worker/job queue.
  Dùng khi cần: viết unit test cho business logic, integration test cho API
  endpoint, kiểm thử authentication và authorization, test database operations,
  mock external service/dependency, kiểm thử error handling và edge cases, thiết
  lập test strategy cho dự án mới. Trigger khi user nhắc đến "test API",
  "test endpoint", "unit test", "integration test", "kiểm thử backend", "pytest",
  "Jest backend", "mock database", "test authentication", "test middleware",
  hoặc bất kỳ yêu cầu đảm bảo chất lượng phía server. Luôn đọc skill này
  trước khi viết bất kỳ backend test nào.
---

# Backend Testing Skill

Mục tiêu: test **contract và behavior** — API trả về đúng response, business
logic xử lý đúng case, lỗi được handle đúng cách. Không test framework, không
test language runtime.

---

## Bước 0 — Phân tích trước khi viết test

```
1. Stack là gì?
   Python (pytest / FastAPI / Django) / Node.js (Jest / Vitest) /
   Go (testing package) / Java (JUnit) / …
   → Mặc định nếu không rõ: Python + pytest hoặc Node.js + Jest

2. Loại test cần viết?
   Unit          → function, class, service method (không I/O)
   Integration   → endpoint + DB + service cùng nhau
   Contract      → API response shape đúng với spec
   Auth          → authn (ai?) + authz (được làm gì?)
   DB layer      → query đúng, migration, constraint

3. Dependencies nào cần mock?
   Database         → in-memory hoặc test DB riêng
   External API     → mock / stub / record-replay
   Message queue    → in-memory fake
   File system      → tmp dir hoặc mock
   Time/clock       → freeze/mock
```

---

## Phần 1 — Nguyên tắc cốt lõi

### 1.1 Pyramid testing

```
        /\
       /E2E\          ← ít nhất, chậm nhất, test critical flows
      /──────\
     /  Integ  \      ← vừa phải, test API contract + DB
    /────────────\
   /     Unit     \   ← nhiều nhất, nhanh nhất, test business logic
  /────────────────\
```

Unit test: không chạm I/O (DB, network, file). Nhanh, deterministic, isolate.
Integration test: test một slice dọc (request → handler → DB → response).
E2E: test full system với dependencies thật hoặc staging.

### 1.2 Test một thứ mỗi lần

```python
# ❌ Sai — test quá nhiều thứ cùng lúc
def test_user_flow():
    user = create_user("alice@example.com")
    assert user.id is not None
    token = login(user)
    assert token is not None
    profile = get_profile(token)
    assert profile["email"] == "alice@example.com"
    update_profile(token, {"name": "Alice"})
    assert get_profile(token)["name"] == "Alice"

# ✅ Đúng — mỗi test một behavior
def test_create_user_returns_id():
    user = create_user("alice@example.com")
    assert user.id is not None

def test_login_returns_jwt_token():
    user = create_user("alice@example.com")
    token = login(user)
    assert is_valid_jwt(token)
```

### 1.3 Đặt tên test

Pattern: `test_[unit]_[condition]_[expected_result]`

```
✅ test_create_user_with_duplicate_email_raises_conflict
✅ test_get_orders_without_auth_returns_401
✅ test_calculate_discount_when_cart_over_100_applies_10_percent
❌ test_user
❌ test_create_1
❌ it_works
```

### 1.4 F.I.R.S.T

```
Fast        — unit test < 1ms, không sleep(), không network
Isolated    — không phụ thuộc thứ tự chạy, không share state
Repeatable  — kết quả như nhau dù chạy ở đâu, lúc nào
Self-validating — pass hoặc fail rõ ràng, không cần đọc log
Timely      — viết cùng lúc hoặc trước code (không phải sau)
```

---

## Phần 2 — Unit Testing

### 2.1 Structure — Arrange / Act / Assert

```python
# Python + pytest
def test_calculate_tax_for_us_region():
    # Arrange
    cart = Cart(items=[Item(price=100)])
    tax_calculator = TaxCalculator(region="US")

    # Act
    result = tax_calculator.calculate(cart)

    # Assert
    assert result.amount == 8.25
    assert result.rate == 0.0825
    assert result.currency == "USD"
```

```ts
// TypeScript + Jest/Vitest
it('returns discounted price when coupon is valid', () => {
  // Arrange
  const pricing = new PricingService()
  const coupon = { code: 'SAVE10', type: 'percent', value: 10 }

  // Act
  const result = pricing.applyDiscount(100, coupon)

  // Assert
  expect(result).toBe(90)
})
```

### 2.2 Mocking dependencies

```python
# Python — mock external service
from unittest.mock import patch, MagicMock

def test_send_welcome_email_called_after_signup(mock_email):
    with patch('app.services.email.send_email') as mock_send:
        signup_user("alice@example.com", "password123")
        mock_send.assert_called_once_with(
            to="alice@example.com",
            template="welcome"
        )

# Mock database
def test_get_user_not_found_raises_404():
    with patch('app.db.users.find_by_id', return_value=None):
        with pytest.raises(NotFoundError) as exc:
            get_user(user_id=999)
        assert exc.value.status_code == 404
```

```ts
// TypeScript — mock với Jest
jest.mock('../services/emailService')
const mockSend = jest.mocked(emailService.send)

it('sends verification email after registration', async () => {
  mockSend.mockResolvedValueOnce({ messageId: 'abc' })

  await registerUser({ email: 'alice@example.com', password: 'pass123' })

  expect(mockSend).toHaveBeenCalledWith(
    expect.objectContaining({ to: 'alice@example.com', template: 'verify' })
  )
})
```

### 2.3 Edge cases quan trọng

Với mỗi function/method, luôn test:

```
□ Happy path — input hợp lệ, output đúng
□ Empty input — [], "", null, 0
□ Boundary values — min, max, ±1 quanh ngưỡng
□ Invalid input — wrong type, out of range
□ Concurrent / duplicate — gọi 2 lần cùng lúc
□ Side effects — những gì được gọi, không gọi
```

---

## Phần 3 — API Integration Testing

### 3.1 Test HTTP endpoint (FastAPI + pytest)

```python
# conftest.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db
from tests.factories import UserFactory

@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

@pytest.fixture
def auth_client(client, db_session):
    user = UserFactory(db_session)
    token = create_access_token(user.id)
    client.headers["Authorization"] = f"Bearer {token}"
    return client
```

```python
# test_users_api.py
class TestGetUsers:
    def test_returns_list_of_users(self, auth_client, db_session):
        UserFactory.create_batch(3, session=db_session)
        response = auth_client.get("/api/users")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 3

    def test_requires_authentication(self, client):
        response = client.get("/api/users")
        assert response.status_code == 401

    def test_pagination_works(self, auth_client, db_session):
        UserFactory.create_batch(25, session=db_session)
        response = auth_client.get("/api/users?page=2&limit=10")
        body = response.json()
        assert len(body["data"]) == 10
        assert body["meta"]["page"] == 2
        assert body["meta"]["total"] == 25
```

### 3.2 Test HTTP endpoint (Express + Jest)

```ts
// app.test.ts
import request from 'supertest'
import { app } from '../app'
import { db } from '../db'
import { createTestUser, generateToken } from './helpers'

describe('GET /api/users/:id', () => {
  let token: string
  let userId: number

  beforeEach(async () => {
    const user = await createTestUser({ role: 'admin' })
    token = generateToken(user.id)
    userId = user.id
  })

  it('returns user when found', async () => {
    const res = await request(app)
      .get(`/api/users/${userId}`)
      .set('Authorization', `Bearer ${token}`)

    expect(res.status).toBe(200)
    expect(res.body).toMatchObject({
      id: userId,
      email: expect.any(String),
    })
    // Không leak sensitive fields
    expect(res.body).not.toHaveProperty('password_hash')
    expect(res.body).not.toHaveProperty('reset_token')
  })

  it('returns 404 for non-existent user', async () => {
    const res = await request(app)
      .get('/api/users/99999')
      .set('Authorization', `Bearer ${token}`)
    expect(res.status).toBe(404)
    expect(res.body).toHaveProperty('error')
  })
})
```

### 3.3 Response contract testing

Luôn assert đủ 4 thứ cho mọi endpoint:

```python
def test_create_order_response_contract(auth_client):
    payload = {"product_id": 1, "quantity": 2}
    response = auth_client.post("/api/orders", json=payload)

    # 1. Status code đúng
    assert response.status_code == 201

    # 2. Headers đúng
    assert response.headers["content-type"] == "application/json"

    # 3. Shape đúng — tất cả required fields có mặt
    body = response.json()
    assert "id" in body
    assert "status" in body
    assert "created_at" in body
    assert "items" in body

    # 4. Không leak sensitive data
    assert "internal_cost" not in body
    assert "payment_token" not in body
```

---

## Phần 4 — Authentication & Authorization

### 4.1 Authn — ai đang gọi?

```python
class TestAuthentication:
    def test_no_token_returns_401(self, client):
        assert client.get("/api/me").status_code == 401

    def test_invalid_token_returns_401(self, client):
        client.headers["Authorization"] = "Bearer invalid.token.here"
        assert client.get("/api/me").status_code == 401

    def test_expired_token_returns_401(self, client):
        expired = create_token(user_id=1, expires_delta=timedelta(seconds=-1))
        client.headers["Authorization"] = f"Bearer {expired}"
        assert client.get("/api/me").status_code == 401

    def test_valid_token_returns_200(self, auth_client):
        assert auth_client.get("/api/me").status_code == 200
```

### 4.2 Authz — được làm gì?

```python
class TestAuthorization:
    # Test theo matrix: role × action × resource
    #
    #          | own_resource | others_resource | admin_resource |
    # user     |    ✓ / ✗    |       ✗         |       ✗        |
    # admin    |    ✓ / ✓    |       ✓         |       ✓        |

    def test_user_can_read_own_profile(self, user_client, current_user):
        res = user_client.get(f"/api/users/{current_user.id}")
        assert res.status_code == 200

    def test_user_cannot_read_other_profile(self, user_client, other_user):
        res = user_client.get(f"/api/users/{other_user.id}")
        assert res.status_code == 403

    def test_admin_can_read_any_profile(self, admin_client, other_user):
        res = admin_client.get(f"/api/users/{other_user.id}")
        assert res.status_code == 200

    def test_user_cannot_delete_own_account(self, user_client, current_user):
        res = user_client.delete(f"/api/users/{current_user.id}")
        assert res.status_code == 403

    def test_admin_can_delete_any_account(self, admin_client, other_user):
        res = admin_client.delete(f"/api/users/{other_user.id}")
        assert res.status_code == 204
```

---

## Phần 5 — Database Testing

### 5.1 Isolation strategy

```python
# conftest.py — rollback sau mỗi test (không dọn bằng tay)
@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
```

### 5.2 Test query và constraint

```python
def test_unique_email_constraint(db_session):
    UserFactory(email="alice@example.com", session=db_session)
    with pytest.raises(IntegrityError):
        UserFactory(email="alice@example.com", session=db_session)

def test_cascade_delete_removes_posts(db_session):
    user = UserFactory(session=db_session)
    PostFactory(author=user, session=db_session)
    PostFactory(author=user, session=db_session)

    db_session.delete(user)
    db_session.flush()

    remaining = db_session.query(Post).filter_by(author_id=user.id).count()
    assert remaining == 0

def test_soft_delete_hides_from_default_query(db_session):
    user = UserFactory(session=db_session)
    user.soft_delete()

    result = db_session.query(User).filter_by(id=user.id).first()
    assert result is None  # default scope ẩn deleted records

    result_with_deleted = db_session.query(User).with_deleted().filter_by(id=user.id).first()
    assert result_with_deleted is not None
```

### 5.3 Factory pattern

Dùng `factory_boy` (Python) hoặc `fishery` (TS) để tạo test data nhất quán — không hardcode fixture JSON. Factory dùng `Sequence` cho unique fields (email, slug), `SubFactory` cho relations, `Faker` cho realistic data. Tạo `AdminFactory(UserFactory)` bằng cách override field cần đổi. Chi tiết trong `references/pytest-fixtures.md`.

---

## Phần 6 — Error Handling & Edge Cases

### 6.1 Checklist error cases cho mọi endpoint

```
Input:      missing field → 422 | wrong type → 422 | out of range → 422 | too long → 422
Business:   not found → 404 | duplicate → 409 | invalid state → 422 | rate limit → 429
Auth:       no token → 401 | expired → 401 | insufficient perm → 403
External:   DB down → 503 | timeout → 504 | (không expose stack trace)
```

### 6.2 Test error response format

```python
def test_validation_error_format(client):
    res = client.post("/api/users", json={"name": ""})  # email missing
    assert res.status_code == 422
    body = res.json()
    # Phải có structure nhất quán, không để raw exception leak
    assert "error" in body or "errors" in body
    assert "stack_trace" not in body
    assert "sql" not in str(body).lower()
```

---

## Phần 7 — Test Configuration

### 7.1 pytest setup chuẩn

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
markers = [
    "unit: pure unit tests, no I/O",
    "integration: tests with DB or external services",
    "slow: tests taking more than 1s",
]

[tool.coverage.run]
source = ["app"]
omit = ["app/migrations/*", "tests/*"]

[tool.coverage.report]
fail_under = 80
exclude_lines = ["if TYPE_CHECKING:", "raise NotImplementedError"]
```

```bash
# Chạy theo layer
pytest -m unit            # nhanh, chạy thường xuyên
pytest -m integration     # chậm hơn, chạy trước merge
pytest --cov=app --cov-report=term-missing  # với coverage
```

### 7.2 Jest/Vitest setup chuẩn

`testEnvironment: 'node'`, `setupFilesAfterFramework` chạy `db.connect()` trước tất cả tests, `afterAll` disconnect, `afterEach` rollback. Coverage threshold đặt `lines: 80` ở global, fail CI nếu xuống dưới.

---

## Phần 8 — Coverage Strategy

### 8.1 Target có nghĩa

```
≥ 90% — business logic layer (services, use cases, domain)
≥ 80% — API handler layer
≥ 70% — repository/DB layer (integration test)
  skip — migration files, config, generated code
```

Coverage 100% không có nghĩa gì nếu assertion sai. Tập trung vào **mutation coverage**: nếu logic sai thì test fail không?

### 8.2 Ưu tiên theo risk

```
HIGH — test bắt buộc:
  ✓ Auth/authz logic
  ✓ Payment, billing, financial calculation
  ✓ Data validation trước khi write DB
  ✓ State transitions (order status, user lifecycle)
  ✓ Rate limiting và security controls

MEDIUM — test nên có:
  ✓ CRUD operations cho mọi resource
  ✓ Search, filter, sort, pagination
  ✓ Notification trigger (email, webhook)
  ✓ Background job logic

LOW — skip hoặc test nhẹ:
  ✗ Config loading
  ✗ Logging calls
  ✗ Health check endpoint
  ✗ Framework boilerplate
```

---

## Tham chiếu

- `references/pytest-fixtures.md` — fixture patterns nâng cao, factory với faker
- `references/msw-node.md` — Mock Service Worker cho Node.js integration test
- `references/db-strategies.md` — In-memory vs test DB, migration strategy
- `references/security-tests.md` — OWASP top 10 test cases cho API