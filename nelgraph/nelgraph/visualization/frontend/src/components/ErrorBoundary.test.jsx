import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ErrorBoundary from './ErrorBoundary'
import axios from 'axios'

// Mock axios
vi.mock('axios', () => {
  return {
    default: {
      post: vi.fn().mockResolvedValue({ data: { success: true } })
    }
  }
})

// A component that always throws an error for testing
function BuggyComponent() {
  throw new Error('Test rendering crash')
}

describe('ErrorBoundary Component', () => {
  let consoleErrorMock

  beforeEach(() => {
    // Suppress console.error output in test logs during intentional crashes
    consoleErrorMock = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    consoleErrorMock.mockRestore()
    vi.clearAllMocks()
  })

  it('renders children normally when no error occurs', () => {
    render(
      <ErrorBoundary>
        <div data-testid="child">Safe Child Content</div>
      </ErrorBoundary>
    )
    expect(screen.getByTestId('child')).toHaveTextContent('Safe Child Content')
    expect(screen.queryByText(/Error Rendering Node Details/)).not.toBeInTheDocument()
  })

  it('renders fallback error message and calls axios.post when child crashes', () => {
    const selectedNode = { name: 'buggy_func', type: 'Function' }

    render(
      <ErrorBoundary selectedNode={selectedNode}>
        <BuggyComponent />
      </ErrorBoundary>
    )

    // Verify fallback UI is rendered
    expect(screen.getByText('⚠️ Error Rendering Node Details')).toBeInTheDocument()
    expect(screen.getByText(/Test rendering crash/)).toBeInTheDocument()

    // Verify axios.post was called with log details
    expect(axios.post).toHaveBeenCalledTimes(1)
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/log'),
      expect.objectContaining({
        level: 'error',
        message: 'Test rendering crash',
        source: 'frontend_error_boundary',
        selectedNode: { name: 'buggy_func', type: 'Function' }
      })
    )
  })

  it('resets error state and triggers onReset when Reset button is clicked', async () => {
    const onResetMock = vi.fn()
    const selectedNode = { name: 'buggy_func', type: 'Function' }

    let shouldThrow = true
    function BuggyOrSafeComponent() {
      if (shouldThrow) {
        throw new Error('Test rendering crash')
      }
      return <div data-testid="recovered">Recovered safe component</div>
    }

    render(
      <ErrorBoundary selectedNode={selectedNode} onReset={onResetMock}>
        <BuggyOrSafeComponent />
      </ErrorBoundary>
    )

    // Verify crash UI
    expect(screen.getByText('⚠️ Error Rendering Node Details')).toBeInTheDocument()

    // Disable throwing before clicking reset so the child can render safely
    shouldThrow = false

    // Click reset button
    const resetBtn = screen.getByRole('button', { name: 'Reset Panel' })
    await userEvent.click(resetBtn)

    // Verify callback was triggered
    expect(onResetMock).toHaveBeenCalledTimes(1)

    // Verify it recovered and renders child safely
    expect(screen.getByTestId('recovered')).toHaveTextContent('Recovered safe component')
    expect(screen.queryByText('⚠️ Error Rendering Node Details')).not.toBeInTheDocument()
  })
})
