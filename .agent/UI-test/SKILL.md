---
name: testing-ui
description: >
  Skill kiểm thử UI/UX chuyên nghiệp cho bất kỳ dự án frontend nào — web app,
  dashboard, form, landing page, component library. Dùng khi cần: viết test cho
  React/Vue/HTML component, kiểm thử interaction (click, input, navigation),
  kiểm thử accessibility, kiểm thử responsive, E2E flow với Playwright hoặc
  Cypress, visual regression, hoặc review UI hiện tại để tìm lỗi. Trigger khi
  user nhắc đến "test UI", "test component", "kiểm thử giao diện", "viết test
  cho form/button/modal", "E2E", "Playwright", "Cypress", "accessibility check",
  "responsive test", hoặc bất kỳ yêu cầu nào liên quan đến đảm bảo chất lượng
  frontend. Luôn đọc skill này trước khi viết bất kỳ UI test nào.
---

# UI/UX Testing Skill

Mục tiêu: test **hành vi từ góc nhìn user**, không test implementation detail.
User không quan tâm tên hàm hay state nội bộ — họ quan tâm giao diện làm đúng không.

---

## Bước 0 — Phân tích trước khi viết test

Trả lời 3 câu hỏi (suy luận từ context):

```
1. Stack là gì?
   React + Vitest/RTL / Vue + Vitest / Playwright (E2E) / Cypress / Vanilla JS

2. Loại test cần viết?
   Unit component  → RTL / Vue Test Utils
   Integration     → RTL + mock API
   E2E flow        → Playwright / Cypress
   Accessibility   → axe-core / Playwright
   Visual          → Playwright screenshot / Storybook

3. Độ phức tạp của component?
   Simple (stateless, display only) → ít test, happy path là đủ
   Interactive (form, modal, nav)   → test states + edge cases
   Data-driven (fetch, filter)      → test loading/empty/error + data render
```

Nếu user không nói rõ stack → **mặc định React + Vitest + React Testing Library**.

---

## Phần 1 — Nguyên tắc cốt lõi

### 1.1 Test behavior, không test implementation

```tsx
// ❌ Sai — test implementation detail
expect(component.state.isOpen).toBe(true)
expect(wrapper.find('DropdownMenu').props().visible).toBe(true)

// ✅ Đúng — test điều user thấy
expect(screen.getByRole('listbox')).toBeVisible()
expect(screen.getByText('Option A')).toBeInTheDocument()
```

### 1.2 Query theo thứ tự ưu tiên (RTL)

```
1. getByRole          → chuẩn nhất, test accessibility luôn
2. getByLabelText     → form fields
3. getByPlaceholderText
4. getByText          → non-interactive content
5. getByDisplayValue  → select, input đang có value
6. getByAltText       → image
7. getByTitle
8. getByTestId        → last resort, khi không còn cách nào khác
```

Không dùng `querySelector`, `getElementById`, hay class selector trong test.

### 1.3 Cấu trúc test chuẩn — AAA

```tsx
it('shows error message when email is invalid', async () => {
  // Arrange — setup
  render(<LoginForm />)
  const emailInput = screen.getByLabelText('Email')
  const submitBtn  = screen.getByRole('button', { name: /sign in/i })

  // Act — thực hiện action
  await userEvent.type(emailInput, 'not-an-email')
  await userEvent.click(submitBtn)

  // Assert — kiểm tra kết quả
  expect(screen.getByRole('alert')).toHaveTextContent('Please enter a valid email')
  expect(emailInput).toHaveAttribute('aria-invalid', 'true')
})
```

### 1.4 Đặt tên test

Pattern: `[component] [khi nào] [kết quả gì]`

```
✅ "LoginForm shows validation error when email is empty"
✅ "Dropdown closes when user clicks outside"
✅ "DataTable sorts rows ascending on first header click"
❌ "test1"
❌ "works correctly"
❌ "LoginForm test"
```

---

## Phần 2 — Component Testing (React Testing Library)

### 2.1 Setup chuẩn

```tsx
// test-utils.tsx — wrapper dùng chung
import { render, RenderOptions } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

function AllProviders({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <ThemeProvider>
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  )
}

function customRender(ui: React.ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: AllProviders, ...options })
}

// Re-export everything
export * from '@testing-library/react'
export { customRender as render }
export { userEvent }
```

### 2.2 Async render và data fetching

```tsx
// Mock API — dùng msw hoặc vi.mock
vi.mock('../api', () => ({
  fetchUsers: vi.fn().mockResolvedValue([
    { id: 1, name: 'Alice', role: 'admin' }
  ])
}))

it('renders user list after loading', async () => {
  render(<UserList />)

  // Loading state
  expect(screen.getByRole('status')).toBeInTheDocument()  // spinner

  // Data loaded
  await screen.findByText('Alice')  // findBy = waitFor + getBy
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.getByText('admin')).toBeInTheDocument()
})

it('shows empty state when no users', async () => {
  vi.mocked(fetchUsers).mockResolvedValueOnce([])
  render(<UserList />)
  await screen.findByText('No users yet')
})

it('shows error state when fetch fails', async () => {
  vi.mocked(fetchUsers).mockRejectedValueOnce(new Error('Network error'))
  render(<UserList />)
  await screen.findByRole('alert')
  expect(screen.getByText(/failed to load/i)).toBeInTheDocument()
})
```

### 2.3 Form testing

```tsx
it('submits form with valid data', async () => {
  const onSubmit = vi.fn()
  render(<ContactForm onSubmit={onSubmit} />)

  await userEvent.type(screen.getByLabelText('Name'),  'Alice')
  await userEvent.type(screen.getByLabelText('Email'), 'alice@example.com')
  await userEvent.selectOptions(screen.getByLabelText('Subject'), 'billing')
  await userEvent.click(screen.getByRole('button', { name: /submit/i }))

  expect(onSubmit).toHaveBeenCalledWith({
    name: 'Alice',
    email: 'alice@example.com',
    subject: 'billing'
  })
})

it('disables submit button while submitting', async () => {
  // Form đang xử lý async
  render(<ContactForm onSubmit={() => new Promise(() => {})} />)
  // fill fields...
  await userEvent.click(screen.getByRole('button', { name: /submit/i }))
  expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled()
})
```

### 2.4 Modal và Dialog

```tsx
it('opens modal on trigger click and closes on Escape', async () => {
  render(<DeleteButton itemName="Report Q3" />)

  // Mở
  await userEvent.click(screen.getByRole('button', { name: /delete/i }))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.getByText('Delete Report Q3?')).toBeVisible()

  // Đóng bằng Escape
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

it('calls onConfirm when delete is confirmed', async () => {
  const onConfirm = vi.fn()
  render(<DeleteButton onConfirm={onConfirm} />)
  await userEvent.click(screen.getByRole('button', { name: /delete/i }))
  await userEvent.click(screen.getByRole('button', { name: /confirm/i }))
  expect(onConfirm).toHaveBeenCalledTimes(1)
})
```

### 2.5 Navigation và routing

```tsx
// Dùng MemoryRouter để test routing
it('navigates to user profile on row click', async () => {
  render(
    <MemoryRouter initialEntries={['/users']}>
      <Routes>
        <Route path="/users" element={<UserTable />} />
        <Route path="/users/:id" element={<UserProfile />} />
      </Routes>
    </MemoryRouter>
  )

  await screen.findByText('Alice')
  await userEvent.click(screen.getByRole('row', { name: /alice/i }))
  expect(screen.getByRole('heading', { name: /alice/i })).toBeInTheDocument()
})
```

---

## Phần 3 — Accessibility Testing

### 3.1 axe-core với RTL

```tsx
import { axe, toHaveNoViolations } from 'jest-axe'
expect.extend(toHaveNoViolations)

it('has no accessibility violations', async () => {
  const { container } = render(<LoginForm />)
  const results = await axe(container)
  expect(results).toHaveNoViolations()
})
```

### 3.2 Manual checks quan trọng

Kiểm tra thủ công những điều axe không catch được:

```
Keyboard navigation:
  □ Tab đi qua tất cả interactive elements theo thứ tự logic
  □ Enter/Space activate button và checkbox
  □ Escape đóng modal, dropdown, drawer
  □ Arrow keys navigate menu, listbox, tablist
  □ Focus không bị "bẫy" ngoại trừ trong modal (focus trap đúng)
  □ Focus visible luôn rõ ràng (không bao giờ outline: none đơn thuần)

ARIA:
  □ Images có alt text có nghĩa (không phải "image" hay "photo")
  □ Icon buttons có aria-label
  □ Form inputs có label liên kết (htmlFor hoặc aria-labelledby)
  □ Error messages có role="alert" hoặc aria-live="polite"
  □ Loading spinners có aria-label + role="status"
  □ Modal có role="dialog" + aria-labelledby + aria-modal="true"

Color & contrast:
  □ Text thường ≥ 4.5:1 contrast ratio (WCAG AA)
  □ Large text (18px+) ≥ 3:1
  □ Không dùng màu là tín hiệu DUY NHẤT (ví dụ: error chỉ đổi màu đỏ)
```

### 3.3 Test keyboard với RTL

```tsx
it('traps focus inside modal', async () => {
  render(<Modal isOpen title="Confirm" />)
  const dialog = screen.getByRole('dialog')
  const focusable = within(dialog).getAllByRole('button')

  // Tab từ last element về first
  focusable[focusable.length - 1].focus()
  await userEvent.tab()
  expect(focusable[0]).toHaveFocus()
})
```

---

## Phần 4 — E2E Testing (Playwright)

### 4.1 Cấu trúc file

```
tests/
├── e2e/
│   ├── auth.spec.ts        ← login, logout, session
│   ├── [feature].spec.ts   ← 1 file per feature
│   └── critical-paths.spec.ts  ← happy paths quan trọng nhất
├── fixtures/
│   └── users.ts            ← test data
└── helpers/
    └── pages.ts            ← Page Object Model
```

### 4.2 Page Object Model

```tsx
// helpers/pages/LoginPage.ts
export class LoginPage {
  constructor(private page: Page) {}

  async goto() { await this.page.goto('/login') }

  async login(email: string, password: string) {
    await this.page.getByLabel('Email').fill(email)
    await this.page.getByLabel('Password').fill(password)
    await this.page.getByRole('button', { name: 'Sign in' }).click()
  }

  async expectError(message: string) {
    await expect(this.page.getByRole('alert')).toContainText(message)
  }
}

// Dùng trong test
test('login with invalid credentials', async ({ page }) => {
  const loginPage = new LoginPage(page)
  await loginPage.goto()
  await loginPage.login('user@example.com', 'wrongpassword')
  await loginPage.expectError('Invalid email or password')
})
```

### 4.3 Network mocking trong Playwright

```tsx
// Mock API để test không phụ thuộc backend
test('shows error when API is down', async ({ page }) => {
  await page.route('**/api/users', route =>
    route.fulfill({ status: 500, body: 'Internal Server Error' })
  )
  await page.goto('/users')
  await expect(page.getByRole('alert')).toContainText('Failed to load users')
})

// Mock chậm để test loading state
test('shows loading spinner while fetching', async ({ page }) => {
  await page.route('**/api/users', async route => {
    await new Promise(r => setTimeout(r, 500))
    await route.continue()
  })
  await page.goto('/users')
  await expect(page.getByRole('status')).toBeVisible()
})
```

### 4.5 Visual regression

```tsx
test('dashboard layout matches snapshot', async ({ page }) => {
  await page.goto('/dashboard')
  await page.waitForLoadState('networkidle')
  // Ẩn dynamic content (timestamp, avatar) trước khi chụp
  await page.evaluate(() => {
    document.querySelectorAll('[data-testid="timestamp"]')
      .forEach(el => (el as HTMLElement).style.visibility = 'hidden')
  })
  await expect(page).toMatchSnapshot('dashboard.png', { threshold: 0.02 })
})
```

---

## Phần 5 — Responsive Testing

### 5.1 Viewports cần test

```tsx
const VIEWPORTS = {
  mobile:  { width: 375,  height: 812 },   // iPhone SE
  tablet:  { width: 768,  height: 1024 },  // iPad
  desktop: { width: 1280, height: 800 },   // Standard
  wide:    { width: 1920, height: 1080 },  // Large monitor
}

for (const [device, viewport] of Object.entries(VIEWPORTS)) {
  test(`sidebar collapses on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto('/dashboard')

    if (viewport.width < 768) {
      await expect(page.getByRole('navigation')).not.toBeVisible()
      await expect(page.getByRole('button', { name: 'Menu' })).toBeVisible()
    } else {
      await expect(page.getByRole('navigation')).toBeVisible()
    }
  })
}
```

### 5.2 Checklist responsive thủ công

```
□ Không có overflow ngang ở bất kỳ breakpoint nào
□ Text không bị cắt (overflow: hidden mà không có ellipsis)
□ Touch targets ≥ 44x44px trên mobile
□ Sidebar/drawer hoạt động đúng trên mobile
□ Table/grid không vỡ — có horizontal scroll hoặc stack đúng
□ Font size không quá nhỏ (≥ 14px body trên mobile)
□ Images không vỡ ratio
```

---

## Phần 6 — Test Coverage Strategy

### 6.1 Không cần 100% coverage

Ưu tiên test theo giá trị, không theo số:

```
MUST test (critical):
  ✓ Authentication flows (login, logout, session expire)
  ✓ Form validation — tất cả error cases
  ✓ Mọi action có side effect (delete, submit, payment)
  ✓ Error states và empty states
  ✓ Permission/role-based UI differences

SHOULD test (high value):
  ✓ Complex interactive components (multi-step form, drag-drop)
  ✓ Data loading states (loading → success → error)
  ✓ Pagination, sort, filter behavior
  ✓ Keyboard navigation cho critical flows

SKIP (low value):
  ✗ Pure display component không có logic
  ✗ Third-party library behavior
  ✗ CSS/styling (dùng visual regression thay)
  ✗ Implementation detail (internal state, private methods)
```

### 6.2 Test file structure

```
src/
└── components/
    ├── LoginForm/
    │   ├── LoginForm.tsx
    │   ├── LoginForm.test.tsx    ← unit + integration
    │   └── LoginForm.stories.tsx ← Storybook (optional)
    └── UserTable/
        ├── UserTable.tsx
        └── UserTable.test.tsx
tests/
└── e2e/
    └── auth.spec.ts
```

---

## Phần 7 — Checklist trước khi done

```
Setup:
  □ test-utils.tsx có wrapper đủ providers
  □ Mock API setup (msw hoặc vi.mock)
  □ userEvent thay vì fireEvent

Mỗi component có test có coverage:
  □ Happy path (render đúng với valid data)
  □ Loading state
  □ Empty state
  □ Error state
  □ Validation errors (nếu là form)
  □ Keyboard interaction (nếu là interactive)

E2E:
  □ Mỗi critical user flow có ít nhất 1 E2E test
  □ Happy path không mock network (test thật)
  □ Error paths mock network

Accessibility:
  □ axe chạy được không violation
  □ Tab order hợp lý
  □ Aria attributes đúng
```

---

## Tham chiếu

- `references/msw-setup.md` — Mock Service Worker setup đầy đủ
- `references/playwright-config.md` — playwright.config.ts chuẩn + CI setup
- `references/a11y-checklist.md` — WCAG 2.1 AA checklist chi tiết