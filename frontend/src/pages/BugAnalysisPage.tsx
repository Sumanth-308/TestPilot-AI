import { AlertCircle, Bug, CircleDashed, ListChecks } from 'lucide-react'
import { useEffect, useState } from 'react'

import { executionApi } from '../services/executionApi'
import { projectApi } from '../services/projectApi'
import type { Application } from '../types/application'
import type { BugFinding } from '../types/execution'

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Unknown date' : date.toLocaleString()
}

export default function BugAnalysisPage() {
  const [projects, setProjects] = useState<Application[]>([])
  const [projectId, setProjectId] = useState<number | null>(null)
  const [findings, setFindings] = useState<BugFinding[]>([])
  const [loadingProjects, setLoadingProjects] = useState(true)
  const [loading, setLoading] = useState(true)
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
      .finally(() => {
        if (active) setLoadingProjects(false)
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    void executionApi.listBugs(projectId ?? undefined)
      .then((items) => {
        if (active) setFindings(items)
      })
      .catch((error: unknown) => {
        if (active) setErrorMessage(error instanceof Error ? error.message : 'Unable to load execution findings.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [projectId])

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.24em] text-sky-300">Evidence-based diagnostics</p>
        <h2 className="mt-2 text-3xl font-semibold text-slate-50">Bug Analysis</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
          Failure categories and diagnostics come from saved browser execution results. Likely causes are hypotheses, not confirmed root causes.
        </p>
      </div>

      {errorMessage ? (
        <div role="alert" className="flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /><span>{errorMessage}</span>
        </div>
      ) : null}

      <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
        <label htmlFor="bug-project" className="mb-2 block text-xs uppercase tracking-[0.2em] text-slate-400">Project</label>
        <select
          id="bug-project"
          value={projectId ?? ''}
          onChange={(event) => {
            setProjectId(Number(event.target.value) || null)
            setLoading(true)
            setErrorMessage('')
          }}
          disabled={loadingProjects}
          className="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-3 text-sm text-slate-100 outline-none focus:border-sky-500"
        >
          <option value="">All projects</option>
          {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
      </section>

      {loading ? (
        <div className="flex min-h-44 items-center justify-center gap-2 text-sm text-slate-300"><CircleDashed className="h-4 w-4 animate-spin" /> Loading execution findings...</div>
      ) : findings.length === 0 ? (
        <div className="flex min-h-56 flex-col items-center justify-center rounded-3xl border border-dashed border-slate-700 bg-slate-900/40 p-8 text-center">
          <Bug className="h-8 w-8 text-slate-500" />
          <h3 className="mt-4 text-lg font-semibold text-slate-200">No recorded failures</h3>
          <p className="mt-2 max-w-lg text-sm text-slate-400">Failed, blocked, or errored execution results will appear here after a real browser run.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {findings.map((finding) => (
            <article key={finding.id} className="space-y-4 rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-rose-500/30 bg-rose-500/10 px-2.5 py-1 text-[10px] uppercase tracking-[0.16em] text-rose-200">{finding.failure_category}</span>
                    <span className="text-xs text-slate-500">{finding.project_name} · Run #{finding.execution_run_id}</span>
                  </div>
                  <h3 className="mt-3 text-lg font-semibold text-slate-100">{finding.scenario}</h3>
                  <p className="mt-1 text-sm text-slate-400">{formatDate(finding.run_started_at)} · {finding.test_case_id}</p>
                </div>
                <span className="rounded-full border border-slate-700 px-2.5 py-1 text-[10px] uppercase tracking-[0.14em] text-slate-300">{finding.execution_status}</span>
              </div>

              <div className="grid gap-3 lg:grid-cols-2">
                <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                  <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Error summary</p>
                  <p className="mt-2 text-sm text-slate-200">{finding.error_summary}</p>
                  <p className="mt-3 text-xs leading-5 text-slate-400">{finding.diagnostic_details}</p>
                </div>
                <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4">
                  <p className="text-xs uppercase tracking-[0.16em] text-amber-300">Likely cause (unconfirmed)</p>
                  <p className="mt-2 text-sm leading-6 text-amber-100/90">{finding.likely_cause}</p>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
                <p className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-slate-400"><ListChecks className="h-3.5 w-3.5" /> Suggested investigation</p>
                <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-300">
                  {finding.suggested_investigation_steps.map((step) => <li key={step}>{step}</li>)}
                </ul>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
