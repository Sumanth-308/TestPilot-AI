import type {
  BugFinding,
  DashboardSummary,
  ExecutionCandidate,
  ExecutionDetail,
  ExecutionReport,
  ExecutionRun,
} from '../types/execution'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8001').replace(/\/$/, '')

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.headers ?? {}),
    },
  })

  const text = response.status === 204 ? '' : await response.text()
  let payload: unknown
  if (text) {
    try {
      payload = JSON.parse(text) as unknown
    } catch {
      payload = text
    }
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? payload.detail
        : 'Request failed'
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail) && detail.length > 0 && typeof detail[0] === 'object' && detail[0] !== null && 'msg' in detail[0]
        ? String(detail[0].msg)
        : 'Request failed'
    throw new Error(message)
  }

  if (!text) {
    return undefined as T
  }
  return payload as T
}

export const executionApi = {
  getBackendHealth: (): Promise<{ status: string }> =>
    request('/health'),

  listCandidates: (projectId: number): Promise<ExecutionCandidate[]> =>
    request(`/api/projects/${projectId}/execution-candidates`),

  startRun: (projectId: number, testCaseIds: string[]): Promise<ExecutionDetail> =>
    request(`/api/projects/${projectId}/executions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ test_case_ids: testCaseIds }),
    }),

  listRuns: (projectId: number): Promise<ExecutionRun[]> =>
    request(`/api/projects/${projectId}/executions`),

  getRun: (runId: number): Promise<ExecutionDetail> =>
    request(`/api/executions/${runId}`),

  listBugs: (projectId?: number): Promise<BugFinding[]> => {
    const query = projectId === undefined ? '' : `?project_id=${projectId}`
    return request(`/api/bug-analysis${query}`)
  },

  getReports: (projectId?: number): Promise<ExecutionReport> => {
    const query = projectId === undefined ? '' : `?project_id=${projectId}`
    return request(`/api/reports${query}`)
  },

  getDashboardSummary: (): Promise<DashboardSummary> =>
    request('/api/dashboard/summary'),

  downloadCsv: async (projectId?: number): Promise<Blob> => {
    const query = projectId === undefined ? '' : `?project_id=${projectId}`
    const response = await fetch(`${API_BASE_URL}/api/reports.csv${query}`, {
      headers: { Accept: 'text/csv' },
    })
    if (!response.ok) {
      const error = await response.text()
      throw new Error(error || 'Report download failed')
    }
    return response.blob()
  },
}
