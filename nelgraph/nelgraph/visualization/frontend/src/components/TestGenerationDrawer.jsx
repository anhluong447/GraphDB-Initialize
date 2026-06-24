import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'

export default function TestGenerationDrawer({ target, file, className, onClose }) {
  const [mode, setMode] = useState('unit')
  const [taskId, setTaskId] = useState(null)
  const [status, setStatus] = useState('idle') // idle | running | done | error
  const [report, setReport] = useState(null)
  const [runResult, setRunResult] = useState(null)
  const pollRef = useRef(null)

  // Start test generation
  const handleGenerate = useCallback(async () => {
    setStatus('running')
    setReport(null)
    setRunResult(null)
    try {
      const { data } = await axios.post(`${API}/generate_tests`, {
        target, mode, file: file || null, class_name: className || null,
      })
      setTaskId(data.task_id)
    } catch (e) {
      setStatus('error')
      setReport({ error: e.message, log: [] })
    }
  }, [target, mode, file, className])

  // Poll for task completion
  useEffect(() => {
    if (!taskId || status !== 'running') return

    pollRef.current = setInterval(async () => {
      try {
        const { data } = await axios.get(`${API}/task/${taskId}/status`)
        if (data.status === 'done' || data.status === 'error') {
          clearInterval(pollRef.current)
          setStatus(data.status === 'done' ? 'done' : 'error')
          setReport(data.result)
        }
      } catch {
        clearInterval(pollRef.current)
        setStatus('error')
      }
    }, 2000)

    return () => clearInterval(pollRef.current)
  }, [taskId, status])

  // Run a generated test file
  const handleRunTest = useCallback(async (filePath) => {
    setRunResult({ status: 'running', file: filePath })
    try {
      const { data } = await axios.post(`${API}/test/run`, { file_path: filePath })
      setRunResult({ ...data, file: filePath })
    } catch (e) {
      setRunResult({ status: 'error', output: e.message, file: filePath })
    }
  }, [])

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div style={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={styles.drawer}>
        {/* Header */}
        <div style={styles.header}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 500 }}>🧪 AI Test Generator</div>
            <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginTop: 2 }}>
              Target: <span style={{ color: 'var(--color-accent)' }}>{target}</span>
            </div>
          </div>
          <button onClick={onClose} style={styles.closeBtn}>×</button>
        </div>

        {/* Mode selector */}
        <div style={styles.modeBar}>
          {['unit', 'integration', 'system'].map(m => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                ...styles.modeBtn,
                ...(mode === m ? styles.modeBtnActive : {}),
              }}
            >
              {m === 'unit' ? '🧪' : m === 'integration' ? '⛓️' : '🌐'} {m}
            </button>
          ))}
        </div>

        {/* Generate button */}
        {status === 'idle' && (
          <div style={{ padding: '12px 16px' }}>
            <button onClick={handleGenerate} style={styles.generateBtn}>
              Generate {mode} tests for "{target}"
            </button>
          </div>
        )}

        {/* Running state */}
        {status === 'running' && (
          <div style={styles.runningBox}>
            <div style={styles.spinner} />
            <div>
              <div style={{ fontWeight: 500, fontSize: 12 }}>Agent is working...</div>
              <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginTop: 2 }}>
                Commander is analyzing dependencies and planning strategy
              </div>
            </div>
          </div>
        )}

        {/* Report */}
        {report && status !== 'running' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '0 16px 16px' }}>
            {/* Summary cards */}
            {report.summary && (
              <div style={styles.summaryRow}>
                <div style={styles.summaryCard}>
                  <div style={styles.summaryLabel}>Total</div>
                  <div style={styles.summaryValue}>{report.summary.total_files}</div>
                </div>
                <div style={styles.summaryCard}>
                  <div style={styles.summaryLabel}>Passed</div>
                  <div style={{ ...styles.summaryValue, color: 'var(--color-success)' }}>{report.summary.passed}</div>
                </div>
                <div style={styles.summaryCard}>
                  <div style={styles.summaryLabel}>Failed</div>
                  <div style={{ ...styles.summaryValue, color: report.summary.failed > 0 ? 'var(--color-danger)' : 'var(--color-text-tertiary)' }}>{report.summary.failed}</div>
                </div>
                <div style={styles.summaryCard}>
                  <div style={styles.summaryLabel}>Self-healed</div>
                  <div style={{ ...styles.summaryValue, color: 'var(--color-warning)' }}>{report.summary.self_healed}</div>
                </div>
              </div>
            )}

            {/* Strategy */}
            {report.strategy && (
              <div style={{ marginBottom: 12 }}>
                <div style={styles.sectionTitle}>Strategy</div>
                <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
                  {report.strategy}
                </div>
              </div>
            )}

            {/* Generated files */}
            {report.generated_files?.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={styles.sectionTitle}>Generated Files</div>
                {report.generated_files.map((f, i) => (
                  <div key={i} style={styles.fileRow}>
                    <span style={{ fontSize: 12, flex: 1, fontFamily: 'var(--font-mono)', fontSize: 11 }}>{f}</span>
                    <button onClick={() => handleRunTest(f)} style={styles.runBtn}>
                      ▶ Run
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Run result */}
            {runResult && (
              <div style={{ marginBottom: 12 }}>
                <div style={styles.sectionTitle}>
                  Test Output — {runResult.file}
                  <span style={{
                    marginLeft: 8, fontSize: 10, padding: '1px 6px', borderRadius: 2,
                    background: runResult.status === 'passed' ? 'var(--color-success-muted)' : runResult.status === 'running' ? 'var(--color-warning-muted)' : 'var(--color-danger-muted)',
                    color: runResult.status === 'passed' ? 'var(--color-success)' : runResult.status === 'running' ? 'var(--color-warning)' : 'var(--color-danger)',
                  }}>
                    {runResult.status === 'running' ? 'Running...' : runResult.status}
                  </span>
                </div>
                {runResult.output && (
                  <pre style={styles.outputBlock}>{runResult.output}</pre>
                )}
              </div>
            )}

            {/* Bugs found */}
            {report.bugs_found?.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ ...styles.sectionTitle, color: 'var(--color-danger)' }}>🚨 Real Bugs Detected</div>
                {report.bugs_found.map((b, i) => (
                  <div key={i} style={styles.bugCard}>
                    <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 4 }}>{b.file}</div>
                    <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>{b.explanation}</div>
                    {b.fix_suggestion && (
                      <pre style={{ ...styles.outputBlock, marginTop: 6, fontSize: 10 }}>{b.fix_suggestion}</pre>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Test results detail */}
            {report.test_results?.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={styles.sectionTitle}>Detailed Results</div>
                {report.test_results.map((r, i) => (
                  <details key={i} style={styles.resultDetail}>
                    <summary style={styles.resultSummary}>
                      <span style={{
                        display: 'inline-block', width: 8, height: 8, borderRadius: '50%', marginRight: 6,
                        background: r.status === 'passed' ? 'var(--color-success)' : 'var(--color-danger)',
                      }} />
                      {r.file} — {r.status}
                    </summary>
                    {r.output && <pre style={{ ...styles.outputBlock, marginTop: 4 }}>{r.output}</pre>}
                  </details>
                ))}
              </div>
            )}

            {/* Agent log */}
            {report.log?.length > 0 && (
              <details style={{ marginBottom: 12 }}>
                <summary style={{ ...styles.sectionTitle, cursor: 'pointer' }}>Agent Log ({report.log.length} entries)</summary>
                <pre style={{ ...styles.outputBlock, maxHeight: 200, marginTop: 4 }}>
                  {report.log.join('\n')}
                </pre>
              </details>
            )}

            {/* Re-generate */}
            <button onClick={() => { setStatus('idle'); setReport(null); setTaskId(null); setRunResult(null) }} style={styles.retryBtn}>
              ↻ Generate Again
            </button>
          </div>
        )}

        {/* Error fallback */}
        {status === 'error' && !report && (
          <div style={{ padding: 16, color: 'var(--color-danger)', fontSize: 12 }}>
            An error occurred. Please try again.
          </div>
        )}
      </div>
    </div>
  )
}

const styles = {
  overlay: {
    position: 'fixed', inset: 0, zIndex: 200,
    background: 'rgba(0,0,0,0.3)',
    display: 'flex', justifyContent: 'flex-end',
    animation: 'fadeIn 150ms ease',
  },
  drawer: {
    width: 520, maxWidth: '90vw', height: '100vh',
    background: 'var(--color-background-primary)',
    borderLeft: '0.5px solid var(--color-border-tertiary)',
    display: 'flex', flexDirection: 'column',
    animation: 'slideInRight 200ms cubic-bezier(0.16, 1, 0.3, 1)',
    overflow: 'hidden',
  },
  header: {
    padding: '12px 16px', display: 'flex', alignItems: 'flex-start', gap: 8,
    borderBottom: '0.5px solid var(--color-border-tertiary)', flexShrink: 0,
  },
  closeBtn: {
    background: 'none', border: 'none', cursor: 'pointer', fontSize: 20,
    color: 'var(--color-text-tertiary)', lineHeight: 1, padding: 0,
  },
  modeBar: {
    display: 'flex', gap: 6, padding: '10px 16px',
    borderBottom: '0.5px solid var(--color-border-tertiary)', flexShrink: 0,
  },
  modeBtn: {
    fontSize: 11, padding: '5px 10px', borderRadius: 'var(--radius-md)',
    border: '1px solid var(--color-border-primary)', background: 'transparent',
    color: 'var(--color-text-secondary)', cursor: 'pointer',
    transition: 'all 120ms ease', textTransform: 'capitalize',
  },
  modeBtnActive: {
    background: 'var(--color-accent-muted)', borderColor: 'var(--color-accent)',
    color: 'var(--color-accent)', fontWeight: 500,
  },
  generateBtn: {
    width: '100%', padding: '10px 16px', borderRadius: 'var(--radius-md)',
    border: 'none', background: 'var(--color-accent)', color: '#fff',
    fontSize: 13, fontWeight: 500, cursor: 'pointer',
    transition: 'background 120ms ease',
  },
  runningBox: {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '20px 16px', animation: 'fadeIn 200ms ease',
  },
  spinner: {
    width: 20, height: 20, border: '2px solid var(--color-border-secondary)',
    borderTopColor: 'var(--color-accent)', borderRadius: '50%',
    animation: 'spin 0.8s linear infinite', flexShrink: 0,
  },
  summaryRow: {
    display: 'flex', gap: 8, marginBottom: 12, marginTop: 8,
  },
  summaryCard: {
    flex: 1, background: 'var(--color-background-secondary)', borderRadius: 'var(--radius-lg)',
    padding: '10px 12px', textAlign: 'center',
  },
  summaryLabel: { fontSize: 10, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.3px' },
  summaryValue: { fontSize: 18, fontWeight: 500, marginTop: 2 },
  sectionTitle: {
    fontSize: 10, fontWeight: 500, color: 'var(--color-text-tertiary)',
    textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 6,
  },
  fileRow: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0',
    borderBottom: '0.5px solid var(--color-border-tertiary)',
  },
  runBtn: {
    fontSize: 10, padding: '3px 8px', borderRadius: 'var(--radius-md)',
    border: '1px solid var(--color-accent)', background: 'var(--color-accent-muted)',
    color: 'var(--color-accent)', cursor: 'pointer', fontWeight: 500, flexShrink: 0,
  },
  outputBlock: {
    fontSize: 10, fontFamily: 'var(--font-mono)', background: 'var(--color-background-tertiary)',
    borderRadius: 'var(--radius-md)', padding: 10, overflowX: 'auto',
    maxHeight: 300, overflowY: 'auto', whiteSpace: 'pre-wrap',
    color: 'var(--color-text-primary)', lineHeight: 1.4, margin: 0,
  },
  bugCard: {
    background: 'var(--color-danger-muted)', borderRadius: 'var(--radius-md)',
    padding: '10px 12px', marginBottom: 6,
  },
  resultDetail: {
    marginBottom: 4,
  },
  resultSummary: {
    fontSize: 12, cursor: 'pointer', padding: '4px 0',
    display: 'flex', alignItems: 'center',
  },
  retryBtn: {
    width: '100%', padding: '8px 16px', borderRadius: 'var(--radius-md)',
    border: '1px solid var(--color-border-primary)', background: 'var(--color-background-secondary)',
    fontSize: 12, cursor: 'pointer', color: 'var(--color-text-secondary)',
  },
}
