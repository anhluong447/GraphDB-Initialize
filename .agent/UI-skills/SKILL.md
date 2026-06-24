---
name: ui-ux-design
description: >
  Skill thiết kế và implement UI/UX chuyên nghiệp cho bất kỳ dự án nào —
  web app, dashboard, tool nội bộ, landing page, mobile-first site. Dùng khi
  cần: xây design system từ đầu, implement layout phức tạp, thiết kế component
  library, review và cải thiện UI hiện có, hoặc translate spec/wireframe thành
  code. Trigger khi user nhắc đến giao diện, UI, UX, layout, component, design
  system, hoặc muốn "làm đẹp" / "cải thiện" một cái gì đó visual. Luôn đọc
  skill này trước khi viết bất kỳ dòng UI code nào, dù task có vẻ đơn giản.
---

# UI/UX Design Skill — General

Đọc song song với skill `frontend-design` (aesthetic direction).
Skill này cover phần **engineering của design**: tokens, anatomy, patterns,
code quality. Không phải "trông đẹp" — mà là "build đúng để có thể trông đẹp".

---

## Bước 0 — Đọc brief và định vị

Trước khi thiết kế bất cứ thứ gì, trả lời 4 câu hỏi này (suy luận từ context,
không hỏi user nếu đã rõ):

```
1. Loại sản phẩm?
   App / Dashboard / Tool nội bộ / Landing page / Form / E-commerce / Docs

2. Ai dùng và trong hoàn cảnh nào?
   Developer / End-user / Admin / Khách vãng lai / Mobile-first / Desktop-only

3. Mục tiêu chính của màn hình này là gì?
   Một câu duy nhất. Nếu không trả lời được → spec chưa rõ, cần clarify.

4. Constraint nào đã cứng?
   Stack, thư viện, breakpoint, brand color, accessibility requirement.
```

Phân loại complexity:
- **Simple** — ≤ 3 views, ≤ 10 component, không real-time
- **Medium** — 4–8 views, multi-state, sort/filter, auth
- **Complex** — multi-view app, real-time, role-based, nhiều data type

---

## Phần 1 — Design Token System

**Quy tắc vàng**: Không bao giờ hardcode màu, size, hay spacing trong component.
Tất cả đi qua token. Component không biết màu của mình — nó chỉ biết vai trò của mình.

### 1.1 Cấu trúc 3 tầng

```
Tầng 1: Primitive   → giá trị thô, không dùng trực tiếp
Tầng 2: Semantic    → vai trò trong UI, dùng trong component
Tầng 3: Component   → override cụ thể, dùng khi tầng 2 không đủ
```

```css
/* ── Tầng 1: Primitive ─────────────────────────── */
--blue-400: #60a5fa;
--blue-500: #3b82f6;
--blue-600: #2563eb;
--gray-50:  #f9fafb;
--gray-900: #111827;
/* ... */

/* ── Tầng 2: Semantic ──────────────────────────── */
/* Background */
--bg-base:      var(--gray-50);   /* canvas chính */
--bg-surface:   #ffffff;          /* card, panel */
--bg-elevated:  #ffffff;          /* modal, dropdown */
--bg-sunken:    var(--gray-100);  /* input, code block */
--bg-overlay:   rgba(0,0,0,0.4);  /* backdrop */

/* Text */
--text-primary:   var(--gray-900);
--text-secondary: var(--gray-500);
--text-tertiary:  var(--gray-400);
--text-disabled:  var(--gray-300);
--text-inverse:   #ffffff;
--text-link:      var(--blue-600);

/* Border */
--border-subtle:  rgba(0,0,0,0.06);
--border-default: rgba(0,0,0,0.12);
--border-strong:  rgba(0,0,0,0.24);
--border-focus:   var(--blue-500);

/* Interactive */
--accent:         var(--blue-600);
--accent-hover:   var(--blue-700);
--accent-muted:   rgba(37,99,235,0.08);
--danger:         #dc2626;
--danger-muted:   #fef2f2;
--success:        #16a34a;
--success-muted:  #f0fdf4;
--warning:        #d97706;
--warning-muted:  #fffbeb;

/* ── Tầng 3: Component (ví dụ) ─────────────────── */
--sidebar-bg:    var(--bg-sunken);
--sidebar-width: 240px;
--panel-width:   320px;
--topbar-height: 56px;
```

### 1.2 Dark theme

Khi cần dark mode, chỉ đổi tầng 2 — tầng 3 tự cập nhật:

```css
[data-theme="dark"] {
  --bg-base:      #0f1117;
  --bg-surface:   #161b25;
  --bg-elevated:  #1c2333;
  --bg-sunken:    #0b0e14;
  --text-primary:   #e8eaf0;
  --text-secondary: #9ba3b5;
  --text-tertiary:  #5c6478;
  --border-subtle:  rgba(255,255,255,0.05);
  --border-default: rgba(255,255,255,0.10);
}
```

Nguyên tắc dark theme:
- Background tối theo tầng: base < surface < elevated (ngược light theme)
- Không dùng màu thuần black (`#000`) — luôn có tint màu (xanh, tím nhẹ)
- Saturate accent lên 10-20% so với light version để bù mất contrast

### 1.3 Typography tokens

```css
/* Scale */
--text-xs:   10px;  /* micro label, badge */
--text-sm:   12px;  /* body phụ, tooltip */
--text-base: 14px;  /* body chính */
--text-md:   16px;  /* heading nhỏ */
--text-lg:   20px;  /* heading section */
--text-xl:   24px;  /* page title */
--text-2xl:  32px;  /* hero number */

/* Weight — chỉ dùng 2 trong 1 project */
--font-regular: 400;
--font-medium:  500;
/* 600/700 chỉ dùng khi cần bold làm điểm nhấn duy nhất */

/* Line height */
--leading-tight:  1.25;  /* heading */
--leading-normal: 1.5;   /* body */
--leading-loose:  1.75;  /* paragraph dài */

/* Font stack theo mục đích */
--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
--font-serif: 'Lora', 'Georgia', serif;      /* editorial, landing */
--font-mono: 'JetBrains Mono', 'Fira Code', monospace;  /* code, data */
```

### 1.4 Spacing & Shape tokens

```css
/* Spacing — 4px base grid */
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;

/* Border radius — phân biệt theo vai trò */
--radius-sm:   2px;   /* tag, badge — sharp, technical */
--radius-md:   4px;   /* button, input, card nhỏ */
--radius-lg:   6px;   /* panel, popover */
--radius-xl:   8px;   /* modal, sheet */
--radius-full: 9999px; /* pill, avatar */

/* Shadow */
--shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
--shadow-md: 0 4px 12px rgba(0,0,0,0.08);
--shadow-lg: 0 8px 24px rgba(0,0,0,0.12);
--shadow-focus: 0 0 0 3px var(--accent-muted);

/* Z-index system */
--z-base:    0;
--z-raised:  1;
--z-sticky:  10;
--z-overlay: 100;
--z-modal:   200;
--z-toast:   300;
```

---

## Phần 2 — Layout Architecture

### 2.1 Chọn pattern layout

**App shell — sidebar + main** (admin, dashboard, tool):
```
┌──────────┬──────────────────────────────────┐
│ Sidebar  │ Main                             │
│ fixed    │ flex col:                        │
│ 240px    │  ├─ Topbar (56px)               │
│          │  └─ Content (flex:1, scroll)     │
└──────────┴──────────────────────────────────┘
```

**App shell — sidebar + main + detail** (IDE-like, inspector):
```
┌──────────┬────────────────────┬─────────────┐
│ Sidebar  │ Main               │ Detail      │
│ 220px    │ flex: 1            │ 0→320px     │
│          │                    │ (slide in)  │
└──────────┴────────────────────┴─────────────┘
```

**Topbar + content** (landing, docs, simple app):
```
┌────────────────────────────────────────────┐
│ Topbar/Nav (56–64px)                       │
├────────────────────────────────────────────┤
│ Content (flex:1, overflow-y: auto)         │
│   hoặc sections full-width stacked         │
└────────────────────────────────────────────┘
```

**Centered column** (form, auth, article):
```
┌────────────────────────────────────────────┐
│            max-width: 640px                │
│            margin: 0 auto                  │
│            padding: 48px 24px              │
└────────────────────────────────────────────┘
```

### 2.2 Quy tắc bắt buộc

```css
/* Root shell — không bao giờ scroll toàn trang trong app */
.app-shell {
  height: 100vh;
  display: flex;
  overflow: hidden;
}

/* Mỗi vùng scroll độc lập */
.sidebar  { overflow-y: auto; }
.main     { flex: 1; overflow-y: auto; }
.detail   { overflow-y: auto; }

/* Detail panel — slide in/out */
.detail-panel {
  width: 0;
  transition: width 200ms ease;
  overflow: hidden;
}
.detail-panel.open {
  width: var(--panel-width);
}
```

### 2.3 Responsive strategy

```
Mobile first: < 640px  → stack dọc, sidebar thành bottom nav hoặc drawer
Tablet:  640–1024px   → sidebar thu nhỏ (icon only, 56px) hoặc overlay
Desktop: > 1024px     → layout đầy đủ
```

Breakpoint token:
```css
--breakpoint-sm: 640px;
--breakpoint-md: 768px;
--breakpoint-lg: 1024px;
--breakpoint-xl: 1280px;
```

---

## Phần 3 — Component Anatomy

Mỗi component có anatomy: slots rõ ràng + states đầy đủ + variants ngữ nghĩa.
Full CSS cho từng component trong `references/components.md`. Tóm tắt pattern:

### Quy tắc chung

- **Button**: `[icon?] [label] [trailing?]` — 3 sizes (sm/md/lg), 5 variants (primary/secondary/ghost/danger/link). Sizes: sm=28px, md=36px, lg=44px. Focus dùng `box-shadow: var(--shadow-focus)`, không bao giờ `outline: none` đơn thuần. Disabled: `opacity: 0.4; pointer-events: none`.
- **Input**: `[label] [input-wrapper] [hint|error]` — States: default/focus/error/disabled. Focus: `border-color: var(--border-focus)` + focus ring.
- **Badge**: `padding: 2px 6px; radius: var(--radius-sm); font-size: var(--text-xs)` — Variants: neutral/accent/success/danger/warning, tất cả dùng `--*-muted` bg.
- **Card**: `[header] [body] [footer]` — Variants: flat (border only) / raised (shadow-sm) / elevated (shadow-md).
- **Nav item**: `padding: 8px 12px; radius: var(--radius-md)` — Active state: `background: var(--bg-surface); font-weight: var(--font-medium)` + optional left accent bar `box-shadow: inset 3px 0 0 var(--accent)`.

### 3.6 Empty & Loading states

Mọi list, table, và data view phải có cả hai:

```jsx
/* Loading */
function Skeleton({ width = '100%', height = 16 }) {
  return (
    <div style={{ width, height, borderRadius: 'var(--radius-md)',
      background: 'var(--bg-sunken)',
      animation: 'pulse 1.5s ease infinite' }} />
  )
}

/* Empty */
function EmptyState({ icon, title, description, action }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column',
      alignItems: 'center', gap: 'var(--space-3)',
      padding: 'var(--space-12)', color: 'var(--text-tertiary)' }}>
      {icon && <div style={{ fontSize: 32, opacity: 0.3 }}>{icon}</div>}
      <p style={{ fontWeight: 'var(--font-medium)', color: 'var(--text-secondary)' }}>{title}</p>
      {description && <p style={{ fontSize: 'var(--text-sm)' }}>{description}</p>}
      {action}
    </div>
  )
}
```

Quy tắc: Empty state mô tả **hành động cần làm**, không phải trạng thái ("No data" → "Add your first item").

---

## Phần 4 — Interaction Patterns

### 4.1 Micro-interactions

Mỗi interaction feedback phải có: duration + easing + property rõ ràng.

```css
/* Hover */
transition: background 120ms ease, color 120ms ease;

/* Focus */
transition: box-shadow 120ms ease;

/* Expand/collapse */
transition: max-height 200ms ease, opacity 200ms ease;

/* Slide in panel */
transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1);

/* Scale on click */
:active { transform: scale(0.98); }
```

Nguyên tắc:
- Hover: 80–150ms
- Panel open/close: 180–250ms
- Page transition: 200–300ms
- Không dùng `transition: all` — chỉ property cụ thể

### 4.2 Debounce pattern

```js
// Search, resize, scroll
function useDebounce(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

// Usage
const debouncedSearch = useDebounce(searchInput, 300)
useEffect(() => {
  if (debouncedSearch) fetchResults(debouncedSearch)
}, [debouncedSearch])
```

### 4.3 Optimistic UI

Khi user thực hiện action (mark, delete, toggle), update UI ngay — rollback nếu lỗi:

```js
async function markTested(name) {
  // Update ngay
  setItems(prev => prev.map(i => i.name === name ? { ...i, tested: true } : i))
  try {
    await api.post(`/node/${name}/mark_tested`)
  } catch {
    // Rollback
    setItems(prev => prev.map(i => i.name === name ? { ...i, tested: false } : i))
    showToast('error', 'Failed to update. Try again.')
  }
}
```

### 4.4 Selection & Detail panel

Click item → mở panel, click lại item đó → đóng panel (toggle). Click outside → đóng.

```js
function handleSelect(item) {
  setSelected(prev => prev?.id === item.id ? null : item)
}
```

### 4.5 Keyboard navigation

Bắt buộc cho mọi interactive component:
- `Tab` / `Shift+Tab`: focus order hợp lý
- `Enter` / `Space`: activate button, checkbox
- `Escape`: đóng modal, popover, panel
- `Arrow keys`: navigate list, table row

```js
// Close on Escape
useEffect(() => {
  const handler = (e) => { if (e.key === 'Escape') onClose() }
  document.addEventListener('keydown', handler)
  return () => document.removeEventListener('keydown', handler)
}, [onClose])
```

---

## Phần 5 — Data Patterns

### 5.1 Custom hook template

Không fetch trong component body. Mọi async data đi qua hook với 3 trường: `{ data, loading, error }`. Luôn có cleanup `cancelled = true` để tránh setState sau unmount. Pattern:

```js
function useData(url, params) {
  const [state, setState] = useState({ data: null, loading: true, error: null })
  useEffect(() => {
    let cancelled = false
    setState(s => ({ ...s, loading: true }))
    api.get(url, { params })
      .then(data => { if (!cancelled) setState({ data, loading: false, error: null }) })
      .catch(err  => { if (!cancelled) setState({ data: null, loading: false, error: err }) })
    return () => { cancelled = true }
  }, [url, JSON.stringify(params)])
  return state
}
```

### 5.2 Filter + sort state

Filter state luôn có `page: 1` reset khi filter thay đổi. Sort state: `{ key, dir: 'asc'|'desc' }`, toggle dir khi click cùng key, reset về `desc` khi đổi key. Chi tiết + pagination pattern trong `references/data-tables.md`.

---

## Phần 6 — Quality Checklist

Trước khi giao bất kỳ UI nào, kiểm tra:

**Token:**
- [ ] Không có màu hardcode trong JSX/CSS (ngoài canvas/svg)
- [ ] Tất cả text dùng `--text-*` token
- [ ] Tất cả background dùng `--bg-*` token

**Layout:**
- [ ] Shell có `height: 100vh; overflow: hidden`
- [ ] Mỗi scrollable vùng có `overflow-y: auto` riêng
- [ ] Không có scroll ngang trên desktop

**State:**
- [ ] Mọi list/table có loading state
- [ ] Mọi list/table có empty state
- [ ] Mọi async action có error handling

**Interaction:**
- [ ] Hover state rõ ràng
- [ ] Focus state visible (không bao giờ `outline: none` không có thay thế)
- [ ] Disabled state có `opacity` giảm + `cursor: not-allowed`
- [ ] Escape đóng modal/panel

**Copy (text):**
- [ ] Label mô tả action, không mô tả hệ thống
- [ ] Empty state có hướng dẫn hành động
- [ ] Error message nói được gì sai và cách fix

---

## Tham chiếu chi tiết

Đọc thêm khi cần:
- `references/data-tables.md` — sort, filter, pagination, sticky header
- `references/forms.md` — validation, multi-step, error states
- `references/dark-theme.md` — token system chi tiết cho dark UI
- `references/accessibility.md` — ARIA roles, contrast ratio, screen reader

---

## Anti-patterns

| ❌ Sai                           | ✅ Đúng                                              |
| ------------------------------- | --------------------------------------------------- |
| `color: #6b7280` hardcode       | `color: var(--text-secondary)`                      |
| `z-index: 9999`                 | Dùng `--z-modal: 200`                               |
| `transition: all 0.3s`          | `transition: background 120ms ease`                 |
| `outline: none` thuần           | `outline: none` + `box-shadow: var(--shadow-focus)` |
| Fetch trong render              | Fetch trong `useEffect` với cleanup                 |
| `font-weight: 700` tràn lan     | 400/500 thôi, 700 tối đa 1 điểm nhấn                |
| Empty list không có state       | Luôn có empty state với call-to-action              |
| Modal không có Escape           | Luôn `keydown → Escape → onClose`                   |
| `border-radius: 8px` cho tất cả | `2px/4px/6px/8px` theo vai trò component            |