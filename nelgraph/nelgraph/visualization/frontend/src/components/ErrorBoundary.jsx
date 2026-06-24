import React from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo })
    
    // Log to console
    console.error("ErrorBoundary caught an error:", error, errorInfo)

    // POST to backend API /log
    axios.post(`${API}/log`, {
      level: 'error',
      message: error.message || String(error),
      stack: error.stack || '',
      componentStack: errorInfo?.componentStack || '',
      source: 'frontend_error_boundary',
      selectedNode: this.props.selectedNode ? {
        name: this.props.selectedNode.name,
        type: this.props.selectedNode.type
      } : null
    }).catch(err => {
      console.error("Failed to send frontend error log to backend:", err)
    })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: 20,
          backgroundColor: '#FFF2F2',
          border: '1px solid #FFA3A3',
          borderRadius: 8,
          margin: 16,
          fontFamily: 'monospace',
          color: '#A80000',
          fontSize: 13,
          boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
          maxWidth: '100%',
          overflowX: 'auto'
        }}>
          <h4 style={{ margin: '0 0 10px 0', fontSize: 15 }}>⚠️ Error Rendering Node Details</h4>
          <p style={{ margin: '0 0 12px 0', color: '#555', fontSize: 12 }}>
            This error has been automatically captured and written to `viz.log`.
          </p>
          <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
            <button 
              onClick={() => {
                this.setState({ hasError: false, error: null, errorInfo: null })
                if (this.props.onReset) this.props.onReset()
              }}
              style={{
                padding: '4px 10px',
                backgroundColor: '#A80000',
                color: '#FFF',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: 12
              }}
            >
              Reset Panel
            </button>
          </div>
          <pre style={{ 
            marginTop: 10, 
            fontSize: 11, 
            whiteSpace: 'pre-wrap', 
            backgroundColor: '#FFF8F8', 
            padding: 10, 
            borderRadius: 4,
            border: '1px solid #FFD3D3'
          }}>
            {this.state.error?.stack || String(this.state.error)}
          </pre>
        </div>
      )
    }

    return this.props.children
  }
}
