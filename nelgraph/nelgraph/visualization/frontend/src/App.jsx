import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import Sidebar from './components/Sidebar'
import GraphView from './components/GraphView'
import CommunitiesView from './components/CommunitiesView'
import FunctionsView from './components/FunctionsView'
import TestCoverageView from './components/TestCoverageView'
import CommitsView from './components/CommitsView'
import DetailPanel from './components/DetailPanel'
import TestGenerationDrawer from './components/TestGenerationDrawer'
import ErrorBoundary from './components/ErrorBoundary'
import { useStatus } from './hooks/useStatus'
import { useGraph } from './hooks/useGraph'
import { useNodeDetail } from './hooks/useNodeDetail'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'

export default function App() {
  const [activeView, setActiveView] = useState('graph')
  const [selectedNodeName, setSelectedNodeName] = useState(null)
  const [selectedNode, setSelectedNode] = useState(null)
  const [highlightNodes, setHighlightNodes] = useState(new Set())
  const [testGenTarget, setTestGenTarget] = useState(null) // {name, file, class_name}

  const { status, refresh: refreshStatus } = useStatus()
  const { graphData, loading: graphLoading, stats, loadFullGraph, loadCommunitySubgraph } = useGraph()
  const { detail, loading: detailLoading } = useNodeDetail(selectedNodeName)

  // Load graph on mount
  useEffect(() => { loadFullGraph() }, [loadFullGraph])

  // Close panel on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') { setSelectedNodeName(null); setSelectedNode(null) } }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  const handleNodeClick = useCallback((node) => {
    setSelectedNode(node)
    setSelectedNodeName(node.name)
  }, [])

  const handleBackgroundClick = useCallback(() => {
    setSelectedNode(null)
    setSelectedNodeName(null)
  }, [])

  const handleNodeNavigate = useCallback((name) => {
    setSelectedNode({ name, type: '?' })
    setSelectedNodeName(name)
  }, [])

  const handleCommunityClick = useCallback((community) => {
    loadCommunitySubgraph(community.id)
    setActiveView('graph')
    // Load community detail in panel
    setSelectedNode({ name: community.name, type: 'Community' })
    setSelectedNodeName(community.name)
  }, [loadCommunitySubgraph])

  const handleViewInGraph = useCallback((community) => {
    loadCommunitySubgraph(community.id)
    setActiveView('graph')
  }, [loadCommunitySubgraph])

  const handleSync = useCallback(async () => {
    await axios.get(`${API}/sync`)
    setTimeout(refreshStatus, 3000)
  }, [refreshStatus])

  const handleMarkTested = useCallback(async (name) => {
    try {
      await axios.post(`${API}/node/${encodeURIComponent(name)}/mark_tested`)
      refreshStatus()
    } catch {}
  }, [refreshStatus])

  const handleGenerateTest = useCallback((nodeInfo) => {
    setTestGenTarget(nodeInfo)
  }, [])

  const renderView = () => {
    switch (activeView) {
      case 'graph':
        return (
          <GraphView
            graphData={graphData} graphLoading={graphLoading} stats={stats} status={status}
            onNodeClick={handleNodeClick} onBackgroundClick={handleBackgroundClick}
            highlightNodes={highlightNodes} setHighlightNodes={setHighlightNodes}
          />
        )
      case 'communities':
        return <CommunitiesView onViewInGraph={handleViewInGraph} />
      case 'functions':
        return <FunctionsView onNodeClick={handleNodeClick} />
      case 'coverage':
        return <TestCoverageView status={status} onMarkTested={handleMarkTested} onGenerateTest={handleGenerateTest} />
      case 'commits':
        return <CommitsView />
      default:
        return null
    }
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar
        activeView={activeView}
        onViewChange={setActiveView}
        onCommunityClick={handleCommunityClick}
        status={status}
        onSync={handleSync}
      />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {renderView()}
      </div>
      {selectedNode && (
        <ErrorBoundary selectedNode={selectedNode} onReset={handleBackgroundClick}>
          <DetailPanel
            detail={detail}
            loading={detailLoading}
            selectedNode={selectedNode}
            onClose={handleBackgroundClick}
            onNodeNavigate={handleNodeNavigate}
            onMarkTested={handleMarkTested}
            onCommunityClick={handleCommunityClick}
            onGenerateTest={handleGenerateTest}
          />
        </ErrorBoundary>
      )}
      {testGenTarget && (
        <TestGenerationDrawer
          target={testGenTarget.name}
          file={testGenTarget.file}
          className={testGenTarget.class_name}
          onClose={() => setTestGenTarget(null)}
        />
      )}
    </div>
  )
}
