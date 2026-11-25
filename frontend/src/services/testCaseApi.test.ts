import { afterEach, describe, expect, it, vi } from 'vitest'

import { testCaseApi } from './testCaseApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('testCaseApi generation', () => {
  it('posts to the existing project-and-scan generation endpoint', async () => {
    const response = {
      project_id: 6,
      scan_id: 8,
      summary: {
        generated_count: 1,
        saved_count: 1,
        inserted_count: 1,
        duplicate_count: 0,
        project_id: 6,
        scan_id: 8,
      },
      test_cases: [],
    }
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(response), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(testCaseApi.generateFromScan(6, 8)).resolves.toEqual(response)
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8001/api/projects/6/scans/8/test-cases/generate',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
