export default function DetailPanel({ detail, loading, selectedNode, onClose, onNodeNavigate, onMarkTested, onCommunityClick }) {
  if (!selectedNode) return null

  const node = detail?.node || {}
  const labels = detail?.labels || []
  const nodeType = labels[0] || selectedNode.type || '?'
  const isCommunityDetail = nodeType === 'Community'

  // Parse inputs JSON
  let parsedInputs = []
  if (node.inputs) {
    try {
      const inp = typeof node.inputs === 'string' ? JSON.parse(node.inputs) : node.inputs
      if (Array.isArray(inp)) {
        parsedInputs = inp
      } else if (inp && typeof inp === 'object') {
        parsedInputs = Object.entries(inp).map(([k, v]) => ({ name: k, type: v }))
      }
    } catch {}
  }

  // Parse edge_cases and test_recommendations
  const edgeCases = parseList(node.edge_cases)
  const testRecs = parseList(node.test_recommendations)

  const badgeStyle = getBadgeStyle(nodeType)

  return (
    <div style={styles.panel}>
      {/* Header */}
      <div style={styles.header}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <span style={{ ...styles.badge, background: badgeStyle.bg, color: badgeStyle.color }}>{nodeType}</span>
            {node.tested && (
              <span style={{ ...styles.badge, background: 'var(--badge-tested-bg)', color: 'var(--badge-tested-color)' }}>✓ tested</span>
            )}
          </div>
          <div style={{ fontSize: 16, fontWeight: 500 }}>{selectedNode.name || node.name}</div>
          {(node.file || node.class_name) && (
            <div style={{ fontSize: 12, color: 'var(--color-text-tertiary)', marginTop: 2 }}>
              {node.file}{node.class_name ? ` · ${node.class_name}` : ''}
            </div>
          )}
        </div>
        <button onClick={onClose} style={styles.closeBtn}>×</button>
      </div>

      {loading && <div style={{ padding: 16, color: 'var(--color-text-tertiary)', fontSize: 12 }}>Loading...</div>}

      <div style={styles.content}>
        {isCommunityDetail ? (
          <CommunityDetailContent detail={detail} onNodeNavigate={onNodeNavigate} />
        ) : (
          <>
            {/* How it works */}
            {node.how_it_works && (
              <Section title="How it works">
                <p style={styles.bodyText}>{node.how_it_works}</p>
              </Section>
            )}

            {/* Signature */}
            {(parsedInputs.length > 0 || node.output || node.raises) && (
              <Section title="Signature">
                {parsedInputs.map((p, i) => {
                  if (!p) return null
                  const name = typeof p === 'object' ? (p.name || '') : p
                  const type = typeof p === 'object' ? (p.type || p.annotation || '') : ''
                  return (
                    <div key={i} style={styles.propRow}>
                      <span style={styles.propKey}>{name}</span>
                      <span style={styles.propVal}>{type}</span>
                    </div>
                  )
                })}
                {node.output && (
                  <div style={styles.propRow}>
                    <span style={styles.propKey}>returns</span>
                    <span style={styles.propVal}>{node.output}</span>
                  </div>
                )}
                {node.raises && (
                  <div style={styles.propRow}>
                    <span style={styles.propKey}>raises</span>
                    <span style={{ ...styles.propVal, color: 'var(--color-danger)' }}>{node.raises}</span>
                  </div>
                )}
              </Section>
            )}

            {/* Edge cases */}
            {edgeCases.length > 0 && (
              <Section title="Edge cases">
                <ul style={styles.bulletList}>
                  {edgeCases.map((e, i) => <li key={i}>{renderListItem(e)}</li>)}
                </ul>
              </Section>
            )}

            {/* Test recommendations */}
            {testRecs.length > 0 && (
              <Section title="Test recommendations">
                <ul style={styles.bulletList}>
                  {testRecs.map((t, i) => <li key={i}>{renderListItem(t)}</li>)}
                </ul>
                {!node.tested && onMarkTested && (
                  <button onClick={() => onMarkTested(node.name || selectedNode.name)} style={styles.markTestedBtn}>
                    Mark as tested
                  </button>
                )}
              </Section>
            )}

            {/* Properties */}
            <Section title="Properties">
              <div style={styles.propRow}><span style={styles.propKey}>Complexity</span><span style={styles.propVal}>{node.complexity ?? '–'}</span></div>
              <div style={styles.propRow}><span style={styles.propKey}>Async</span><span style={styles.propVal}>{node.is_async ? 'Yes' : 'No'}</span></div>
              <div style={styles.propRow}><span style={styles.propKey}>Visibility</span><span style={styles.propVal}>{node.visibility || '–'}</span></div>
              {(node.start_line || node.end_line) && (
                <div style={styles.propRow}><span style={styles.propKey}>Lines</span><span style={styles.propVal}>{node.start_line}–{node.end_line}</span></div>
              )}
              {detail?.community_name && (
                <div style={styles.propRow}>
                  <span style={styles.propKey}>Community</span>
                  <button onClick={() => onCommunityClick && onCommunityClick({ id: node.community_id, name: detail.community_name })}
                    style={{ ...styles.propVal, color: 'var(--color-accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                    {detail.community_name}
                  </button>
                </div>
              )}
            </Section>

            {/* Called by */}
            {detail?.incoming?.filter(r => r && r.source).length > 0 && (
              <Section title="Called by">
                <div style={styles.chipContainer}>
                  {detail.incoming.filter(r => r && r.source).map((r, i) => (
                    <button key={i} onClick={() => onNodeNavigate(r.source)} style={styles.chip}>
                      <span style={{ fontSize: 10 }}>ƒ</span> {r.source}
                    </button>
                  ))}
                </div>
              </Section>
            )}

            {/* Calls */}
            {detail?.outgoing?.filter(r => r && r.target).length > 0 && (
              <Section title="Calls">
                <div style={styles.chipContainer}>
                  {detail.outgoing.filter(r => r && r.target).map((r, i) => (
                    <button key={i} onClick={() => onNodeNavigate(r.target)} style={styles.chip}>
                      <span style={{ fontSize: 10 }}>ƒ</span> {r.target}
                    </button>
                  ))}
                </div>
              </Section>
            )}

            {/* Source */}
            {node.raw_code && typeof node.raw_code === 'string' && (
              <Section title="Source">
                <pre style={styles.codeBlock}>
                  {node.raw_code.length > 800 ? node.raw_code.slice(0, 800) + '\n... (truncated)' : node.raw_code}
                </pre>
              </Section>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function CommunityDetailContent({ detail, onNodeNavigate }) {
  const node = detail?.node || {}
  const members = detail?.outgoing?.filter(r => r && r.target) || []
  return (
    <>
      {node.summary && <Section title="Summary"><p style={styles.bodyText}>{node.summary}</p></Section>}
      {members.length > 0 && (
        <Section title="Members">
          <div style={styles.chipContainer}>
            {members.map((m, i) => (
              <button key={i} onClick={() => onNodeNavigate(m.target)} style={styles.chip}>
                {m.target}
              </button>
            ))}
          </div>
        </Section>
      )}
    </>
  )
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={styles.sectionTitle}>{title}</div>
      {children}
    </div>
  )
}

function parseList(val) {
  if (!val) return []
  if (Array.isArray(val)) return val
  if (typeof val === 'string') {
    try { const p = JSON.parse(val); if (Array.isArray(p)) return p } catch {}
    return val.split('\n').filter(Boolean)
  }
  return [String(val)]
}

function renderListItem(item) {
  if (!item) return ''
  if (typeof item === 'object') {
    const parts = []
    const typeOrPath = item.type || item.path
    if (typeOrPath) parts.push(`[${typeOrPath}] `)
    if (item.name) parts.push(`${item.name}: `)
    parts.push(item.description || item.summary || JSON.stringify(item))
    return parts.join('')
  }
  return String(item)
}

function getBadgeStyle(type) {
  const map = {
    Function: { bg: 'var(--badge-function-bg)', color: 'var(--badge-function-color)' },
    Class: { bg: 'var(--badge-class-bg)', color: 'var(--badge-class-color)' },
    Community: { bg: 'var(--badge-community-bg)', color: 'var(--badge-community-color)' },
    File: { bg: 'var(--badge-file-bg)', color: 'var(--badge-file-color)' },
    Commit: { bg: 'var(--badge-commit-bg)', color: 'var(--badge-commit-color)' },
  }
  return map[type] || { bg: 'var(--badge-file-bg)', color: 'var(--badge-file-color)' }
}

const styles = {
  panel: {
    width: 300, flexShrink: 0, display: 'flex', flexDirection: 'column',
    borderLeft: '0.5px solid var(--color-border-tertiary)',
    background: 'var(--color-background-primary)', height: '100%', overflow: 'hidden',
  },
  header: {
    padding: '12px 16px', borderBottom: '0.5px solid var(--color-border-tertiary)',
    display: 'flex', alignItems: 'flex-start', gap: 8,
  },
  closeBtn: {
    background: 'none', border: 'none', cursor: 'pointer', fontSize: 20,
    color: 'var(--color-text-tertiary)', lineHeight: 1, padding: 0,
  },
  badge: {
    fontSize: 10, fontWeight: 500, padding: '2px 6px', borderRadius: 'var(--radius-sm)',
    display: 'inline-block',
  },
  content: { flex: 1, overflowY: 'auto', padding: '12px 16px' },
  sectionTitle: {
    fontSize: 10, fontWeight: 500, color: 'var(--color-text-tertiary)',
    textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 6,
  },
  bodyText: { fontSize: 12, lineHeight: 1.6, color: 'var(--color-text-secondary)' },
  propRow: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '3px 0', fontSize: 12,
  },
  propKey: { color: 'var(--color-text-tertiary)' },
  propVal: { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-text-primary)' },
  bulletList: {
    fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.6,
    paddingLeft: 16, margin: 0,
  },
  chipContainer: { display: 'flex', flexWrap: 'wrap', gap: 4 },
  chip: {
    fontSize: 11, padding: '3px 8px', borderRadius: 'var(--radius-md)',
    border: '1px solid var(--color-border-primary)', background: 'var(--color-background-secondary)',
    cursor: 'pointer', color: 'var(--color-text-primary)',
    display: 'flex', alignItems: 'center', gap: 4,
    transition: 'background 120ms ease',
  },
  codeBlock: {
    fontSize: 11, fontFamily: 'var(--font-mono)', background: 'var(--color-background-tertiary)',
    borderRadius: 'var(--radius-md)', padding: 10, overflowX: 'auto',
    maxHeight: 120, overflowY: 'auto', whiteSpace: 'pre-wrap',
    color: 'var(--color-text-primary)', lineHeight: 1.5, margin: 0,
  },
  markTestedBtn: {
    marginTop: 8, fontSize: 12, padding: '6px 12px', borderRadius: 'var(--radius-md)',
    border: 'none', background: 'var(--badge-tested-bg)', color: 'var(--badge-tested-color)',
    cursor: 'pointer', fontWeight: 500,
  },
}
