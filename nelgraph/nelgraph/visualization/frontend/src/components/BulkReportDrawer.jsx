import { useState, useEffect } from 'react'
import axios from 'axios'
import MarkdownRenderer from './MarkdownRenderer'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'

export default function BulkReportDrawer({ taskId, onClose }) {
  const [reportMd, setReportMd] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!taskId) return

    const fetchReport = async () => {
      setLoading(true)
      setError(null)
      try {
        const { data } = await axios.get(`${API}/task/${taskId}/report`)
        if (data.error) {
          setError(data.error)
        } else {
          setReportMd(data.markdown || '')
        }
      } catch (err) {
        setError('Failed to load markdown report. Ensure the backend server is running.')
      } finally {
        setLoading(false)
      }
    }

    fetchReport()
  }, [taskId])

  // Close on Escape key
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div style={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={styles.drawer}>
        {/* Header */}
        <div style={styles.header}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              📋 AI Quality & Coverage Report
            </div>
            <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginTop: 2 }}>
              Task ID: <span style={{ color: 'var(--color-accent)', fontFamily: 'monospace' }}>{taskId}</span>
            </div>
          </div>
          <button onClick={onClose} style={styles.closeBtn}>×</button>
        </div>

        {/* Content Section */}
        <div style={styles.content}>
          {loading ? (
            <div style={styles.loadingBox}>
              <div style={styles.spinner} />
              <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', fontWeight: 500 }}>
                Summarizing test results with DeepSeek-V4...
              </div>
            </div>
          ) : error ? (
            <div style={styles.errorBox}>
              <div style={{ fontSize: 14, marginBottom: 8 }}>⚠️ Error</div>
              <div style={{ fontSize: 12 }}>{error}</div>
            </div>
          ) : (
            <div style={styles.reportArea}>
              <MarkdownRenderer content={reportMd} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

const styles = {
  overlay: {
    position: 'fixed',
    inset: 0,
    zIndex: 300,
    background: 'rgba(0,0,0,0.4)',
    display: 'flex',
    justifyContent: 'flex-end',
    backdropFilter: 'blur(2px)',
  },
  drawer: {
    width: 650,
    maxWidth: '95vw',
    height: '100vh',
    background: 'var(--color-background-primary)',
    borderLeft: '0.5px solid var(--color-border-tertiary)',
    display: 'flex',
    flexDirection: 'column',
    boxShadow: '-8px 0 24px rgba(0,0,0,0.15)',
    overflow: 'hidden',
  },
  header: {
    padding: '16px',
    display: 'flex',
    alignItems: 'center',
    borderBottom: '0.5px solid var(--color-border-tertiary)',
    background: 'var(--color-background-secondary)',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: 24,
    color: 'var(--color-text-tertiary)',
    lineHeight: 1,
    padding: '0 4px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'color 120ms ease',
    ':hover': {
      color: 'var(--color-text)',
    }
  },
  content: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    position: 'relative',
  },
  loadingBox: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
  },
  spinner: {
    width: 28,
    height: 28,
    border: '3px solid var(--color-border-secondary)',
    borderTopColor: 'var(--color-accent)',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  errorBox: {
    margin: 16,
    padding: 16,
    borderRadius: 'var(--radius-md)',
    background: 'rgba(231, 76, 60, 0.1)',
    color: 'var(--color-danger)',
    borderLeft: '4px solid var(--color-danger)',
  },
  reportArea: {
    flex: 1,
    overflowY: 'auto',
    padding: '20px 24px',
  }
}
