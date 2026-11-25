// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import type { WorkspaceSettings } from '../types/settings'
import SettingsPage from './SettingsPage'

const mocks = vi.hoisted(() => ({
  listApplications: vi.fn(),
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
  resetSettings: vi.fn(),
  getBackendHealth: vi.fn(),
  getDashboardSummary: vi.fn(),
}))

vi.mock('../services/projectApi', () => ({
  projectApi: { listApplications: mocks.listApplications },
}))

vi.mock('../services/settingsApi', () => ({
  settingsApi: {
    get: mocks.getSettings,
    update: mocks.updateSettings,
    reset: mocks.resetSettings,
  },
}))

vi.mock('../services/executionApi', () => ({
  executionApi: {
    getBackendHealth: mocks.getBackendHealth,
    getDashboardSummary: mocks.getDashboardSummary,
  },
}))

const applications = [
  {
    id: 5,
    name: 'Checkout',
    url: 'https://checkout.example.test',
    description: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const settings: WorkspaceSettings = {
  workspace_name: 'TestPilot AI',
  default_environment: 'development',
  default_project_id: 5,
  environment_urls: {},
  configured_environments: {},
  execution_timeout_ms: 10000,
  max_tests_per_run: 100,
  quality_gate_pass_rate_threshold: 80,
  quality_gate_failure_threshold: 0,
  updated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.listApplications.mockResolvedValue(applications)
  mocks.getSettings.mockResolvedValue(settings)
  mocks.updateSettings.mockImplementation(async (value: Omit<WorkspaceSettings, 'configured_environments' | 'updated_at'>) => ({
    ...value,
    configured_environments: {},
    updated_at: '2026-01-02T00:00:00Z',
  }))
  mocks.resetSettings.mockResolvedValue(settings)
  mocks.getBackendHealth.mockResolvedValue({ status: 'healthy' })
  mocks.getDashboardSummary.mockResolvedValue({
    project_count: 0,
    test_case_count: 0,
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

afterEach(() => cleanup())

describe('Settings page', () => {
  it('loads settings, saves edits, and persists the configured project/environment preferences', async () => {
    render(<SettingsPage />)

    expect(await screen.findByDisplayValue('TestPilot AI')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Workspace name'), { target: { value: 'QA workspace' } })
    fireEvent.change(document.getElementById('settings-active-environment') as HTMLSelectElement, { target: { value: 'staging' } })
    fireEvent.change(document.getElementById('settings-url-staging') as HTMLInputElement, { target: { value: 'https://stage.example.test' } })
    fireEvent.change(document.getElementById('settings-timeout') as HTMLInputElement, { target: { value: '14000' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Save Changes' })[0])

    await waitFor(() => expect(mocks.updateSettings).toHaveBeenCalledTimes(1))
    const sentSettings = mocks.updateSettings.mock.calls[0][0]
    expect(sentSettings.workspace_name).toBe('QA workspace')
    expect(sentSettings.default_environment).toBe('staging')
    expect(sentSettings.environment_urls[5].staging).toBe('https://stage.example.test')
    expect(sentSettings.execution_timeout_ms).toBe(14000)
    expect(await screen.findByText(/Settings saved/)).toBeTruthy()
  })

  it('provides reset, loading, empty-project, and error states', async () => {
    mocks.getSettings.mockReturnValueOnce(new Promise(() => undefined))
    const { unmount } = render(<SettingsPage />)
    expect(screen.getByRole('status').textContent).toContain('Loading')
    unmount()

    mocks.getSettings.mockResolvedValue(settings)
    mocks.listApplications.mockResolvedValue([])
    render(<SettingsPage />)
    expect(await screen.findByText('No registered applications are available.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reset to Defaults' }))
    await waitFor(() => expect(mocks.resetSettings).toHaveBeenCalledTimes(1))

    cleanup()
    mocks.getSettings.mockRejectedValueOnce(new Error('Settings service unavailable'))
    render(<SettingsPage />)
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Settings service unavailable')
    expect(screen.getByRole('button', { name: 'Retry loading settings' })).toBeTruthy()
  })

  it('opens the dedicated Settings page from sidebar navigation', async () => {
    mocks.getSettings.mockResolvedValueOnce({ ...settings, workspace_name: 'Release Workspace' })
    render(<App />)
    expect(await screen.findByText('Release Workspace')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Settings/ }))
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeTruthy()
    expect(screen.getByText('Workspace Preferences')).toBeTruthy()
    expect(screen.queryByText('This module is ready for future integration with the backend and product roadmap.')).toBeNull()
  })
})
