# Data Table Patterns

## Anatomy

```
┌──────────────────────────────────────────────────────┐
│ [Filters bar: toggle chips + dropdown]               │
├──────────────────────────────────────────────────────┤
│ NAME ↑  │ FILE    │ COMPLEXITY │ TESTED │ COMMUNITY  │  ← sticky header
├──────────────────────────────────────────────────────┤
│ authUser │ auth.py │    7 ████  │   ✓   │ Auth       │  ← row
│ parseJWT │ jwt.py  │    3 ██   │        │ Auth       │
└──────────────────────────────────────────────────────┘
│                        Load more (50/247)            │
```

## Sort State

```js
const [sort, setSort] = useState({ key: 'complexity', dir: 'desc' })

function toggleSort(key) {
  setSort(prev =>
    prev.key === key
      ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
      : { key, dir: 'desc' }
  )
}

const sorted = useMemo(() =>
  [...data].sort((a, b) => {
    const v = sort.dir === 'asc' ? 1 : -1
    return a[sort.key] > b[sort.key] ? v : -v
  }),
  [data, sort]
)
```

## Filter Chips (toggle style)

```jsx
<div className="filter-bar">
  <FilterToggle
    active={filters.untestedOnly}
    onChange={v => setFilters(f => ({ ...f, untestedOnly: v }))}
  >
    Untested only
  </FilterToggle>
  <FilterToggle
    active={filters.highComplexity}
    onChange={v => setFilters(f => ({ ...f, highComplexity: v }))}
  >
    High complexity (≥5)
  </FilterToggle>
  <select onChange={e => setFilters(f => ({ ...f, community: e.target.value }))}>
    <option value="">All communities</option>
    {communities.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
  </select>
</div>
```

```css
.filter-toggle {
  padding: 4px 10px; border-radius: 4px; font-size: 12px;
  border: 1px solid var(--color-border-primary);
  background: transparent; color: var(--color-text-secondary);
  cursor: pointer; transition: all 120ms;
}
.filter-toggle.active {
  background: var(--color-accent-muted);
  border-color: var(--color-accent);
  color: var(--color-accent);
}
```

## Complexity visualization

Complexity badge với bar thay vì chỉ số thuần:

```jsx
function ComplexityBadge({ value }) {
  const level = value >= 5 ? 'high' : value >= 3 ? 'mid' : 'low'
  const bars = Math.min(value, 8)  // cap tại 8 bars
  return (
    <span className={`complexity complexity-${level}`}>
      {value}
      <span className="complexity-bar" style={{ width: bars * 4 + 'px' }} />
    </span>
  )
}
```

```css
.complexity { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; }
.complexity-bar { height: 3px; border-radius: 2px; background: currentColor; opacity: 0.5; }
.complexity-high { color: var(--color-danger); }
.complexity-mid  { color: var(--color-warning); }
.complexity-low  { color: var(--color-text-tertiary); }
```

## Pagination — Load More pattern

```jsx
const PAGE_SIZE = 50
const [offset, setOffset] = useState(0)
const [rows, setRows] = useState([])
const [total, setTotal] = useState(0)
const [loading, setLoading] = useState(false)

async function loadMore() {
  setLoading(true)
  const res = await api.get(`/functions?limit=${PAGE_SIZE}&offset=${offset}`, { params: filters })
  setRows(prev => [...prev, ...res.data])
  setTotal(res.total)
  setOffset(o => o + PAGE_SIZE)
  setLoading(false)
}

// Reset khi filter thay đổi
useEffect(() => {
  setRows([])
  setOffset(0)
  loadMore()
}, [filters])
```

```jsx
{rows.length < total && (
  <button className="load-more" onClick={loadMore} disabled={loading}>
    {loading ? 'Loading...' : `Load more (${rows.length}/${total})`}
  </button>
)}
```

## Row click → Detail panel

Click row mở detail panel bên phải, **không navigate**. Giữ nguyên sort/filter/scroll.

```jsx
<tr
  className={selectedNode?.name === row.name ? 'row-selected' : ''}
  onClick={() => setSelectedNode(row)}
>
```

```css
.row-selected { background: var(--color-accent-muted); }
tr:hover { background: var(--color-background-secondary); }
```

## Sticky header

```css
.table-wrapper {
  overflow-y: auto;
  flex: 1;
}
thead th {
  position: sticky;
  top: 0;
  background: var(--color-background-primary);
  z-index: 1;
  border-bottom: 1px solid var(--color-border-primary);
}
```

## Sort header button

```jsx
function SortHeader({ label, sortKey, currentSort, onSort }) {
  const active = currentSort.key === sortKey
  return (
    <th onClick={() => onSort(sortKey)} style={{ cursor: 'pointer', userSelect: 'none' }}>
      <span>{label}</span>
      <ChevronIcon
        direction={active && currentSort.dir === 'asc' ? 'up' : 'down'}
        style={{ opacity: active ? 1 : 0, transition: 'opacity 120ms' }}
      />
    </th>
  )
}
```