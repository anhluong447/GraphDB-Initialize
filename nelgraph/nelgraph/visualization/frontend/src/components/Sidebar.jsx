import { useState, useEffect } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'

const COMMUNITY_COLORS = ['#378ADD','#7F77DD','#1D9E75','#D85A30','#BA7517','#888780']

const NAV_ITEMS = [
  { key: 'graph', label: 'Graph', icon: '⬡' },
  { key: 'communities', label: 'Communities', icon: '▦' },
  { key: 'functions', label: 'Functions', icon: 'ƒ' },
  { key: 'coverage', label: 'Test coverage', icon: '✓' },
  { key: 'commits', label: 'Commits', icon: '●' },
]

function formatSyncTime(isoStr) {
  if (!isoStr) return 'never'
  const diff = (Date.now() - new Date(isoStr).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

export default function Sidebar({ activeView, onViewChange, onCommunityClick, status, onSync }) {
  const [communities, setCommunities] = useState([])
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    axios.get(`${API}/communities`).then(({ data }) => setCommunities(data)).catch(() => {})
  }, [])

  const handleSync = async () => {
    setSyncing(true)
    try { await onSync() } catch {}
    setTimeout(() => setSyncing(false), 2000)
  }

  const folderName = status?.codebase_path?.split(/[/\\]/).filter(Boolean).pop() || ''

  return (
    <div style={styles.sidebar}>
      {/* Header */}
      <div style={styles.header}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 18, opacity: 0.7 }}>⬡</span>
          <span style={{ fontSize: 14, fontWeight: 500 }}>{status?.project_name || 'NelGraph'}</span>
        </div>
        <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginTop: 2 }}>
          {folderName} · {status?.total_functions || 0} nodes
        </div>
      </div>

      {/* Navigation */}
      <div style={styles.nav}>
        {NAV_ITEMS.map(item => (
          <button
            key={item.key}
            onClick={() => onViewChange(item.key)}
            style={{
              ...styles.navItem,
              background: activeView === item.key ? 'var(--color-background-primary)' : 'transparent',
              fontWeight: activeView === item.key ? 500 : 400,
              color: activeView === item.key ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
            }}
          >
            <span style={{ width: 20, textAlign: 'center', fontSize: 13 }}>{item.icon}</span>
            {item.label}
          </button>
        ))}
      </div>

      {/* Community list */}
      <div style={styles.communitySection}>
        <div style={styles.sectionLabel}>Communities</div>
        <div style={styles.communityList}>
          {communities.map((c, i) => (
            <button key={c.id} onClick={() => onCommunityClick(c)} style={styles.communityItem}>
              <span style={{ ...styles.dot, background: COMMUNITY_COLORS[i % 6] }} />
              <span style={{ flex: 1, fontSize: 12, fontWeight: 500, textAlign: 'left' }}>{c.name}</span>
              <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>{c.member_count}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Footer — sync info */}
      <div style={styles.footer}>
        <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
          Last sync: {formatSyncTime(status?.last_sync)}
        </span>
        <button onClick={handleSync} disabled={syncing} style={styles.refreshBtn}>
          <span style={{ display: 'inline-block', animation: syncing ? 'spin 1s linear infinite' : 'none', fontSize: 14 }}>↻</span>
        </button>
      </div>
    </div>
  )
}

const styles = {
  sidebar: {
    width: 220, flexShrink: 0, display: 'flex', flexDirection: 'column',
    borderRight: '0.5px solid var(--color-border-tertiary)',
    background: 'var(--color-background-secondary)',
    height: '100%', overflow: 'hidden',
  },
  header: {
    padding: '16px 14px 12px', borderBottom: '0.5px solid var(--color-border-tertiary)',
  },
  nav: {
    padding: '8px 8px 0', display: 'flex', flexDirection: 'column', gap: 1,
    borderBottom: '0.5px solid var(--color-border-tertiary)', paddingBottom: 8,
  },
  navItem: {
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '7px 14px', borderRadius: 'var(--radius-md)',
    border: 'none', cursor: 'pointer', fontSize: 13,
    transition: 'background 120ms ease, color 120ms ease',
    textAlign: 'left', width: '100%',
  },
  communitySection: {
    flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column',
    padding: '8px 0 0',
  },
  sectionLabel: {
    fontSize: 10, fontWeight: 500, color: 'var(--color-text-tertiary)',
    textTransform: 'uppercase', letterSpacing: '0.5px',
    padding: '4px 14px 6px',
  },
  communityList: {
    flex: 1, overflowY: 'auto', padding: '0 8px',
    display: 'flex', flexDirection: 'column', gap: 1,
  },
  communityItem: {
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '6px 8px', borderRadius: 'var(--radius-md)',
    border: 'none', cursor: 'pointer', background: 'transparent',
    transition: 'background 120ms ease', width: '100%',
    color: 'var(--color-text-primary)',
  },
  dot: { width: 8, height: 8, borderRadius: '50%', flexShrink: 0 },
  footer: {
    padding: '10px 14px', borderTop: '0.5px solid var(--color-border-tertiary)',
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  },
  refreshBtn: {
    background: 'none', border: 'none', cursor: 'pointer',
    color: 'var(--color-text-tertiary)', padding: 4, borderRadius: 'var(--radius-md)',
  },
}
