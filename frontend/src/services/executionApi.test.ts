import { afterEach, describe, expect, it, vi } from 'vitest'

import { executionApi } from './executionApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('executionApi', () => {
  it('loads project-specific automation candidates from the backend', async () => {
    const candidates = [
      {
        id: 1,
        test_case_id: 'TC-1',
        project_id: 7,
        scan_id: 3,
        scenario: 'Verify heading is visible.',
        description: 'Metadata-backed check.',
        preconditions: [],
        steps: [],
        test_data: {},
        expected_result: 'The heading is visible.',
        priority: 'Medium',
        category: 'Functional',
        execution_type: 'Manual',
        status: 'Not Executed',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        automatable: true,
        eligibility: 'Automatable',
        reason: null,
        action: 'Inspect the element.',
      },
    ]
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(candidates), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(executionApi.listCandidates(7)).resolves.toEqual(candidates)
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8001/api/projects/7/execution-candidates',
      expect.objectContaining({ headers: expect.objectContaining({ Accept: 'application/json' }) }),
    )
  })

  it('posts the selected test-case IDs and returns persisted run detail', async () => {
    const detail = {
      id: 12,
      project_id: 7,
      project_name: 'Demo',
      scan_id: 3,
      status: 'completed',
      total_tests: 1,
      passed: 1,
      failed: 0,
      blocked: 0,
      errors: 0,
      not_automatable: 0,
      started_at: '2026-01-01T00:00:00Z',
      completed_at: '2026-01-01T00:00:01Z',
      duration_ms: 1000,
      results: [],
    }
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(detail), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(executionApi.startRun(7, ['TC-1'])).resolves.toEqual(detail)
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8001/api/projects/7/executions',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ test_case_ids: ['TC-1'] }),
      }),
    )
  })

  it('surfaces backend validation errors instead of fabricating a run', async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify({ detail: 'One or more test cases were not found in this project' }),
      { status: 404, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetchMock)

    await expect(executionApi.startRun(7, ['missing'])).rejects.toThrow(
      'One or more test cases were not found in this project',
    )
  })

  it('requests a downloadable project-scoped CSV report', async () => {
    const csv = 'Project,Run\\nDemo,12\\n'
    const fetchMock = vi.fn(async () => new Response(csv, {
      status: 200,
      headers: { 'Content-Type': 'text/csv' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const blob = await executionApi.downloadCsv(7)
    expect(await blob.text()).toBe(csv)
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8001/api/reports.csv?project_id=7',
      { headers: { Accept: 'text/csv' } },
    )
  })
})
