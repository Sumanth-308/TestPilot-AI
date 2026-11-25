import type { Application, ApplicationCreate, ApplicationUpdate } from '../types/application'

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

export const projectApi = {
  listApplications: async (): Promise<Application[]> =>
    request<Application[]>('/api/projects'),

  createApplication: async (application: ApplicationCreate): Promise<Application> =>
    request<Application>('/api/projects', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(application),
    }),

  getApplication: async (id: number): Promise<Application> =>
    request<Application>(`/api/projects/${id}`),

  updateApplication: async (id: number, application: ApplicationUpdate): Promise<Application> =>
    request<Application>(`/api/projects/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(application),
    }),

  deleteApplication: async (id: number): Promise<void> =>
    request<void>(`/api/projects/${id}`, {
      method: 'DELETE',
    }),
}
