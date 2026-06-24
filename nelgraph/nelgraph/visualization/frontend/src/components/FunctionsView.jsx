import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'
const PAGE_SIZE = 50

const COLUMNS = [
  { key: 'name', label: 'Name' },
  { key: 'file', label: 'File' },
  { key: 'class_name', label: 'Class' },
  { key: 'complexity', label: 'Complexity' },
  { key: 'is_async', label: 'Async' },
  { key: 'tested', label: 'Tested' },
  { key: 'community_name', label: 'Community' },
]

export default function FunctionsView({ onNodeClick, communities }) {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [sort, setSort] = useState({ key: 'complexity', dir: 'desc' })
  const [filters, setFilters] = useState({ untestedOnly: false, highComplexity: false, community: '' })
  const [comms, setComms] = useState([])

  useEffect(() => {
    if (communities) setComms(communities)
    else axios.get(`${API}/communities`).then(({ data }) => setComms(data)).catch(() => {})
  }, [communities])

  const loadData = async (reset = false) => {
    setLoading(true)
    const params = new URLSearchParams()
    params.set('limit', PAGE_SIZE)
    params.set('offset', reset ? 0 : offset)
    if (filters.untestedOnly) params.set('tested', 'false')
    if (filters.highComplexity) params.set('high_complexity', 'true')
    if (filters.community) params.set('community_id', filters.community)

    try {
      const { data } = await axios.get(`${API}/functions?${params}`)
      if (reset) { setRows(data.data); setOffset(PAGE_SIZE) }
      else { setRows(prev => [...prev, ...data.data]); setOffset(o => o + PAGE_SIZE) }
      setTotal(data.total)
    } catch {}
    setLoading(false)
  }

  useEffect(() => { loadData(true) }, [filters])

  const sorted = useMemo(() =>
    [...rows].sort((a, b) => {
      const v = sort.dir === 'asc' ? 1 : -1
      const av = a[sort.key], bv = b[sort.key]
      if (av == null) return 1; if (bv == null) return -1
      return av > bv ? v : av < bv ? -v : 0
    }), [rows, sort])

  const toggleSort = (key) => {
    setSort(prev => prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      {/* Filters */}
      <div style={styles.filterBar}>
        <FilterToggle active={filters.untestedOnly} onChange={v => setFilters(f => ({ ...f, untestedOnly: v }))}>Untested only</FilterToggle>
        <FilterToggle active={filters.highComplexity} onChange={v => setFilters(f => ({ ...f, highComplexity: v }))}>High complexity (≥5)</FilterToggle>
        <select value={filters.community} onChange={e => setFilters(f => ({ ...f, community: e.target.value }))} style={styles.select}>
          <option value="">All communities</option>
          {comms.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      {/* Table */}
      <div style={styles.tableWrapper}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {COLUMNS.map(col => (
                <th key={col.key} onClick={() => toggleSort(col.key)} style={styles.th}>
                  {col.label}
                  {sort.key === col.key && <span style={{ marginLeft: 4, fontSize: 10 }}>{sort.dir === 'asc' ? '▲' : '▼'}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <tr key={i} onClick={() => onNodeClick({ name: row.name, type: 'Function' })} style={styles.row}>
                <td style={styles.td}><span style={{ fontWeight: 500 }}>{row.name}</span></td>
                <td style={{ ...styles.td, color: 'var(--color-text-tertiary)', fontSize: 11 }}>{row.file}</td>
                <td style={{ ...styles.td, fontSize: 11 }}>{row.class_name || '–'}</td>
                <td style={styles.td}><ComplexityBadge value={row.complexity} /></td>
                <td style={styles.td}>{row.is_async ? '⚡' : '–'}</td>
                <td style={styles.td}>{row.tested ? <span style={styles.testedBadge}>✓</span> : '–'}</td>
                <td style={{ ...styles.td, fontSize: 11, color: 'var(--color-accent)' }}>{row.community_name || '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {sorted.length === 0 && !loading && (
          <div style={styles.empty}>No functions found matching your filters.</div>
        )}
        {rows.length < total && (
          <button onClick={() => loadData(false)} disabled={loading} style={styles.loadMore}>
            {loading ? 'Loading...' : `Load more (${rows.length}/${total})`}
          </button>
        )}
      </div>
    </div>
  )
}

function FilterToggle({ active, onChange, children }) {
  return (
    <button onClick={() => onChange(!active)}
      style={{
        ...styles.filterChip,
        background: active ? 'var(--color-accent-muted)' : 'transparent',
        borderColor: active ? 'var(--color-accent)' : 'var(--color-border-primary)',
        color: active ? 'var(--color-accent)' : 'var(--color-text-secondary)',
      }}>{children}</button>
  )
}

function ComplexityBadge({ value }) {
  if (value == null) return <span style={{ fontSize: 12, color: 'var(--color-text-tertiary)' }}>–</span>
  const level = value >= 5 ? 'high' : value >= 3 ? 'mid' : 'low'
  const colorMap = { high: 'var(--color-danger)', mid: 'var(--color-warning)', low: 'var(--color-text-tertiary)' }
  const bars = Math.min(value, 8)
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: colorMap[level] }}>
      {value}
      <span style={{ height: 3, width: bars * 4, borderRadius: 2, background: 'currentColor', opacity: 0.5 }} />
    </span>
  )
}

const styles = {
  filterBar: { padding: '10px 16px', display: 'flex', gap: 8, alignItems: 'center', borderBottom: '0.5px solid var(--color-border-tertiary)', flexShrink: 0 },
  filterChip: { padding: '4px 10px', borderRadius: 4, fontSize: 12, border: '1px solid', cursor: 'pointer', transition: 'all 120ms' },
  select: { fontSize: 12, padding: '4px 8px', borderRadius: 4, border: '1px solid var(--color-border-primary)', background: 'var(--color-background-primary)', color: 'var(--color-text-primary)', cursor: 'pointer' },
  tableWrapper: { flex: 1, overflowY: 'auto' },
  th: { position: 'sticky', top: 0, background: 'var(--color-background-primary)', borderBottom: '1px solid var(--color-border-primary)', padding: '8px 12px', textAlign: 'left', fontSize: 11, fontWeight: 500, color: 'var(--color-text-tertiary)', cursor: 'pointer', userSelect: 'none', zIndex: 1, textTransform: 'uppercase', letterSpacing: '0.3px' },
  td: { padding: '7px 12px', fontSize: 12, borderBottom: '0.5px solid var(--color-border-tertiary)' },
  row: { cursor: 'pointer', transition: 'background 80ms ease' },
  testedBadge: { fontSize: 10, padding: '1px 5px', borderRadius: 2, background: 'var(--badge-tested-bg)', color: 'var(--badge-tested-color)' },
  empty: { padding: 32, textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: 13 },
  loadMore: { width: '100%', padding: '10px', border: 'none', borderTop: '0.5px solid var(--color-border-tertiary)', background: 'var(--color-background-secondary)', color: 'var(--color-text-secondary)', cursor: 'pointer', fontSize: 12 },
}
