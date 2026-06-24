import { useState, useEffect } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'
const COMMUNITY_COLORS = ['#378ADD','#7F77DD','#1D9E75','#D85A30','#BA7517','#888780']

export default function CommunitiesView({ onViewInGraph }) {
  const [communities, setCommunities] = useState([])
  const [expanded, setExpanded] = useState({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    axios.get(`${API}/communities`)
      .then(({ data }) => setCommunities(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingState />

  return (
    <div style={{ padding: 16, overflowY: 'auto', flex: 1 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {communities.map((c, i) => {
          const isExpanded = expanded[c.id]
          const summary = c.summary || ''
          const needsTruncate = summary.length > 150
          return (
            <div key={c.id} style={styles.card}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: COMMUNITY_COLORS[i % 6], flexShrink: 0 }} />
                <span style={{ fontSize: 14, fontWeight: 500, flex: 1 }}>{c.name}</span>
                <span style={styles.memberBadge}>{c.member_count} nodes</span>
              </div>
              <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.6, margin: 0 }}>
                {isExpanded || !needsTruncate ? summary : summary.slice(0, 150) + '...'}
              </p>
              {needsTruncate && (
                <button onClick={() => setExpanded(p => ({ ...p, [c.id]: !p[c.id] }))}
                  style={styles.showMore}>
                  {isExpanded ? 'show less' : 'show more'}
                </button>
              )}
              <div style={{ marginTop: 10, borderTop: '0.5px solid var(--color-border-tertiary)', paddingTop: 8 }}>
                <button onClick={() => onViewInGraph(c)} style={styles.viewBtn}>View in graph →</button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function LoadingState() {
  return (
    <div style={{ padding: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      {[1,2,3,4].map(i => (
        <div key={i} style={{ ...styles.card, height: 120 }}>
          <div style={{ width: '60%', height: 14, background: 'var(--color-background-tertiary)', borderRadius: 4, animation: 'pulse 1.5s ease infinite' }} />
          <div style={{ width: '100%', height: 10, background: 'var(--color-background-tertiary)', borderRadius: 4, marginTop: 12, animation: 'pulse 1.5s ease infinite' }} />
          <div style={{ width: '80%', height: 10, background: 'var(--color-background-tertiary)', borderRadius: 4, marginTop: 6, animation: 'pulse 1.5s ease infinite' }} />
        </div>
      ))}
    </div>
  )
}

const styles = {
  card: {
    background: 'var(--color-background-primary)',
    border: '0.5px solid var(--color-border-tertiary)',
    borderRadius: 'var(--radius-lg)', padding: 14,
  },
  memberBadge: {
    fontSize: 10, padding: '2px 6px', borderRadius: 'var(--radius-sm)',
    background: 'var(--color-background-tertiary)', color: 'var(--color-text-tertiary)',
  },
  showMore: {
    fontSize: 11, color: 'var(--color-accent)', background: 'none',
    border: 'none', cursor: 'pointer', padding: 0, marginTop: 4,
  },
  viewBtn: {
    fontSize: 12, color: 'var(--color-accent)', background: 'none',
    border: 'none', cursor: 'pointer', padding: 0, fontWeight: 500,
  },
}
