import { AlertCircle, BarChart3, CircleDashed, Clock3, Download } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { executionApi } from '../services/executionApi'
import { projectApi } from '../services/projectApi'
import type { Application } from '../types/application'
import type { ExecutionReport } from '../types/execution'

function formatDate(value: string | null) {
  if (!value) return 'In progress'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Unknown date' : date.toLocaleString()
}

function formatDuration(value: number) {
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(2)} s`
}

export default function ReportsPage() {
  const [projects, setProjects] = useState<Application[]>([])
  const [projectId, setProjectId] = useState<number | null>(null)
  const [report, setReport] = useState<ExecutionReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    let active = true
    void projectApi.listApplications()
      .then((items) => {
        if (active) setProjects(items)
      })
      .catch((error: unknown) => {
        if (active) setErrorMessage(error instanceof Error ? error.message : 'Unable to load projects.')
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    void executionApi.getReports(projectId ?? undefined)
      .then((data) => {
        if (active) setReport(data)
      })
      .catch((error: unknown) => {
        if (active) setErrorMessage(error instanceof Error ? error.message : 'Unable to load execution reports.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [projectId])

  const totals = useMemo(() => (report?.runs ?? []).reduce(
    (value, run) => ({
      runs: value.runs + 1,
      tests: value.tests + run.total_tests,
      passed: value.passed + run.passed,
      failed: value.failed + run.failed,
      blocked: value.blocked + run.blocked,
      errors: value.errors + run.errors,
      notAutomatable: value.notAutomatable + run.not_automatable,
    }),
    { runs: 0, tests: 0, passed: 0, failed: 0, blocked: 0, errors: 0, notAutomatable: 0 },
  ), [report])

  const handleDownload = async () => {
    setDownloading(true)
    setErrorMessage('')
    try {
      const blob = await executionApi.downloadCsv(projectId ?? undefined)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'testpilot-execution-report.csv'
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to download the report.')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-sky-300">Saved execution data</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-50">Reports</h2>
        </div>
        <button
          type="button"
          onClick={() => void handleDownload()}
          disabled={downloading || loading}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-2.5 text-sm font-medium text-sky-200 transition hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {downloading ? <CircleDashed className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          {downloading ? 'Preparing CSV...' : 'Download CSV'}
        </button>
      </div>

      {errorMessage ? (
        <div role="alert" className="flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /><span>{errorMessage}</span>
        </div>
      ) : null}

      <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
        <label htmlFor="reports-project" className="mb-2 block text-xs uppercase tracking-[0.2em] text-slate-400">Project</label>
        <select
          id="reports-project"
          value={projectId ?? ''}
          onChange={(event) => {
            setProjectId(Number(event.target.value) || null)
            setLoading(true)
            setErrorMessage('')
          }}
          className="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-3 text-sm text-slate-100 outline-none focus:border-sky-500"
        >
          <option value="">All projects</option>
          {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
      </section>

      {loading ? (
        <div className="flex min-h-44 items-center justify-center gap-2 text-sm text-slate-300"><CircleDashed className="h-4 w-4 animate-spin" /> Loading reports...</div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            {[
              { label: 'Runs', value: totals.runs, color: 'text-slate-100' },
              { label: 'Tests in runs', value: totals.tests, color: 'text-slate-100' },
              { label: 'Passed', value: totals.passed, color: 'text-emerald-300' },
              { label: 'Failed', value: totals.failed, color: 'text-rose-200' },
              { label: 'Blocked / Error', value: totals.blocked + totals.errors, color: 'text-amber-200' },
              { label: 'Not Automatable', value: totals.notAutomatable, color: 'text-slate-300' },
            ].map((item) => (
              <div key={item.label} className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                <p className="text-xs uppercase tracking-[0.14em] text-slate-500">{item.label}</p>
                <p className={`mt-2 text-2xl font-semibold ${item.color}`}>{item.value}</p>
              </div>
            ))}
          </div>

          <section className="overflow-hidden rounded-3xl border border-slate-800 bg-slate-900/70">
            <div className="flex items-center gap-3 border-b border-slate-800 px-5 py-4">
              <BarChart3 className="h-4 w-4 text-sky-300" />
              <div>
                <h3 className="font-semibold text-slate-100">Execution history</h3>
                <p className="mt-1 text-xs text-slate-400">Duration, outcomes, and failure categories from saved runs</p>
              </div>
            </div>
            {(report?.runs.length ?? 0) === 0 ? (
              <p className="p-8 text-center text-sm text-slate-400">No execution runs have been recorded yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-950/50 text-xs uppercase tracking-[0.12em] text-slate-400">
                    <tr>
                      <th className="px-4 py-3 font-medium">Run / Project</th>
                      <th className="px-4 py-3 font-medium">Started</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 font-medium">Passed / Total</th>
                      <th className="px-4 py-3 font-medium">Fail / Block / Error</th>
                      <th className="px-4 py-3 font-medium">Duration</th>
                      <th className="px-4 py-3 font-medium">Failure summaries</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {report?.runs.map((run) => (
                      <tr key={run.id} className="bg-slate-900/30 align-top text-slate-200">
                        <td className="px-4 py-3"><span className="font-medium">#{run.id}</span><span className="mt-1 block text-xs text-slate-500">{run.project_name}</span></td>
                        <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">{formatDate(run.started_at)}</td>
                        <td className="px-4 py-3 text-xs capitalize">{run.status}</td>
                        <td className="px-4 py-3">{run.passed} / {run.total_tests}</td>
                        <td className="px-4 py-3">{run.failed} / {run.blocked} / {run.errors}</td>
                        <td className="whitespace-nowrap px-4 py-3"><span className="inline-flex items-center gap-1.5"><Clock3 className="h-3.5 w-3.5 text-slate-500" />{formatDuration(run.duration_ms)}</span></td>
                        <td className="max-w-64 px-4 py-3 text-xs text-slate-400">{run.failure_summaries?.join(', ') || 'None'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="overflow-hidden rounded-3xl border border-slate-800 bg-slate-900/70">
            <div className="border-b border-slate-800 px-5 py-4">
              <h3 className="font-semibold text-slate-100">Project-wise results</h3>
              <p className="mt-1 text-xs text-slate-400">Aggregated from recorded execution runs</p>
            </div>
            {(report?.projects.length ?? 0) === 0 ? (
              <p className="p-8 text-center text-sm text-slate-400">No registered projects are available.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-950/50 text-xs uppercase tracking-[0.12em] text-slate-400">
                    <tr>
                      <th className="px-4 py-3 font-medium">Project</th>
                      <th className="px-4 py-3 font-medium">Test cases</th>
                      <th className="px-4 py-3 font-medium">Runs</th>
                      <th className="px-4 py-3 font-medium">Passed</th>
                      <th className="px-4 py-3 font-medium">Failed</th>
                      <th className="px-4 py-3 font-medium">Blocked</th>
                      <th className="px-4 py-3 font-medium">Errors</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {report?.projects.map((project) => (
                      <tr key={project.project_id} className="bg-slate-900/30 text-slate-200">
                        <td className="px-4 py-3 font-medium">{project.project_name}</td>
                        <td className="px-4 py-3">{project.total_test_cases}</td>
                        <td className="px-4 py-3">{project.total_runs}</td>
                        <td className="px-4 py-3 text-emerald-300">{project.passed}</td>
                        <td className="px-4 py-3 text-rose-200">{project.failed}</td>
                        <td className="px-4 py-3 text-amber-200">{project.blocked}</td>
                        <td className="px-4 py-3 text-orange-200">{project.errors}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
