// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import DashboardPage from './DashboardPage'
import TestCasesPage from './TestCasesPage'
import TestGeneratorPage from './TestGeneratorPage'

const mocks = vi.hoisted(() => ({
  listApplications: vi.fn(),
  listProjectScans: vi.fn(),
  generateFromScan: vi.fn(),
  listProjectTestCases: vi.fn(),
  updateStatus: vi.fn(),
  getBackendHealth: vi.fn(),
  getDashboardSummary: vi.fn(),
}))

vi.mock('../services/projectApi', () => ({
  projectApi: { listApplications: mocks.listApplications },
}))

vi.mock('../services/scannerApi', () => ({
  scannerApi: { listProjectScans: mocks.listProjectScans },
}))

vi.mock('../services/testCaseApi', () => ({
  testCaseApi: {
    listProjectTestCases: mocks.listProjectTestCases,
    generateFromScan: mocks.generateFromScan,
    updateStatus: mocks.updateStatus,
  },
}))

vi.mock('../services/executionApi', () => ({
  executionApi: {
    getBackendHealth: mocks.getBackendHealth,
    getDashboardSummary: mocks.getDashboardSummary,
  },
}))

const projects = [
  {
    id: 5,
    name: 'Project Five',
    url: 'https://example.com',
    description: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 6,
    name: 'Project Six',
    url: 'https://example.org',
    description: null,
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
]

const savedCase = {
  id: 1,
  test_case_id: 'TC-5-case',
  project_id: 5,
  scan_id: 3,
  scenario: 'Inspect the Docs link.',
  description: 'Check the scanner-backed link metadata.',
  preconditions: ['Page is loaded.'],
  steps: ['Inspect the Docs link.'],
  test_data: { text: 'Docs', href: '/docs' },
  expected_result: 'The link destination is recorded.',
  priority: 'Medium' as const,
  category: 'Navigation' as const,
  execution_type: 'Manual' as const,
  status: 'Not Executed' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const generationResponse = {
  project_id: 5,
  scan_id: 3,
  summary: {
    generated_count: 2,
    saved_count: 2,
    inserted_count: 1,
    duplicate_count: 1,
    project_id: 5,
    scan_id: 3,
    notes: ['Generated from scanner metadata.'],
  },
  test_cases: [
    { ...savedCase, persistence_status: 'inserted' as const },
    {
      ...savedCase,
      id: 2,
      test_case_id: 'TC-5-existing',
      scenario: 'Verify the saved button.',
      persistence_status: 'duplicate' as const,
    },
  ],
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.listApplications.mockResolvedValue(projects)
  mocks.listProjectScans.mockResolvedValue([
    {
      id: 4,
      project_id: 5,
      status: 'running',
      started_at: '2026-01-04T00:00:00Z',
      completed_at: null,
      page_title: 'Running',
      final_url: 'https://example.com',
      result_json: null,
      error_message: null,
    },
    {
      id: 3,
      project_id: 5,
      status: 'completed',
      started_at: '2026-01-03T00:00:00Z',
      completed_at: '2026-01-03T00:00:01Z',
      page_title: 'Example',
      final_url: 'https://example.com',
      result_json: null,
      error_message: null,
    },
  ])
  mocks.generateFromScan.mockResolvedValue(generationResponse)
  mocks.listProjectTestCases.mockResolvedValue([savedCase])
  mocks.updateStatus.mockImplementation(async (_id: string, status: string) => ({
    ...savedCase,
    status,
    updated_at: '2026-01-02T00:00:00Z',
  }))
  mocks.getBackendHealth.mockResolvedValue({ status: 'healthy' })
  mocks.getDashboardSummary.mockResolvedValue({
    project_count: 2,
    test_case_count: 1,
    total_runs: 0,
    tests_executed: 0,
    pass_rate: null,
    passed: 0,
    failed: 0,
    blocked: 0,
    errors: 0,
    recent_runs: [],
  })
})

afterEach(() => {
  cleanup()
})

describe('separate generator and saved inventory pages', () => {
  it('routes the dashboard Generate Test Cases quick action to the generator', async () => {
    const onNavigate = vi.fn()
    render(<DashboardPage onNavigate={onNavigate} />)

    fireEvent.click(await screen.findByRole('button', { name: /Generate Test Cases/ }))

    expect(onNavigate).toHaveBeenCalledWith('generator')
  })

  it('shows in-progress dashboard runs as Running, not Passed', async () => {
    mocks.getDashboardSummary.mockResolvedValueOnce({
      project_count: 2,
      test_case_count: 1,
      total_runs: 1,
      tests_executed: 0,
      pass_rate: null,
      passed: 0,
      failed: 0,
      blocked: 0,
      errors: 0,
      recent_runs: [
        {
          id: 9,
          project_id: 5,
          status: 'running',
          total_tests: 1,
          passed: 0,
          failed: 0,
          blocked: 0,
          errors: 0,
          not_automatable: 0,
          duration_ms: 0,
          started_at: '2026-01-01T00:00:00Z',
          completed_at: null,
        },
      ],
    })
    render(<DashboardPage />)

    const runName = await screen.findByText('Run #9')
    expect(runName.closest('tr')?.textContent).toContain('Running')
    expect(screen.getByRole('columnheader', { name: 'Failed / blocked / error' })).toBeTruthy()
  })

  it('generates from a completed selected scan and distinguishes inserts from duplicates', async () => {
    const onOpenSavedTestCases = vi.fn()
    const generationRequest = deferred<typeof generationResponse>()
    mocks.generateFromScan.mockReturnValueOnce(generationRequest.promise)
    render(<TestGeneratorPage onOpenSavedTestCases={onOpenSavedTestCases} />)

    await screen.findByRole('option', { name: /Scan #3/ })
    expect(screen.queryByRole('option', { name: /Scan #4/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Generate Test Cases' }))
    expect(await screen.findByRole('button', { name: /Generating test cases/ })).toBeTruthy()
    generationRequest.resolve(generationResponse)

    expect(await screen.findByText('Newly saved')).toBeTruthy()
    expect(screen.getByText('Already existed')).toBeTruthy()
    expect(screen.getByText('Generated')).toBeTruthy()
    expect(screen.getAllByText('2', { selector: 'p' })).toHaveLength(2)
    expect(mocks.generateFromScan).toHaveBeenCalledWith(5, 3)

    fireEvent.click(screen.getByRole('button', { name: /Open saved Test Cases/ }))
    expect(onOpenSavedTestCases).toHaveBeenCalledWith(5)
  })

  it('shows generator loading, empty-scan, and backend error states', async () => {
    const projectsRequest = deferred<typeof projects>()
    mocks.listApplications.mockReturnValueOnce(projectsRequest.promise)
    const { unmount } = render(<TestGeneratorPage onOpenSavedTestCases={vi.fn()} />)
    expect(screen.getByText('Loading projects...')).toBeTruthy()

    projectsRequest.resolve([])
    expect(await screen.findByText('Register an application in Projects before generating test cases.')).toBeTruthy()
    expect(mocks.generateFromScan).not.toHaveBeenCalled()
    unmount()

    mocks.listProjectScans.mockResolvedValueOnce([])
    render(<TestGeneratorPage onOpenSavedTestCases={vi.fn()} />)
    expect(await screen.findByText(/no completed scans yet/i)).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Generate Test Cases' }) as HTMLButtonElement).disabled).toBe(true)
    cleanup()

    mocks.generateFromScan.mockRejectedValueOnce(new Error('Generation rejected'))
    render(<TestGeneratorPage onOpenSavedTestCases={vi.fn()} />)
    await screen.findByRole('option', { name: /Scan #3/ })
    fireEvent.click(screen.getByRole('button', { name: 'Generate Test Cases' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Generation rejected')
    cleanup()

    mocks.listApplications.mockRejectedValueOnce(new Error('Projects unavailable'))
    render(<TestGeneratorPage onOpenSavedTestCases={vi.fn()} />)
    expect((await screen.findByRole('alert')).textContent).toContain('Projects unavailable')
  })

  it('loads scans for the selected project and generates using its selected scan', async () => {
    mocks.listProjectScans
      .mockResolvedValueOnce([
        {
          id: 3,
          project_id: 5,
          status: 'completed',
          started_at: '2026-01-03T00:00:00Z',
          completed_at: '2026-01-03T00:00:01Z',
          page_title: 'Project Five scan',
          final_url: 'https://example.com',
          result_json: null,
          error_message: null,
        },
      ])
      .mockResolvedValueOnce([
        {
          id: 8,
          project_id: 6,
          status: 'completed',
          started_at: '2026-01-08T00:00:00Z',
          completed_at: '2026-01-08T00:00:01Z',
          page_title: 'Project Six scan',
          final_url: 'https://example.org',
          result_json: null,
          error_message: null,
        },
      ])
    mocks.generateFromScan.mockResolvedValueOnce({
      ...generationResponse,
      project_id: 6,
      scan_id: 8,
      summary: { ...generationResponse.summary, project_id: 6, scan_id: 8 },
      test_cases: generationResponse.test_cases.map((item) => ({
        ...item,
        project_id: 6,
        scan_id: 8,
      })),
    })
    render(<TestGeneratorPage onOpenSavedTestCases={vi.fn()} />)
    await screen.findByRole('option', { name: /Scan #3/ })

    fireEvent.change(screen.getByLabelText('Project'), { target: { value: '6' } })
    await screen.findByRole('option', { name: /Scan #8/ })
    expect(mocks.listProjectScans).toHaveBeenLastCalledWith(6)

    fireEvent.click(screen.getByRole('button', { name: 'Generate Test Cases' }))
    expect(await screen.findByText('Project / Scan')).toBeTruthy()
    expect(mocks.generateFromScan).toHaveBeenCalledWith(6, 8)
  })

  it('loads the inventory, filters cases, shows details, and updates status', async () => {
    render(<TestCasesPage initialProjectId={5} />)

    expect(await screen.findAllByText(savedCase.scenario)).toHaveLength(3)
    expect(mocks.listProjectTestCases).toHaveBeenCalledWith(5, {
      category: undefined,
      priority: undefined,
      status: undefined,
    })
    expect(screen.getByText(savedCase.expected_result)).toBeTruthy()
    expect(screen.getByText('Page is loaded.')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'Navigation' } })
    await waitFor(() => {
      expect(mocks.listProjectTestCases).toHaveBeenLastCalledWith(5, {
        category: 'Navigation',
        priority: undefined,
        status: undefined,
      })
    })

    fireEvent.change(screen.getByLabelText('Priority'), { target: { value: 'Medium' } })
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'Not Executed' } })
    await waitFor(() => {
      expect(mocks.listProjectTestCases).toHaveBeenLastCalledWith(5, {
        category: 'Navigation',
        priority: 'Medium',
        status: 'Not Executed',
      })
    })
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: '' } })

    fireEvent.change(screen.getByLabelText('Update status'), { target: { value: 'Passed' } })
    expect(await screen.findByText('Status updated to Passed.')).toBeTruthy()
    expect(mocks.updateStatus).toHaveBeenCalledWith('TC-5-case', 'Passed')
    expect(screen.getAllByText('Passed', { selector: 'span' })).toHaveLength(2)
  })

  it('displays the persisted Automated execution type in inventory and details', async () => {
    mocks.listProjectTestCases.mockResolvedValueOnce([
      { ...savedCase, execution_type: 'Automated' as const },
    ])
    render(<TestCasesPage initialProjectId={5} />)

    const [caseId] = await screen.findAllByText('TC-5-case')
    expect(caseId.closest('tr')?.textContent).toContain('Automated')
    expect(screen.getAllByText('Automated')).toHaveLength(2)
  })

  it('shows inventory loading, empty, and retrieval error states', async () => {
    const projectsRequest = deferred<typeof projects>()
    const casesRequest = deferred<typeof savedCase[]>()
    mocks.listApplications.mockReturnValueOnce(projectsRequest.promise)
    mocks.listProjectTestCases.mockReturnValueOnce(casesRequest.promise)
    const { unmount } = render(<TestCasesPage />)
    expect(screen.getByText('Loading projects...')).toBeTruthy()
    projectsRequest.resolve(projects)
    expect(await screen.findByText('Loading test cases...')).toBeTruthy()
    casesRequest.resolve([])
    expect(await screen.findByText('No test cases available')).toBeTruthy()
    unmount()

    mocks.listProjectTestCases.mockRejectedValueOnce(new Error('Inventory unavailable'))
    render(<TestCasesPage initialProjectId={5} />)
    expect((await screen.findByRole('alert')).textContent).toContain('Inventory unavailable')
  })

  it('routes Test Generator and Test Cases to distinct interfaces', async () => {
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Test Generator' }))
    expect(await screen.findByLabelText('Completed scan')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Generate Test Cases' })).toBeTruthy()
    expect(screen.queryByLabelText('Category')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Test Cases' }))
    expect(await screen.findByLabelText('Category')).toBeTruthy()
    expect(screen.getByText('Saved test cases')).toBeTruthy()
    expect(screen.queryByLabelText('Completed scan')).toBeNull()
  })

  it('shows generated saved cases in the inventory after navigating from the generator', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Test Generator' }))
    await screen.findByRole('option', { name: /Scan #3/ })

    fireEvent.click(screen.getByRole('button', { name: 'Generate Test Cases' }))
    expect(await screen.findByText('Newly saved')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Open saved Test Cases/ }))

    expect(await screen.findByLabelText('Category')).toBeTruthy()
    expect(await screen.findAllByText(savedCase.scenario)).toHaveLength(3)
    expect(mocks.listProjectTestCases).toHaveBeenCalledWith(5, {
      category: undefined,
      priority: undefined,
      status: undefined,
    })
  })
})
