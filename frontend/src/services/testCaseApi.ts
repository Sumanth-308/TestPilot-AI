export type TestCaseStatus = 'Not Executed' | 'Passed' | 'Failed' | 'Blocked'
export type TestCasePriority = 'High' | 'Medium' | 'Low'
export type TestCaseCategory =
  | 'Positive'
  | 'Negative'
  | 'Boundary'
  | 'Input Validation'
  | 'Form Validation'
  | 'Navigation'
  | 'Button Interaction'
  | 'Functional'

export interface TestCase {
  id: number
  test_case_id: string
  project_id: number
  scan_id: number
  scenario: string
  description: string
  preconditions: string[]
  steps: string[]
  test_data: Record<string, unknown>
  expected_result: string
  priority: TestCasePriority
  category: TestCaseCategory
  execution_type: 'Manual' | 'Automated'
  status: TestCaseStatus
  created_at: string
  updated_at: string
}

export interface TestCaseFilters {
  category?: string
  priority?: string
  status?: string
}

export interface GeneratedTestCase extends TestCase {
  persistence_status: 'inserted' | 'duplicate'
}

export interface TestCaseGenerationSummary {
  generated_count: number
  saved_count: number
  inserted_count: number
  duplicate_count: number
  project_id: number
  scan_id: number
  empty_scan?: boolean
  supported_metadata?: Record<string, number>
  generated_categories?: Record<string, number>
  notes?: string[]
}

export interface TestCaseGenerationResponse {
  project_id: number
  scan_id: number
  test_cases: GeneratedTestCase[]
  summary: TestCaseGenerationSummary
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8001').replace(/\/$/, '')

async function parseJsonResponse<T>(response: Response): Promise<T | null> {
  const text = await response.text()

  if (!text) {
    return null
  }

  try {
    return JSON.parse(text) as T
  } catch {
    return text as unknown as T
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.headers ?? {}),
    },
  })

  if (response.status === 204) {
    return undefined as T
  }

  const payload = await parseJsonResponse<T>(response)

  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? payload.detail
        : 'Request failed'

    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail) && detail.length > 0 && typeof detail[0] === 'object' && detail[0] !== null && 'msg' in detail[0]
          ? String(detail[0].msg)
          : 'Request failed'

    throw new Error(message)
  }

  return payload as T
}

export const testCaseApi = {
  listProjectTestCases: async (projectId: number, filters: TestCaseFilters = {}): Promise<TestCase[]> => {
    const params = new URLSearchParams()

    if (filters.category) {
      params.set('category', filters.category)
    }
    if (filters.priority) {
      params.set('priority', filters.priority)
    }
    if (filters.status) {
      params.set('status', filters.status)
    }

    const query = params.toString()
    return request<TestCase[]>(`/api/projects/${projectId}/test-cases${query ? `?${query}` : ''}`)
  },

  getTestCase: async (testCaseId: string): Promise<TestCase> =>
    request<TestCase>(`/api/test-cases/${encodeURIComponent(testCaseId)}`),

  generateFromScan: async (projectId: number, scanId: number): Promise<TestCaseGenerationResponse> =>
    request<TestCaseGenerationResponse>(
      `/api/projects/${projectId}/scans/${scanId}/test-cases/generate`,
      { method: 'POST' },
    ),

  updateStatus: async (testCaseId: string, status: TestCaseStatus): Promise<TestCase> =>
    request<TestCase>(`/api/test-cases/${encodeURIComponent(testCaseId)}/status`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ status }),
    }),
}
