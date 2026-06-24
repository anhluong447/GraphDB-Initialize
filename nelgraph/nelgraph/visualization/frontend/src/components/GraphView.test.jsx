import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import GraphView from './GraphView'

// Mock react-force-graph-2d since jsdom does not support Canvas
vi.mock('react-force-graph-2d', () => {
  return {
    default: ({ graphData }) => (
      <div data-testid="force-graph-mock">
        <div data-testid="nodes-count">{graphData.nodes.length}</div>
        <div data-testid="links-count">{graphData.links.length}</div>
        {graphData.nodes.map(n => (
          <div key={n.id} data-testid={`node-${n.id}`}>
            {n.name}
          </div>
        ))}
        {graphData.links.map((l, i) => {
          const src = l.source?.id || l.source
          const tgt = l.target?.id || l.target
          return (
            <div key={i} data-testid={`link-${src}-${tgt}`}>
              {src} {"->"} {tgt}
            </div>
          )
        })}
      </div>
    )
  }
})

describe('GraphView Component', () => {
  const defaultGraphData = {
    nodes: [
      { id: '1', name: 'main.py', type: 'File' },
      { id: '2', name: 'process_data', type: 'Function' },
      { id: '3', name: 'DataModel', type: 'Class' }
    ],
    links: [
      { source: '1', target: '2' }, // File -> Function
      { source: '2', target: '3' }  // Function -> Class
    ]
  }

  const defaultStats = { total_nodes: 3, total_edges: 2 }
  const defaultStatus = { total_functions: 10, tested_count: 5 }

  it('renders stats, search, filters and mock force graph correctly', () => {
    const highlightNodes = new Set()
    render(
      <GraphView
        graphData={defaultGraphData}
        graphLoading={false}
        stats={defaultStats}
        status={defaultStatus}
        highlightNodes={highlightNodes}
        setHighlightNodes={() => {}}
      />
    )

    // Verify search input
    expect(screen.getByPlaceholderText(/search functions/i)).toBeInTheDocument()

    // Verify stats cards in header
    expect(screen.getByText('Functions')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument()
    expect(screen.getByText('Test coverage')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()

    // Verify all nodes are rendered in mock graph
    expect(screen.getByTestId('nodes-count')).toHaveTextContent('3')
    expect(screen.getByTestId('links-count')).toHaveTextContent('2')
    expect(screen.getByText('main.py')).toBeInTheDocument()
    expect(screen.getByText('process_data')).toBeInTheDocument()
    expect(screen.getByText('DataModel')).toBeInTheDocument()
  })

  it('filters nodes and corresponding links when a specific filter is clicked', async () => {
    const highlightNodes = new Set()
    render(
      <GraphView
        graphData={defaultGraphData}
        graphLoading={false}
        stats={defaultStats}
        status={defaultStatus}
        highlightNodes={highlightNodes}
        setHighlightNodes={() => {}}
      />
    )

    // Click "Function" filter chip
    const functionFilterChip = screen.getByRole('button', { name: 'Function' })
    await userEvent.click(functionFilterChip)

    // Verify only 1 node is rendered (the Function node)
    expect(screen.getByTestId('nodes-count')).toHaveTextContent('1')
    expect(screen.getByText('process_data')).toBeInTheDocument()
    expect(screen.queryByText('main.py')).not.toBeInTheDocument()
    expect(screen.queryByText('DataModel')).not.toBeInTheDocument()

    // Verify links count is 0 because other node endpoints are filtered out (No dangling links!)
    expect(screen.getByTestId('links-count')).toHaveTextContent('0')
  })
})
