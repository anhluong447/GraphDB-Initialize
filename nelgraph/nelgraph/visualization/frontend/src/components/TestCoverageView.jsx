import { useState, useEffect } from 'react'
import axios from 'axios'
import BulkReportDrawer from './BulkReportDrawer'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'

export default function TestCoverageView({ status, onMarkTested, onGenerateTest }) {
  const [untested, setUntested] = useState([])
  const [loading, setLoading] = useState(true)
  
  // Bulk test states
  const [bulkTaskId, setBulkTaskId] = useState(() => localStorage.getItem('nelgraph_bulk_task_id') || null)
  const [bulkStatus, setBulkStatus] = useState(() => localStorage.getItem('nelgraph_bulk_status') || null)
  const [bulkProgress, setBulkProgress] = useState(() => {
    try {
      const saved = localStorage.getItem('nelgraph_bulk_progress')
      return saved ? JSON.parse(saved) : null
    } catch {
      return null
    }
  })
  const [bulkSummary, setBulkSummary] = useState(() => {
    try {
      const saved = localStorage.getItem('nelgraph_bulk_summary')
      return saved ? JSON.parse(saved) : null
    } catch {
      return null
    }
  })
  
  // Inspector state
  const [inspectTaskId, setInspectTaskId] = useState(null)

  // Synchronize bulk states to localStorage
  useEffect(() => {
    if (bulkTaskId) localStorage.setItem('nelgraph_bulk_task_id', bulkTaskId)
    else localStorage.removeItem('nelgraph_bulk_task_id')
  }, [bulkTaskId])

  useEffect(() => {
    if (bulkStatus) localStorage.setItem('nelgraph_bulk_status', bulkStatus)
    else localStorage.removeItem('nelgraph_bulk_status')
  }, [bulkStatus])

  useEffect(() => {
    if (bulkProgress) localStorage.setItem('nelgraph_bulk_progress', JSON.stringify(bulkProgress))
    else localStorage.removeItem('nelgraph_bulk_progress')
  }, [bulkProgress])

  useEffect(() => {
    if (bulkSummary) localStorage.setItem('nelgraph_bulk_summary', JSON.stringify(bulkSummary))
    else localStorage.removeItem('nelgraph_bulk_summary')
  }, [bulkSummary])

  useEffect(() => {
    axios.get(`${API}/functions?tested=false&limit=200`)
      .then(({ data }) => setUntested(data.data || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!bulkTaskId || bulkStatus !== 'running') return

    const interval = setInterval(async () => {
      try {
        const { data } = await axios.get(`${API}/task/${bulkTaskId}/status`)
        if (data.status === 'running') {
          if (data.progress) {
            setBulkProgress(data.progress)
          }
        } else if (data.status === 'done') {
          setBulkStatus('done')
          if (data.result && data.result.summary) {
            setBulkSummary(data.result.summary)
          }
          setInspectTaskId(bulkTaskId) // Auto popup report window!
          setBulkTaskId(null)
          // Refresh untested list
          const res = await axios.get(`${API}/functions?tested=false&limit=200`)
          setUntested(res.data.data || [])
        } else if (data.status === 'error') {
          setBulkStatus('error')
          setBulkTaskId(null)
        }
      } catch (err) {
        // fail silently
      }
    }, 3000)

    return () => clearInterval(interval)
  }, [bulkTaskId, bulkStatus])

  const startBulkTest = async () => {
    if (untested.length === 0) return
    try {
      setBulkStatus('running')
      setBulkProgress({ done: 0, total: untested.length, current: 'Initializing...' })
      setBulkSummary(null)
      const { data } = await axios.post(`${API}/generate_tests/all`, { mode: 'unit' })
      if (data.task_id) {
        setBulkTaskId(data.task_id)
      } else if (data.status === 'done') {
        setBulkStatus('done')
        setBulkProgress(null)
      }
    } catch (err) {
      setBulkStatus('error')
      setBulkProgress(null)
    }
  }

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
      <div style={{ padding: 16, display: 'flex', gap: 12, borderBottom: '0.5px solid var(--color-border-tertiary)', flexShrink: 0, flexWrap: 'wrap' }}>
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
        
        {/* Generate All Tests trigger button */}
        <div 
          style={{ 
            ...styles.bigCard, 
            display: 'flex', 
            flexDirection: 'column', 
            justifyContent: 'center', 
            alignItems: 'center', 
            cursor: bulkStatus === 'running' || untested.length === 0 ? 'not-allowed' : 'pointer',
            border: '1px solid var(--color-accent-muted)',
            background: 'var(--color-background-tertiary)'
          }} 
          onClick={bulkStatus === 'running' || untested.length === 0 ? null : startBulkTest}
        >
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-accent)', display: 'flex', alignItems: 'center', gap: 6 }}>
            {bulkStatus === 'running' ? '⏳ Running...' : '🚀 Generate All Tests'}
          </div>
          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', marginTop: 4 }}>
            {untested.length} untested functions
          </div>
        </div>

        {/* View Latest Report button */}
        <div 
          style={{ 
            ...styles.bigCard, 
            display: 'flex', 
            flexDirection: 'column', 
            justifyContent: 'center', 
            alignItems: 'center', 
            cursor: 'pointer',
            border: '1px solid var(--color-border-secondary)',
            background: 'var(--color-background-tertiary)',
            transition: 'all 0.2s ease'
          }} 
          onClick={() => setInspectTaskId('latest')}
        >
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-secondary)', display: 'flex', alignItems: 'center', gap: 6 }}>
            📋 View Latest Report
          </div>
          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', marginTop: 4 }}>
            Review previous batch runs
          </div>
        </div>
      </div>

      {/* Bulk progress banner */}
      {bulkStatus === 'running' && bulkProgress && (
        <div style={styles.banner}>
          <div style={{ fontWeight: 500, marginBottom: 6, fontSize: 12 }}>🚀 Generating All Tests (Bulk Mode)...</div>
          <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span>Current: <strong style={{ color: 'var(--color-accent)' }}>{bulkProgress.current || 'Planning...'}</strong></span>
            <span>{bulkProgress.done} / {bulkProgress.total}</span>
          </div>
          <div style={styles.progressBar}>
            <div style={{ ...styles.progressFill, width: `${(bulkProgress.done / (bulkProgress.total || 1)) * 100}%`, background: 'var(--color-accent)' }} />
          </div>
        </div>
      )}

      {/* Bulk complete summary banner */}
      {bulkStatus === 'done' && bulkSummary && (
        <div style={{ ...styles.banner, borderLeft: '4px solid var(--color-success)', background: 'rgba(46, 204, 113, 0.1)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontWeight: 500, color: 'var(--color-success)', fontSize: 12 }}>✓ Bulk Test Generation Completed!</span>
            <button onClick={() => setBulkSummary(null)} style={{ border: 'none', background: 'transparent', color: 'var(--color-text-secondary)', cursor: 'pointer', fontSize: 14 }}>×</button>
          </div>
          <div style={{ fontSize: 11, display: 'flex', gap: 16, alignItems: 'center' }}>
            <span>Total: <strong>{bulkSummary.total}</strong></span>
            <span>Passed: <strong style={{ color: 'var(--color-success)' }}>{bulkSummary.passed}</strong></span>
            <span>Failed: <strong style={{ color: 'var(--color-danger)' }}>{bulkSummary.failed}</strong></span>
            {bulkSummary.skipped > 0 && <span>Skipped: <strong>{bulkSummary.skipped}</strong></span>}
            {bulkSummary.bugs_found > 0 && <span>Bugs: <strong style={{ color: 'var(--color-danger)' }}>{bulkSummary.bugs_found}</strong></span>}
            <button 
              onClick={() => setInspectTaskId('latest')} 
              style={{
                marginLeft: 'auto',
                padding: '3px 8px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--color-success)',
                background: 'rgba(46, 204, 113, 0.15)',
                color: 'var(--color-success)',
                cursor: 'pointer',
                fontSize: '11px',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 4
              }}
            >
              📋 Review Report
            </button>
          </div>
        </div>
      )}

      {/* Bulk error banner */}
      {bulkStatus === 'error' && (
        <div style={{ ...styles.banner, borderLeft: '4px solid var(--color-danger)', background: 'rgba(231, 76, 60, 0.1)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 500, color: 'var(--color-danger)', fontSize: 12 }}>❌ Bulk Test Generation Failed</span>
            <button onClick={() => setBulkStatus(null)} style={{ border: 'none', background: 'transparent', color: 'var(--color-text-secondary)', cursor: 'pointer' }}>×</button>
          </div>
        </div>
      )}

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
                  {onGenerateTest && (
                    <button onClick={() => onGenerateTest({ name: f.name, file: f.file, class_name: f.class_name })} style={styles.genBtn}>🧪 Gen</button>
                  )}
                  <button onClick={() => handleMark(f.name)} style={styles.markBtn}>Mark tested</button>
                </div>
              ))}
            </div>
          ))
        )}
      </div>

      {/* Bulk Report Drawer Modal */}
      {inspectTaskId && (
        <BulkReportDrawer taskId={inspectTaskId} onClose={() => setInspectTaskId(null)} />
      )}
    </div>
  )
}

const styles = {
  bigCard: {
    flex: 1, background: 'var(--color-background-secondary)', borderRadius: 'var(--radius-lg)',
    padding: '14px 16px', minWidth: 160
  },
  bigLabel: { fontSize: 10, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.3px', marginBottom: 6 },
  progressBar: { height: 4, background: 'var(--color-background-tertiary)', borderRadius: 2, marginTop: 8, overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 2, transition: 'width 300ms ease' },
  groupHeader: { fontSize: 11, fontWeight: 500, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.3px', padding: '8px 0 4px', borderBottom: '0.5px solid var(--color-border-tertiary)', marginBottom: 4 },
  funcItem: { display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '0.5px solid var(--color-border-tertiary)' },
  complexityBadge: { fontSize: 10, padding: '2px 6px', borderRadius: 2, background: 'var(--color-danger-muted)', color: 'var(--color-danger)', fontWeight: 500 },
  genBtn: { fontSize: 11, padding: '4px 10px', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-accent)', background: 'var(--color-accent-muted)', color: 'var(--color-accent)', cursor: 'pointer', fontWeight: 500, flexShrink: 0 },
  markBtn: { fontSize: 11, padding: '4px 10px', borderRadius: 'var(--radius-md)', border: 'none', background: 'var(--badge-tested-bg)', color: 'var(--badge-tested-color)', cursor: 'pointer', fontWeight: 500, flexShrink: 0 },
  banner: {
    margin: '16px 16px 0',
    padding: '12px 16px',
    background: 'var(--color-background-secondary)',
    borderLeft: '4px solid var(--color-accent)',
    borderRadius: 'var(--radius-md)',
  }
}

