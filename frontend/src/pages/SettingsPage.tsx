import { AlertCircle, CheckCircle2, RotateCcw, Save, Settings2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'

import { projectApi } from '../services/projectApi'
import { settingsApi } from '../services/settingsApi'
import type { Application } from '../types/application'
import type {
  EnvironmentName,
  EnvironmentUrlMap,
  WorkspaceSettings,
  WorkspaceSettingsUpdate,
} from '../types/settings'

const environments: { id: EnvironmentName; label: string; description: string }[] = [
  { id: 'development', label: 'Development', description: 'Local or developer testing' },
  { id: 'staging', label: 'Staging', description: 'Pre-release verification' },
  { id: 'production', label: 'Production', description: 'Live application checks' },
]

function editableSettings(settings: WorkspaceSettings): WorkspaceSettingsUpdate {
  return {
    workspace_name: settings.workspace_name,
    default_environment: settings.default_environment,
    default_project_id: settings.default_project_id,
    environment_urls: settings.environment_urls,
    execution_timeout_ms: settings.execution_timeout_ms,
    max_tests_per_run: settings.max_tests_per_run,
    quality_gate_pass_rate_threshold: settings.quality_gate_pass_rate_threshold,
    quality_gate_failure_threshold: settings.quality_gate_failure_threshold,
  }
}

function SectionCard({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/20">
      <div className="mb-5">
        <h3 className="text-lg font-semibold text-slate-100">{title}</h3>
        <p className="mt-1 text-sm leading-6 text-slate-400">{description}</p>
      </div>
      {children}
    </section>
  )
}

const fieldClass = 'mt-2 w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-sky-500 disabled:opacity-60'
const labelClass = 'block text-sm font-medium text-slate-200'

interface SettingsPageProps {
  onWorkspaceNameChange?: (workspaceName: string) => void
}

export default function SettingsPage({ onWorkspaceNameChange }: SettingsPageProps) {
  const [projects, setProjects] = useState<Application[]>([])
  const [savedSettings, setSavedSettings] = useState<WorkspaceSettings | null>(null)
  const [draft, setDraft] = useState<WorkspaceSettingsUpdate | null>(null)
  const [environmentProjectId, setEnvironmentProjectId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  const loadSettings = async () => {
    setLoading(true)
    setErrorMessage('')
    try {
      const [settings, applications] = await Promise.all([
        settingsApi.get(),
        projectApi.listApplications(),
      ])
      setSavedSettings(settings)
      setDraft(editableSettings(settings))
      onWorkspaceNameChange?.(settings.workspace_name)
      setProjects(applications)
      const preferredProject = settings.default_project_id
      setEnvironmentProjectId(
        preferredProject !== null && applications.some((project) => project.id === preferredProject)
          ? preferredProject
          : applications[0]?.id ?? null,
      )
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to load workspace settings.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const [settings, applications] = await Promise.all([
          settingsApi.get(),
          projectApi.listApplications(),
        ])
        if (!active) return
        setSavedSettings(settings)
        setDraft(editableSettings(settings))
        onWorkspaceNameChange?.(settings.workspace_name)
        setProjects(applications)
        const preferredProject = settings.default_project_id
        setEnvironmentProjectId(
          preferredProject !== null && applications.some((project) => project.id === preferredProject)
            ? preferredProject
            : applications[0]?.id ?? null,
        )
      } catch (error) {
        if (active) setErrorMessage(error instanceof Error ? error.message : 'Unable to load workspace settings.')
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => { active = false }
  }, [onWorkspaceNameChange])

  const updateDraft = <K extends keyof WorkspaceSettingsUpdate>(
    key: K,
    value: WorkspaceSettingsUpdate[K],
  ) => {
    setDraft((current) => current ? { ...current, [key]: value } : current)
    setSuccessMessage('')
  }

  const updateEnvironmentUrl = (environment: EnvironmentName, value: string) => {
    if (environmentProjectId === null || !draft) return
    const urls: EnvironmentUrlMap = {
      ...draft.environment_urls[environmentProjectId],
      [environment]: value,
    }
    if (!value.trim()) delete urls[environment]
    const environmentUrls = { ...draft.environment_urls }
    if (Object.keys(urls).length) environmentUrls[environmentProjectId] = urls
    else delete environmentUrls[environmentProjectId]
    updateDraft('environment_urls', environmentUrls)
  }

  const handleSave = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!draft || saving) return
    setSaving(true)
    setErrorMessage('')
    setSuccessMessage('')
    try {
      const settings = await settingsApi.update(draft)
      setSavedSettings(settings)
      setDraft(editableSettings(settings))
      onWorkspaceNameChange?.(settings.workspace_name)
      setSuccessMessage('Settings saved. Scanner and execution workflows will use the configured preferences.')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to save workspace settings.')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    if (resetting) return
    setResetting(true)
    setErrorMessage('')
    setSuccessMessage('')
    try {
      const settings = await settingsApi.reset()
      setSavedSettings(settings)
      setDraft(editableSettings(settings))
      onWorkspaceNameChange?.(settings.workspace_name)
      setEnvironmentProjectId(projects[0]?.id ?? null)
      setSuccessMessage('Settings reset to defaults.')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to reset workspace settings.')
    } finally {
      setResetting(false)
    }
  }

  const selectedProject = projects.find((project) => project.id === environmentProjectId)
  const environmentUrls = environmentProjectId === null
    ? {}
    : draft?.environment_urls[environmentProjectId] ?? {}

  if (loading) {
    return (
      <div role="status" className="rounded-3xl border border-slate-800 bg-slate-900/70 p-8 text-sm text-slate-400">
        Loading workspace settings...
      </div>
    )
  }

  if (!draft || !savedSettings) {
    return (
      <div className="space-y-4">
        {errorMessage ? <div role="alert" className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">{errorMessage}</div> : null}
        <button type="button" onClick={() => void loadSettings()} className="rounded-xl border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800">Retry loading settings</button>
      </div>
    )
  }

  return (
    <form onSubmit={(event) => void handleSave(event)} className="space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-sky-300">Workspace configuration</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-50">Settings</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Configure shared defaults for application scanning, browser execution, and quality checks.</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => void handleReset()} disabled={resetting || saving} className="inline-flex items-center gap-2 rounded-xl border border-slate-700 px-4 py-2.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50">
            <RotateCcw className="h-4 w-4" />{resetting ? 'Resetting...' : 'Reset to Defaults'}
          </button>
          <button type="submit" disabled={saving || resetting} className="inline-flex items-center gap-2 rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50">
            <Save className="h-4 w-4" />{saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </header>

      {errorMessage ? <div role="alert" className="flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />{errorMessage}</div> : null}
      {successMessage ? <div role="status" className="flex items-start gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-200"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />{successMessage}</div> : null}

      <SectionCard title="Workspace Preferences" description="Set the workspace identity and default application context used when opening test workflows.">
        <div className="grid gap-5 md:grid-cols-2">
          <label className={labelClass} htmlFor="settings-workspace-name">
            Workspace name
            <input id="settings-workspace-name" required minLength={1} maxLength={80} value={draft.workspace_name} onChange={(event) => updateDraft('workspace_name', event.target.value)} className={fieldClass} />
          </label>
          <label className={labelClass} htmlFor="settings-default-project">
            Default application
            <select id="settings-default-project" value={draft.default_project_id ?? ''} onChange={(event) => updateDraft('default_project_id', event.target.value ? Number(event.target.value) : null)} className={fieldClass}>
              <option value="">No default application</option>
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
            <span className="mt-1 block text-xs font-normal text-slate-500">Prefills the project selector in Test Execution.</span>
          </label>
          <label className={labelClass} htmlFor="settings-active-environment">
            Default environment
            <select id="settings-active-environment" value={draft.default_environment} onChange={(event) => updateDraft('default_environment', event.target.value as EnvironmentName)} className={fieldClass}>
              {environments.map((environment) => <option key={environment.id} value={environment.id}>{environment.label}</option>)}
            </select>
            <span className="mt-1 block text-xs font-normal text-slate-500">This environment is active for new scans and browser execution runs.</span>
          </label>
          <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
            <Settings2 className="h-5 w-5 shrink-0 text-sky-300" />
            <p className="text-sm leading-6 text-slate-400">Execution preferences are applied by the backend, including the browser timeout and maximum tests per run.</p>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Environment Controls" description="Optionally set a safe application URL for each environment. Unconfigured environments use the registered application URL. URLs containing credentials, query strings, or fragments are not accepted.">
        <div className="mb-5 grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <label className={labelClass} htmlFor="settings-environment-project">
            Application URL configuration
            <select id="settings-environment-project" value={environmentProjectId ?? ''} onChange={(event) => setEnvironmentProjectId(Number(event.target.value) || null)} disabled={projects.length === 0} className={fieldClass}>
              {projects.length === 0 ? <option value="">Register an application first</option> : null}
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </label>
          <div className="flex items-center rounded-xl border border-slate-800 bg-slate-950/40 px-4 py-3 text-sm text-slate-400">
            {selectedProject ? <>Registered URL fallback: <span className="ml-1 truncate font-mono text-slate-300">{selectedProject.url}</span></> : 'No registered applications are available.'}
          </div>
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          {environments.map((environment) => {
            const isActive = draft.default_environment === environment.id
            const isConfigured = Boolean(environmentUrls[environment.id]?.trim())
            return (
              <div key={environment.id} className={`rounded-2xl border p-4 ${isActive ? 'border-sky-500/40 bg-sky-500/5' : 'border-slate-800 bg-slate-950/30'}`}>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-medium text-slate-100">{environment.label}</p>
                    <p className="text-xs text-slate-500">{environment.description}</p>
                  </div>
                  <div className="flex gap-1.5">
                    {isActive ? <span className="rounded-full bg-sky-500/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-sky-200">Active</span> : null}
                    <span className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-wide ${isConfigured ? 'bg-emerald-500/10 text-emerald-200' : 'bg-slate-800 text-slate-400'}`}>{isConfigured ? 'Configured' : 'Fallback'}</span>
                  </div>
                </div>
                <label className={labelClass} htmlFor={`settings-url-${environment.id}`}>Application URL</label>
                <input id={`settings-url-${environment.id}`} type="url" inputMode="url" placeholder={selectedProject?.url ?? 'https://example.com'} value={environmentUrls[environment.id] ?? ''} onChange={(event) => updateEnvironmentUrl(environment.id, event.target.value)} disabled={environmentProjectId === null} className={fieldClass} />
              </div>
            )
          })}
        </div>
      </SectionCard>

      <SectionCard title="Quality Workflow Configuration" description="These limits are enforced during execution and stored with every run's quality-gate evaluation.">
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <label className={labelClass} htmlFor="settings-timeout">
            Default execution timeout (ms)
            <input id="settings-timeout" type="number" min={250} max={60000} step={250} required value={draft.execution_timeout_ms} onChange={(event) => updateDraft('execution_timeout_ms', Number(event.target.value))} className={fieldClass} />
            <span className="mt-1 block text-xs font-normal text-slate-500">Applied to page navigation and browser assertions.</span>
          </label>
          <label className={labelClass} htmlFor="settings-max-tests">
            Maximum tests per run
            <input id="settings-max-tests" type="number" min={1} max={100} step={1} required value={draft.max_tests_per_run} onChange={(event) => updateDraft('max_tests_per_run', Number(event.target.value))} className={fieldClass} />
            <span className="mt-1 block text-xs font-normal text-slate-500">Runs above this limit are rejected.</span>
          </label>
          <label className={labelClass} htmlFor="settings-pass-threshold">
            Minimum pass rate (%)
            <input id="settings-pass-threshold" type="number" min={0} max={100} step={1} required value={draft.quality_gate_pass_rate_threshold} onChange={(event) => updateDraft('quality_gate_pass_rate_threshold', Number(event.target.value))} className={fieldClass} />
            <span className="mt-1 block text-xs font-normal text-slate-500">Minimum passing share of executed assertions.</span>
          </label>
          <label className={labelClass} htmlFor="settings-failure-threshold">
            Maximum failed or errored tests
            <input id="settings-failure-threshold" type="number" min={0} max={1000} step={1} required value={draft.quality_gate_failure_threshold} onChange={(event) => updateDraft('quality_gate_failure_threshold', Number(event.target.value))} className={fieldClass} />
            <span className="mt-1 block text-xs font-normal text-slate-500">Runs exceeding this count fail the quality gate.</span>
          </label>
        </div>
      </SectionCard>

      <div className="flex justify-end gap-2 border-t border-slate-800 pt-4">
        <button type="button" onClick={() => savedSettings && setDraft(editableSettings(savedSettings))} disabled={saving || resetting} className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50">Discard Changes</button>
        <button type="submit" disabled={saving || resetting} className="inline-flex items-center gap-2 rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50"><Save className="h-4 w-4" />{saving ? 'Saving...' : 'Save Changes'}</button>
      </div>
    </form>
  )
}
