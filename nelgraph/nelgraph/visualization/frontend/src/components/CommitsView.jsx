import { useState, useEffect } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'

function formatRelativeTime(timestamp) {
  if (!timestamp) return ''
  const diff = (Date.now() - new Date(timestamp).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export default function CommitsView() {
  const [commits, setCommits] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState({})

  useEffect(() => {
    axios.get(`${API}/commits?limit=30`)
      .then(({ data }) => setCommits(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div style={{ padding: 16 }}>
      {[1,2,3].map(i => (
        <div key={i} style={{ padding: 12, marginBottom: 8 }}>
          <div style={{ width: '40%', height: 12, background: 'var(--color-background-tertiary)', borderRadius: 4, animation: 'pulse 1.5s ease infinite' }} />
          <div style={{ width: '70%', height: 10, background: 'var(--color-background-tertiary)', borderRadius: 4, marginTop: 8, animation: 'pulse 1.5s ease infinite' }} />
        </div>
      ))}
    </div>
  )

  if (commits.length === 0) return (
    <div style={{ padding: 48, textAlign: 'center', color: 'var(--color-text-tertiary)' }}>
      <div style={{ fontSize: 24, marginBottom: 8, opacity: 0.3 }}>●</div>
      <div style={{ fontWeight: 500, color: 'var(--color-text-secondary)' }}>No commits indexed yet</div>
      <div style={{ fontSize: 12, marginTop: 4 }}>Run a sync to index commit history</div>
    </div>
  )

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
      {commits.map((c, i) => {
        const hash = (c.hash || '').slice(0, 7)
        const isExp = expanded[i]
        const funcs = (c.functions_affected || []).filter(Boolean)
        return (
          <div key={i} style={styles.commitItem}>
            {/* Timeline dot + line */}
            <div style={styles.timeline}>
              <div style={styles.dot} />
              {i < commits.length - 1 && <div style={styles.line} />}
            </div>
            {/* Content */}
            <div style={{ flex: 1, paddingBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={styles.hashBadge}>{hash}</span>
                <span style={{ fontSize: 12, fontWeight: 500, flex: 1 }}>{c.message || 'No message'}</span>
                {c.files_changed != null && (
                  <span style={styles.filesBadge}>{c.files_changed} files</span>
                )}
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
                {c.author || 'Unknown'} · {formatRelativeTime(c.timestamp)}
              </div>
              {funcs.length > 0 && (
                <button onClick={() => setExpanded(p => ({ ...p, [i]: !p[i] }))} style={styles.expandBtn}>
                  {isExp ? '▾' : '▸'} {funcs.length} functions affected
                </button>
              )}
              {isExp && funcs.length > 0 && (
                <div style={styles.funcList}>
                  {funcs.map((fn, j) => (
                    <div key={j} style={styles.funcItem}>ƒ {fn}</div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

const styles = {
  commitItem: { display: 'flex', gap: 12 },
  timeline: { display: 'flex', flexDirection: 'column', alignItems: 'center', width: 20, flexShrink: 0 },
  dot: { width: 8, height: 8, borderRadius: '50%', background: 'var(--color-border-secondary)', border: '2px solid var(--color-background-primary)', flexShrink: 0, marginTop: 4 },
  line: { width: 1, flex: 1, background: 'var(--color-border-tertiary)' },
  hashBadge: { fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 6px', borderRadius: 'var(--radius-sm)', background: 'var(--color-background-tertiary)', color: 'var(--color-text-tertiary)', flexShrink: 0 },
  filesBadge: { fontSize: 10, padding: '2px 6px', borderRadius: 'var(--radius-sm)', background: 'var(--color-background-secondary)', color: 'var(--color-text-tertiary)', flexShrink: 0 },
  expandBtn: { fontSize: 11, color: 'var(--color-accent)', background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0 0', display: 'block' },
  funcList: { marginTop: 6, padding: '6px 0', borderLeft: '2px solid var(--color-border-tertiary)', paddingLeft: 10 },
  funcItem: { fontSize: 11, color: 'var(--color-text-secondary)', padding: '2px 0' },
}
