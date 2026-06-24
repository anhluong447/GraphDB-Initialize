import { useState, useEffect } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'

export function useNodeDetail(nodeName) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!nodeName) { setDetail(null); return }
    let cancelled = false
    setLoading(true)
    axios.get(`${API}/node/${encodeURIComponent(nodeName)}`)
      .then(({ data }) => { if (!cancelled) setDetail(data) })
      .catch(() => { if (!cancelled) setDetail(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [nodeName])

  return { detail, loading }
}
