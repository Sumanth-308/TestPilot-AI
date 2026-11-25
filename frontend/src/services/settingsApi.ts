import type { WorkspaceSettings, WorkspaceSettingsUpdate } from '../types/settings'

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
        : 'Settings request failed'
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail) && detail.length > 0 && typeof detail[0] === 'object' && detail[0] !== null && 'msg' in detail[0]
        ? String(detail[0].msg)
        : 'Settings request failed'
    throw new Error(message)
  }
  return payload as T
}

export const settingsApi = {
  get: (): Promise<WorkspaceSettings> => request('/api/settings'),

  update: (settings: WorkspaceSettingsUpdate): Promise<WorkspaceSettings> =>
    request('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    }),

  reset: (): Promise<WorkspaceSettings> =>
    request('/api/settings/reset', { method: 'POST' }),
}
