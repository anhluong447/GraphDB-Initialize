import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DetailPanel from './DetailPanel'

describe('DetailPanel Component', () => {
  const defaultSelectedNode = { name: 'add_user', type: 'Function' }
  const defaultDetail = {
    node: {
      name: 'add_user',
      how_it_works: 'Adds a user to the database after validating fields.',
      inputs: JSON.stringify({ email: 'str', role: 'str' }),
      output: 'dict',
      raises: 'ValueError',
      complexity: 3,
      is_async: true,
      visibility: 'public',
      start_line: 10,
      end_line: 30,
      file: 'auth.py',
      tested: false,
      edge_cases: '[]',
      test_recommendations: '[]'
    },
    labels: ['Function'],
    community_name: 'Auth Module',
    outgoing: [],
    incoming: []
  }

  it('renders loading state correctly', () => {
    render(
      <DetailPanel
        selectedNode={defaultSelectedNode}
        detail={null}
        loading={true}
      />
    )
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('renders basic node details and properties correctly', () => {
    render(
      <DetailPanel
        selectedNode={defaultSelectedNode}
        detail={defaultDetail}
        loading={false}
      />
    )

    // Node header and metadata
    expect(screen.getByText('add_user')).toBeInTheDocument()
    expect(screen.getByText('auth.py')).toBeInTheDocument()
    expect(screen.getByText('Adds a user to the database after validating fields.')).toBeInTheDocument()

    // Signature section
    expect(screen.getByText('email')).toBeInTheDocument()
    expect(screen.getByText('role')).toBeInTheDocument()
    expect(screen.getByText('returns')).toBeInTheDocument()
    expect(screen.getByText('dict')).toBeInTheDocument()
    expect(screen.getByText('raises')).toBeInTheDocument()
    expect(screen.getByText('ValueError')).toBeInTheDocument()

    // Properties section
    expect(screen.getByText('Complexity')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('Async')).toBeInTheDocument()
    expect(screen.getByText('Yes')).toBeInTheDocument()
    expect(screen.getByText('Visibility')).toBeInTheDocument()
    expect(screen.getByText('public')).toBeInTheDocument()
    expect(screen.getByText('10–30')).toBeInTheDocument()
    expect(screen.getByText('Auth Module')).toBeInTheDocument()
  })

  it('renders simple string lists for edge cases and test recommendations', () => {
    const detailWithStringLists = {
      ...defaultDetail,
      node: {
        ...defaultDetail.node,
        edge_cases: 'Input email is empty\nDuplicate user email',
        test_recommendations: 'Test with mock database\nAssert ValueError is raised on duplicate'
      }
    }

    render(
      <DetailPanel
        selectedNode={defaultSelectedNode}
        detail={detailWithStringLists}
        loading={false}
      />
    )

    expect(screen.getByText('Input email is empty')).toBeInTheDocument()
    expect(screen.getByText('Duplicate user email')).toBeInTheDocument()
    expect(screen.getByText('Test with mock database')).toBeInTheDocument()
    expect(screen.getByText('Assert ValueError is raised on duplicate')).toBeInTheDocument()
  })

  it('renders structured objects in edge_cases and test_recommendations without crashing', () => {
    const detailWithStructuredObjects = {
      ...defaultDetail,
      node: {
        ...defaultDetail.node,
        edge_cases: JSON.stringify([
          { type: 'edge', name: 'empty_email', description: 'Passing empty email string' }
        ]),
        test_recommendations: JSON.stringify([
          { type: 'error', name: 'duplicate_auth', path: 'test_auth.py', description: 'Assert IntegrityError on duplicate email write' }
        ])
      }
    }

    render(
      <DetailPanel
        selectedNode={defaultSelectedNode}
        detail={detailWithStructuredObjects}
        loading={false}
      />
    )

    // Verify correct format and content using renderListItem helper
    expect(screen.getByText('[edge] empty_email: Passing empty email string')).toBeInTheDocument()
    expect(screen.getByText('[error] duplicate_auth: Assert IntegrityError on duplicate email write')).toBeInTheDocument()
  })

  it('triggers onClose when close button is clicked', async () => {
    const onCloseMock = vi.fn()
    render(
      <DetailPanel
        selectedNode={defaultSelectedNode}
        detail={defaultDetail}
        loading={false}
        onClose={onCloseMock}
      />
    )

    const closeBtn = screen.getByRole('button', { name: '×' })
    await userEvent.click(closeBtn)
    expect(onCloseMock).toHaveBeenCalledTimes(1)
  })

  it('triggers onNodeNavigate when calling or called-by chips are clicked', async () => {
    const onNodeNavigateMock = vi.fn()
    const detailWithRelations = {
      ...defaultDetail,
      incoming: [{ source: 'login_route', type: 'CALLS' }],
      outgoing: [{ target: 'db_insert', type: 'CALLS' }]
    }

    render(
      <DetailPanel
        selectedNode={defaultSelectedNode}
        detail={detailWithRelations}
        loading={false}
        onNodeNavigate={onNodeNavigateMock}
      />
    )

    const incomingChip = screen.getByRole('button', { name: /login_route/ })
    await userEvent.click(incomingChip)
    expect(onNodeNavigateMock).toHaveBeenLastCalledWith('login_route')

    const outgoingChip = screen.getByRole('button', { name: /db_insert/ })
    await userEvent.click(outgoingChip)
    expect(onNodeNavigateMock).toHaveBeenLastCalledWith('db_insert')
  })
})
