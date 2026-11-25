export interface ScanButton {
  text?: string
  type?: string
  form_id?: string | null
}

export interface ScanLink {
  text?: string
  href?: string
}

export interface ScanInputField {
  type?: string
  name?: string | null
  placeholder?: string | null
  id?: string | null
  required?: boolean
}

export interface ScanForm {
  id?: string | null
  action?: string
  method?: string
  fields?: ScanInputField[]
}

export interface ScanResultJson {
  page_title: string | null
  final_url: string | null
  headings: string[]
  buttons: ScanButton[]
  links: ScanLink[]
  inputs: ScanInputField[]
  forms: ScanForm[]
  console_errors: string[]
  page_errors: string[]
  navigation_failures: string[]
}

export interface ScanRecord {
  id: number
  project_id: number
  status: 'running' | 'completed' | 'failed'
  started_at: string
  completed_at: string | null
  page_title: string | null
  final_url: string | null
  result_json: ScanResultJson | null
  error_message: string | null
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

export const scannerApi = {
  listProjectScans: async (projectId: number): Promise<ScanRecord[]> =>
    request<ScanRecord[]>(`/api/projects/${projectId}/scans`),

  startScan: async (projectId: number): Promise<ScanRecord> =>
    request<ScanRecord>(`/api/projects/${projectId}/scans`, {
      method: 'POST',
    }),

  getScan: async (scanId: number): Promise<ScanRecord> =>
    request<ScanRecord>(`/api/scans/${scanId}`),
}
