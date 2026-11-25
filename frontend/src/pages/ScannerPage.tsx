import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  ExternalLink,
  Loader2,
  Play,
  Search,
  ShieldAlert,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { projectApi } from '../services/projectApi'
import {
  scannerApi,
  type ScanForm,
  type ScanInputField,
  type ScanRecord,
  type ScanResultJson,
} from '../services/scannerApi'
import type { Application } from '../types/application'

const sectionOrder = [
  { key: 'headings', label: 'Headings' },
  { key: 'buttons', label: 'Buttons' },
  { key: 'links', label: 'Links' },
  { key: 'inputs', label: 'Input Fields' },
  { key: 'forms', label: 'Forms' },
  { key: 'console_errors', label: 'Console Errors' },
  { key: 'page_errors', label: 'JavaScript Errors' },
  { key: 'navigation_failures', label: 'Navigation Failures' },
] as const

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

function formatDate(value: string | null) {
  if (!value) {
    return 'Not available'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Not available'
  }

  return dateFormatter.format(date)
}

function normalizeResult(raw: unknown): ScanResultJson | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }

  const candidate = raw as Partial<ScanResultJson>

  return {
    page_title: typeof candidate.page_title === 'string' ? candidate.page_title : null,
    final_url: typeof candidate.final_url === 'string' ? candidate.final_url : null,
    headings: Array.isArray(candidate.headings)
      ? candidate.headings.filter((item): item is string => typeof item === 'string')
      : [],
    buttons: Array.isArray(candidate.buttons)
      ? candidate.buttons.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      : [],
    links: Array.isArray(candidate.links)
      ? candidate.links.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      : [],
    inputs: Array.isArray(candidate.inputs)
      ? candidate.inputs.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      : [],
    forms: Array.isArray(candidate.forms)
      ? candidate.forms.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      : [],
    console_errors: Array.isArray(candidate.console_errors)
      ? candidate.console_errors.filter((item): item is string => typeof item === 'string')
      : [],
    page_errors: Array.isArray(candidate.page_errors)
      ? candidate.page_errors.filter((item): item is string => typeof item === 'string')
      : [],
    navigation_failures: Array.isArray(candidate.navigation_failures)
      ? candidate.navigation_failures.filter((item): item is string => typeof item === 'string')
      : [],
  }
}

function getSectionItems(result: ScanResultJson | null, key: (typeof sectionOrder)[number]['key']) {
  if (!result) {
    return []
  }

  switch (key) {
    case 'headings':
      return result.headings
    case 'buttons':
      return result.buttons
    case 'links':
      return result.links
    case 'inputs':
      return result.inputs
    case 'forms':
      return result.forms
    case 'console_errors':
      return result.console_errors
    case 'page_errors':
      return result.page_errors
    case 'navigation_failures':
      return result.navigation_failures
    default:
      return []
  }
}

function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'success' | 'danger' | 'warning' }) {  const tones = {
    neutral: 'border-slate-700 bg-slate-800/80 text-slate-200',
    success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    danger: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
    warning: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  }

  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-[0.2em] ${tones[tone]}`}>{children}</span>
}

function DetailSection<T>({
  title,
  items,
  emptyMessage,
  renderItem,
}: {
  title: string
  items: T[]
  emptyMessage: string
  renderItem: (item: T, index: number) => ReactNode
}) {
  return (
    <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/20">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-slate-50">{title}</h3>
        <Badge tone={items.length > 0 ? 'neutral' : 'warning'}>{items.length} found</Badge>
      </div>

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
          {emptyMessage}
        </div>
      ) : (
        <ul className="space-y-3">{items.map((item, index) => <li key={index}>{renderItem(item, index)}</li>)}</ul>
      )}
    </section>
  )
}

export default function ScannerPage() {
  const [projects, setProjects] = useState<Application[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null)
  const [history, setHistory] = useState<ScanRecord[]>([])
  const [activeScan, setActiveScan] = useState<ScanRecord | null>(null)
  const [isLoadingProjects, setIsLoadingProjects] = useState(true)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [isScanning, setIsScanning] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  )

  const activeResult = useMemo(
    () => normalizeResult(activeScan?.result_json ?? null),
    [activeScan],
  )

  const loadProjects = useCallback(async () => {
    setErrorMessage('')
    setIsLoadingProjects(true)

    try {
      const data = await projectApi.listApplications()
      setProjects(data)

      if (data.length > 0 && selectedProjectId === null) {
        setSelectedProjectId(data[0].id)
      }
      if (data.length === 0) {
        setSelectedProjectId(null)
        setHistory([])
        setActiveScan(null)
      }
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to load applications. Please verify the backend is running.',
      )
    } finally {
      setIsLoadingProjects(false)
    }
  }, [selectedProjectId])

  const loadHistory = useCallback(async (projectId: number) => {
    setIsLoadingHistory(true)
    setErrorMessage('')

    try {
      const scans = await scannerApi.listProjectScans(projectId)
      setHistory(scans)

      if (scans.length > 0) {
        setActiveScan(scans[0])
      } else {
        setActiveScan(null)
      }
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to load scan history for this project.',
      )
    } finally {
      setIsLoadingHistory(false)
    }
  }, [])

  useEffect(() => {
    const fetchProjects = async () => {
      await loadProjects()
    }

    void fetchProjects()
  }, [loadProjects])

  useEffect(() => {
    if (selectedProjectId === null) {
      return
    }

    const fetchHistory = async () => {
      await loadHistory(selectedProjectId)
    }

    void fetchHistory()
  }, [loadHistory, selectedProjectId])

  const handleStartScan = async () => {
    if (!selectedProjectId || isScanning) {
      return
    }

    setIsScanning(true)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      const response = await scannerApi.startScan(selectedProjectId)
      setActiveScan(response)
      setSuccessMessage(
        response.status === 'completed'
          ? 'Scan completed successfully.'
          : response.status === 'failed'
            ? 'Scan finished with errors. Review the results below.'
            : 'Scan started successfully.',
      )

      await loadHistory(selectedProjectId)
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'The scan could not be started. Please try again.',
      )
    } finally {
      setIsScanning(false)
    }
  }

  const handleSelectScan = async (scanId: number) => {
    const selected = history.find((scan) => scan.id === scanId)

    if (!selected) {
      return
    }

    setActiveScan(selected)

    try {
      const details = await scannerApi.getScan(scanId)
      setActiveScan(details)
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to load the selected scan details.',
      )
    }
  }

  const statusTone = {
    running: 'warning',
    completed: 'success',
    failed: 'danger',
  } as const

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-sky-300">Web application inspection</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-50">Application Scanner</h2>
        </div>

        <div className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/80 px-3 py-1.5 text-sm text-slate-300">
          <CircleDashed className="h-4 w-4 text-sky-300" />
          Plays in real browser sessions via Playwright
        </div>
      </div>

      {errorMessage ? (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      ) : null}

      {successMessage ? (
        <div className="flex items-start gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-200">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{successMessage}</span>
        </div>
      ) : null}

      <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/20">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div className="space-y-2">
            <label htmlFor="project-select" className="text-xs uppercase tracking-[0.2em] text-slate-400">
              Project
            </label>

            {isLoadingProjects ? (
              <div className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-3 text-sm text-slate-300">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading projects...
              </div>
            ) : projects.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/40 px-4 py-5 text-sm text-slate-400">
                No applications are registered yet. Add a project in the Projects screen before scanning.
              </div>
            ) : (
              <select
                id="project-select"
                value={selectedProjectId ?? ''}
                onChange={(event) => setSelectedProjectId(Number(event.target.value) || null)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-500/60"
              >
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name} — {project.url}
                  </option>
                ))}
              </select>
            )}
          </div>

          <button
            type="button"
            onClick={() => void handleStartScan()}
            disabled={selectedProjectId === null || isScanning || isLoadingProjects || projects.length === 0}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-sky-500 px-4 py-3 text-sm font-medium text-slate-950 shadow-lg shadow-sky-500/20 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
          >
            {isScanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {isScanning ? 'Scanning...' : 'Start Scan'}
          </button>
        </div>
      </section>

      {selectedProject ? (
        <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/20">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Selected application</p>
              <h3 className="mt-2 text-xl font-semibold text-slate-50">{selectedProject.name}</h3>
            </div>

            <a
              href={selectedProject.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 text-sm font-medium text-sky-300 transition hover:text-sky-200"
            >
              {selectedProject.url}
              <ExternalLink className="h-4 w-4" />
            </a>
          </div>
        </section>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.86fr)_minmax(0,1.14fr)]">
        <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/20">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h3 className="text-lg font-semibold text-slate-50">Scan History</h3>
            <Badge tone={history.length > 0 ? 'neutral' : 'warning'}>{history.length} scans</Badge>
          </div>

          {isLoadingHistory ? (
            <div className="flex items-center gap-2 rounded-2xl border border-slate-700 bg-slate-950/60 px-3 py-4 text-sm text-slate-300">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading scan history...
            </div>
          ) : history.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
              No scan history yet for this project.
            </div>
          ) : (
            <div className="space-y-3">
              {history.map((scan) => (
                <button
                  key={scan.id}
                  type="button"
                  onClick={() => void handleSelectScan(scan.id)}
                  className={`w-full rounded-2xl border p-3 text-left transition ${
                    activeScan?.id === scan.id
                      ? 'border-sky-500/40 bg-sky-500/10'
                      : 'border-slate-700 bg-slate-950/40 hover:border-slate-500'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-slate-50">#{scan.id}</span>
                        <Badge tone={statusTone[scan.status]}>{scan.status}</Badge>
                      </div>
                      <p className="mt-2 text-sm text-slate-300">{scan.page_title ?? 'Untitled page'}</p>
                    </div>
                    <Search className="mt-0.5 h-4 w-4 text-slate-400" />
                  </div>
                  <p className="mt-3 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                    {formatDate(scan.started_at)}
                  </p>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/20">
          {activeScan ? (
            <>
              <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Selected scan</p>
                  <h3 className="mt-2 text-2xl font-semibold text-slate-50">#{activeScan.id}</h3>
                </div>

                <Badge tone={statusTone[activeScan.status]}>{activeScan.status}</Badge>
              </div>

              {(activeScan.error_message || (activeScan.status === 'failed' && !activeResult)) ? (
                <div className="mb-5 flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
                  <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{activeScan.error_message ?? 'The scan failed and no data was captured.'}</span>
                </div>
              ) : null}

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-2xl border border-slate-700 bg-slate-950/50 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Website title</p>
                  <p className="mt-3 text-base font-medium text-slate-50">
                    {activeResult?.page_title ?? activeScan.page_title ?? 'Not available'}
                  </p>
                </div>

                <div className="rounded-2xl border border-slate-700 bg-slate-950/50 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Final URL</p>
                  <p className="mt-3 break-all text-base font-medium text-slate-50">
                    {activeResult?.final_url ?? activeScan.final_url ?? 'Not available'}
                  </p>
                </div>

                <div className="rounded-2xl border border-slate-700 bg-slate-950/50 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Started</p>
                  <p className="mt-3 text-sm text-slate-200">{formatDate(activeScan.started_at)}</p>
                </div>

                <div className="rounded-2xl border border-slate-700 bg-slate-950/50 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Completed</p>
                  <p className="mt-3 text-sm text-slate-200">{formatDate(activeScan.completed_at)}</p>
                </div>
              </div>
            </>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/40 p-6 text-sm text-slate-400">
              Select a scan to view results.
            </div>
          )}
        </section>
      </div>

      {activeResult ? (
        <div className="space-y-6">
          {sectionOrder.map(({ key, label }) => {
            const items = getSectionItems(activeResult, key)

            if (key === 'headings') {
              return (
                <DetailSection
                  key={key}
                  title={label}
                  items={items as string[]}
                  emptyMessage="No headings were detected on the page."
                  renderItem={(item) => <p className="rounded-2xl border border-slate-700 bg-slate-950/40 px-3 py-2 text-sm text-slate-100">{item}</p>}
                />
              )
            }

            if (key === 'buttons') {
              return (
                <DetailSection
                  key={key}
                  title={label}
                  items={items as Array<Record<string, unknown>>}
                  emptyMessage="No visible buttons were found."
                  renderItem={(item) => (
                    <div className="rounded-2xl border border-slate-700 bg-slate-950/40 px-3 py-2 text-sm text-slate-100">
                      <p className="font-medium">{String(item.text ?? 'Unnamed button')}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">
                        {String(item.type ?? 'button')} {item.form_id ? `• form ${String(item.form_id)}` : ''}
                      </p>
                    </div>
                  )}
                />
              )
            }

            if (key === 'links') {
              return (
                <DetailSection
                  key={key}
                  title={label}
                  items={items as Array<Record<string, unknown>>}
                  emptyMessage="No visible links were found."
                  renderItem={(item) => (
                    <div className="rounded-2xl border border-slate-700 bg-slate-950/40 px-3 py-2 text-sm text-slate-100">
                      <p className="font-medium text-slate-50">{String(item.text ?? 'Unnamed link')}</p>
                      <p className="mt-1 break-all text-xs text-sky-300">{String(item.href ?? 'No href')}</p>
                    </div>
                  )}
                />
              )
            }

            if (key === 'inputs') {
              return (
                <DetailSection
                  key={key}
                  title={label}
                  items={items as ScanInputField[]}
                  emptyMessage="No visible input fields were detected."
                  renderItem={(item) => (
                    <div className="rounded-2xl border border-slate-700 bg-slate-950/40 px-3 py-2 text-sm text-slate-100">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium">{item.name ?? item.id ?? 'Unnamed field'}</span>
                        <Badge tone={item.required ? 'warning' : 'neutral'}>{item.required ? 'Required' : 'Optional'}</Badge>
                      </div>
                      <p className="mt-2 text-xs uppercase tracking-[0.16em] text-slate-400">
                        {String(item.type ?? 'text')} • {item.placeholder ?? 'No placeholder'}
                      </p>
                    </div>
                  )}
                />
              )
            }

            if (key === 'forms') {
              return (
                <DetailSection
                  key={key}
                  title={label}
                  items={items as ScanForm[]}
                  emptyMessage="No visible forms were found."
                  renderItem={(item) => (
                    <div className="rounded-2xl border border-slate-700 bg-slate-950/40 px-3 py-2 text-sm text-slate-100">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium">{item.id ?? 'Unnamed form'}</span>
                        <Badge tone="neutral">{String(item.method ?? 'get')}</Badge>
                      </div>
                      <p className="mt-2 break-all text-xs text-slate-300">Action: {String(item.action ?? 'No action')}</p>
                      <div className="mt-3 space-y-2">
                        {(item.fields ?? []).map((field, fieldIndex) => (
                          <div key={fieldIndex} className="rounded-xl border border-slate-700 bg-slate-900/70 px-2 py-1.5 text-xs text-slate-300">
                            {field.name ?? field.id ?? 'Unnamed input'} • {field.type ?? 'text'}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                />
              )
            }

            return (
              <DetailSection
                key={key}
                title={label}
                items={items as string[]}
                emptyMessage={
                  key === 'console_errors'
                    ? 'No browser console errors were reported.'
                    : key === 'page_errors'
                      ? 'No JavaScript runtime errors were captured.'
                      : 'No navigation failures were recorded.'
                }
                renderItem={(item) => (
                  <p className="rounded-2xl border border-slate-700 bg-slate-950/40 px-3 py-2 text-sm text-slate-100">{item}</p>
                )}
              />
            )
          })}
        </div>
      ) : (
        <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-950/40 p-6 text-sm text-slate-400">
          {activeScan && activeScan.status === 'failed'
            ? 'The scan failed and did not return usable results.'
            : 'Run a scan to populate page analysis results.'}
        </div>
      )}
    </div>
  )
}
