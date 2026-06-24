import { useState, useEffect, useRef, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import axios from 'axios'
import { forceCollide } from 'd3-force'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'

const NODE_COLORS = {
  Function: '#378ADD', Class: '#7F77DD', File: '#888780',
  Community: '#1D9E75', Commit: '#B4B2A9',
}
const NODE_SIZES = { Community: 14, Class: 10, Function: 7, File: 5, Commit: 4 }
const FILTER_TYPES = ['All', 'Function', 'Class', 'File', 'Community']

export default function GraphView({ graphData, graphLoading, stats, onNodeClick, onBackgroundClick, highlightNodes, setHighlightNodes, status }) {
  const [searchQuery, setSearchQuery] = useState('')
  const [activeFilter, setActiveFilter] = useState('All')
  const [searchResults, setSearchResults] = useState([])
  const graphRef = useRef()
  const debounceRef = useRef()

  // Search debounce
  useEffect(() => {
    clearTimeout(debounceRef.current)
    if (!searchQuery.trim()) {
      setHighlightNodes(new Set())
      setSearchResults([])
      return
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const { data } = await axios.get(`${API}/graph/search?q=${encodeURIComponent(searchQuery)}`)
        setSearchResults(data)
        setHighlightNodes(new Set(data.map(n => String(n.id))))
      } catch {}
    }, 300)
    return () => clearTimeout(debounceRef.current)
  }, [searchQuery, setHighlightNodes])

  // Tune D3 force simulation parameters to optimize layout and spacing
  useEffect(() => {
    if (graphRef.current) {
      const fg = graphRef.current
      
      // 1. Stronger repulsion up close, but ignore distant nodes to avoid ring formation
      fg.d3Force('charge')
        .strength(-250)
        .distanceMax(250)
      
      // 2. Spread out linked nodes
      fg.d3Force('link')
        .distance(80)
      
      // 3. Collision force to prevent node overlaps
      fg.d3Force('collide', forceCollide(node => {
        const size = NODE_SIZES[node.type] || 5
        return size + 14
      }))
      
      // Reheat simulation to apply the modified forces
      fg.d3ReheatSimulation()
    }
  }, [graphLoading])

  const filteredNodes = activeFilter === 'All'
    ? graphData.nodes
    : graphData.nodes.filter(n => n.type === activeFilter)

  const nodeIds = new Set(filteredNodes.map(n => String(n.id)))

  const filteredLinks = graphData.links.filter(l => {
    const sourceId = String(l.source?.id || l.source)
    const targetId = String(l.target?.id || l.target)
    return nodeIds.has(sourceId) && nodeIds.has(targetId)
  })

  const filteredData = {
    nodes: filteredNodes,
    links: filteredLinks,
  }

  const nodeColor = useCallback((node) => {
    if (highlightNodes.size > 0) {
      return highlightNodes.has(String(node.id)) ? (NODE_COLORS[node.type] || '#B4B2A9') : '#e5e4e0'
    }
    return NODE_COLORS[node.type] || '#B4B2A9'
  }, [highlightNodes])

  const coverage = status ? (status.total_functions > 0 ? Math.round(status.tested_count / status.total_functions * 100) : 0) : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      {/* Toolbar */}
      <div style={styles.toolbar}>
        <span style={{ color: 'var(--color-text-tertiary)', fontSize: 14, flexShrink: 0 }}>⌕</span>
        <input
          style={styles.searchInput}
          placeholder="Search functions, classes, files..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
        />
        {searchResults.length > 0 && (
          <button onClick={() => { setSearchQuery(''); setHighlightNodes(new Set()); setSearchResults([]) }}
            style={styles.clearBtn}>Clear</button>
        )}
        <div style={{ display: 'flex', gap: 4, marginLeft: 8 }}>
          {FILTER_TYPES.map(type => (
            <button key={type} onClick={() => setActiveFilter(type)}
              style={{
                ...styles.filterBtn,
                background: activeFilter === type ? 'var(--color-background-tertiary)' : 'transparent',
                borderColor: activeFilter === type ? 'var(--color-border-secondary)' : 'transparent',
                fontWeight: activeFilter === type ? 500 : 400,
              }}>{type}</button>
          ))}
        </div>
      </div>

      {/* Stats bar */}
      <div style={styles.statsBar}>
        <StatCard label="Functions" value={status?.total_functions || 0} />
        <StatCard label="Classes" value={status?.total_classes || 0} />
        <StatCard label="Test coverage" value={`${coverage}%`} />
      </div>

      {/* Force graph */}
      <div style={{ flex: 1, position: 'relative', background: 'var(--color-background-tertiary)' }}>
        {graphLoading && (
          <div style={styles.loadingOverlay}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 24, animation: 'spin 1s linear infinite', marginBottom: 8, color: 'var(--color-text-tertiary)' }}>⬡</div>
              <div style={{ color: 'var(--color-text-tertiary)', fontSize: 12 }}>Loading graph...</div>
            </div>
          </div>
        )}
        <ForceGraph2D
          ref={graphRef}
          graphData={filteredData}
          nodeColor={nodeColor}
          nodeVal={node => NODE_SIZES[node.type] || 5}
          nodeLabel={node => `[${node.type}] ${node.name}`}
          linkColor={() => '#d4d3cf'}
          linkWidth={0.5}
          linkDirectionalArrowLength={3}
          linkDirectionalArrowRelPos={1}
          backgroundColor="#f1efe8"
          onNodeClick={onNodeClick}
          onBackgroundClick={onBackgroundClick}
          cooldownTicks={100}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const r = NODE_SIZES[node.type] || 5
            const color = nodeColor(node)

            // Glow
            ctx.beginPath()
            ctx.arc(node.x, node.y, r + 3, 0, 2 * Math.PI)
            ctx.fillStyle = color + '26'
            ctx.fill()

            // Circle
            ctx.beginPath()
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
            ctx.fillStyle = color
            ctx.fill()

            // Label
            if (globalScale > 1.8) {
              const fontSize = Math.max(9 / globalScale, 3)
              ctx.font = `${fontSize}px Inter, sans-serif`
              ctx.fillStyle = '#1d1c1a'
              ctx.textAlign = 'center'
              ctx.fillText(node.name?.slice(0, 24) || '', node.x, node.y + r + fontSize + 2)
            }
          }}
        />
      </div>
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <div style={styles.statCard}>
      <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 500 }}>{value}</div>
    </div>
  )
}

const styles = {
  toolbar: {
    height: 44, display: 'flex', alignItems: 'center', gap: 8,
    padding: '0 12px', borderBottom: '0.5px solid var(--color-border-tertiary)',
    flexShrink: 0,
  },
  searchInput: {
    flex: 1, border: 'none', outline: 'none', fontSize: 13,
    background: 'transparent', color: 'var(--color-text-primary)',
    fontFamily: 'var(--font-sans)',
  },
  clearBtn: {
    fontSize: 11, color: 'var(--color-accent)', background: 'none',
    border: 'none', cursor: 'pointer', flexShrink: 0,
  },
  filterBtn: {
    fontSize: 12, padding: '4px 10px', borderRadius: 'var(--radius-md)',
    border: '1px solid transparent', cursor: 'pointer',
    color: 'var(--color-text-secondary)',
    transition: 'background 120ms ease',
  },
  statsBar: {
    height: 56, display: 'flex', alignItems: 'center', gap: 8,
    padding: '0 12px', borderBottom: '0.5px solid var(--color-border-tertiary)',
    background: 'var(--color-background-primary)', flexShrink: 0,
  },
  statCard: {
    background: 'var(--color-background-secondary)', borderRadius: 'var(--radius-md)',
    padding: '8px 10px',
  },
  loadingOverlay: {
    position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
    justifyContent: 'center', background: 'rgba(241,239,232,0.85)', zIndex: 10,
  },
}
