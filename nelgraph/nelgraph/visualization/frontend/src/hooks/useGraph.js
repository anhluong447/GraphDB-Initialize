import { useState, useCallback } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'

export function useGraph() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState({ nodes: 0, edges: 0 })

  const processGraphResponse = (data) => {
    const nodes = data.nodes.map(n => ({ ...n, id: String(n.id) }))
    const nodeIds = new Set(nodes.map(n => n.id))
    const links = data.edges
      .filter(e => nodeIds.has(String(e.source)) && nodeIds.has(String(e.target)))
      .map(e => ({ source: String(e.source), target: String(e.target), label: e.label }))
    setGraphData({ nodes, links })
    setStats({ nodes: nodes.length, edges: links.length })
  }

  const loadFullGraph = useCallback(async (limit = 300) => {
    setLoading(true)
    try {
      const { data } = await axios.get(`${API}/graph/full?limit=${limit}`)
      processGraphResponse(data)
    } catch (err) {
      console.error('Failed to load graph:', err)
    }
    setLoading(false)
  }, [])

  const loadCommunitySubgraph = useCallback(async (communityId) => {
    setLoading(true)
    try {
      const { data } = await axios.get(`${API}/graph/community/${communityId}`)
      processGraphResponse(data)
    } catch (err) {
      console.error('Failed to load community subgraph:', err)
    }
    setLoading(false)
  }, [])

  return { graphData, loading, stats, loadFullGraph, loadCommunitySubgraph }
}
