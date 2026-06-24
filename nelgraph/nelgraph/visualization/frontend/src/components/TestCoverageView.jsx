import { useState, useEffect } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'

export default function TestCoverageView({ status, onMarkTested }) {
  const [untested, setUntested] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    axios.get(`${API}/functions?tested=false&limit=200`)
      .then(({ data }) => setUntested(data.data || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const totalFunctions = status?.total_functions || 0
  const testedCount = status?.tested_count || 0
  const coverage = totalFunctions > 0 ? Math.round(testedCount / totalFunctions * 100) : 0
  const highRisk = untested.filter(f => (f.complexity || 0) >= 5).length

  const coverageColor = coverage > 50 ? 'var(--color-success)' : coverage > 20 ? 'var(--color-warning)' : 'var(--color-danger)'

  // Group by community
  const grouped = {}
  untested.forEach(f => {
    const key = f.community_name || 'Uncategorized'
    if (!grouped[key]) grouped[key] = []
    grouped[key].push(f)
  })

  const handleMark = async (name) => {
    try {
      await axios.post(`${API}/node/${encodeURIComponent(name)}/mark_tested`)
      setUntested(prev => prev.filter(f => f.name !== name))
      onMarkTested?.(name)
    } catch {}
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      {/* Header stats */}
      <div style={{ padding: 16, display: 'flex', gap: 12, borderBottom: '0.5px solid var(--color-border-tertiary)', flexShrink: 0 }}>
        <div style={styles.bigCard}>
          <div style={styles.bigLabel}>Total tested</div>
          <div style={{ fontSize: 20, fontWeight: 500 }}>{testedCount} / {totalFunctions}</div>
          <div style={styles.progressBar}>
            <div style={{ ...styles.progressFill, width: `${coverage}%`, background: coverageColor }} />
          </div>
        </div>
        <div style={styles.bigCard}>
          <div style={styles.bigLabel}>Coverage</div>
          <div style={{ fontSize: 24, fontWeight: 500, color: coverageColor }}>{coverage}%</div>
        </div>
        <div style={styles.bigCard}>
          <div style={styles.bigLabel}>Untested high-complexity</div>
          <div style={{ fontSize: 24, fontWeight: 500, color: highRisk > 0 ? 'var(--color-danger)' : 'var(--color-text-tertiary)' }}>{highRisk}</div>
        </div>
      </div>

      {/* Grouped list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
        {loading ? (
          <div style={{ color: 'var(--color-text-tertiary)', fontSize: 12 }}>Loading untested functions...</div>
        ) : Object.keys(grouped).length === 0 ? (
          <div style={{ textAlign: 'center', padding: 32, color: 'var(--color-text-tertiary)' }}>
            <div style={{ fontSize: 24, marginBottom: 8, opacity: 0.3 }}>✓</div>
            <div style={{ fontWeight: 500, color: 'var(--color-text-secondary)' }}>All functions tested!</div>
          </div>
        ) : (
          Object.entries(grouped).map(([community, funcs]) => (
            <div key={community} style={{ marginBottom: 16 }}>
              <div style={styles.groupHeader}>{community}</div>
              {funcs.map(f => (
                <div key={f.name} style={styles.funcItem}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 500 }}>{f.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>{f.file}</div>
                  </div>
                  {(f.complexity || 0) >= 5 && (
                    <span style={styles.complexityBadge}>{f.complexity}</span>
                  )}
                  <button onClick={() => handleMark(f.name)} style={styles.markBtn}>Mark tested</button>
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

const styles = {
  bigCard: {
    flex: 1, background: 'var(--color-background-secondary)', borderRadius: 'var(--radius-lg)',
    padding: '14px 16px',
  },
  bigLabel: { fontSize: 10, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.3px', marginBottom: 6 },
  progressBar: { height: 4, background: 'var(--color-background-tertiary)', borderRadius: 2, marginTop: 8, overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 2, transition: 'width 300ms ease' },
  groupHeader: { fontSize: 11, fontWeight: 500, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.3px', padding: '8px 0 4px', borderBottom: '0.5px solid var(--color-border-tertiary)', marginBottom: 4 },
  funcItem: { display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '0.5px solid var(--color-border-tertiary)' },
  complexityBadge: { fontSize: 10, padding: '2px 6px', borderRadius: 2, background: 'var(--color-danger-muted)', color: 'var(--color-danger)', fontWeight: 500 },
  markBtn: { fontSize: 11, padding: '4px 10px', borderRadius: 'var(--radius-md)', border: 'none', background: 'var(--badge-tested-bg)', color: 'var(--badge-tested-color)', cursor: 'pointer', fontWeight: 500, flexShrink: 0 },
}
