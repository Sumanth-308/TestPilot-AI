import { AlertCircle, CheckCircle2, CircleDashed, Clock3, Play, RefreshCcw } from 'lucide-react'
import { useEffect, useState } from 'react'

import { executionApi } from '../services/executionApi'
import { projectApi } from '../services/projectApi'
import { settingsApi } from '../services/settingsApi'
import type { Application } from '../types/application'
import type {
  ExecutionCandidate,
  ExecutionDetail,
  ExecutionResult,
  ExecutionRun,
  ExecutionStatus,
} from '../types/execution'
import type { EnvironmentName } from '../types/settings'

const statusStyles: Record<ExecutionStatus, string> = {
  Passed: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  Failed: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
  Blocked: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  Error: 'border-orange-500/30 bg-orange-500/10 text-orange-200',
  'Not Automatable': 'border-slate-600 bg-slate-800/80 text-slate-300',
}

function formatDate(value: string | null) {
  if (!value) return 'In progress'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Unknown date' : date.toLocaleString()
}

function formatDuration(value: number) {
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(2)} s`
}

function StatusBadge({ status }: { status: ExecutionStatus }) {
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.16em] ${statusStyles[status]}`}>
      {status}
    </span>
  )
}

function CountCard({ label, value, tone = 'text-slate-100' }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
      <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${tone}`}>{value}</p>
    </div>
  )
}

function ResultDetail({ result }: { result: ExecutionResult }) {
  return (
    <div className="space-y-4 rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs text-sky-300">{result.test_case_id}</p>
          <p className="mt-1 text-sm text-slate-300">{result.assertion_performed ?? result.action_performed}</p>
        </div>
        <StatusBadge status={result.execution_status} />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Expected</p>
          <p className="mt-2 whitespace-pre-wrap text-sm text-slate-200">{result.expected_result ?? 'No expected result saved.'}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
          <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Actual</p>
          <p className="mt-2 whitespace-pre-wrap text-sm text-slate-200">{result.actual_result ?? result.error_message ?? 'No browser assertion was performed.'}</p>
        </div>
      </div>
      {result.failure_details ? (
        <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 text-sm text-rose-100">
          <p className="font-medium">{result.failure_details.category ?? 'Execution diagnostic'}</p>
          {result.failure_details.details ? <p className="mt-1 text-rose-200/80">{result.failure_details.details}</p> : null}
        </div>
      ) : null}
      <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1.5"><Clock3 className="h-3.5 w-3.5" />{formatDuration(result.duration_ms)}</span>
        <span>Started {formatDate(result.started_at)}</span>
      </div>
    </div>
  )
}

export default function ExecutionPage() {
  const [projects, setProjects] = useState<Application[]>([])
  const [defaultEnvironment, setDefaultEnvironment] = useState<EnvironmentName>('development')
  const [maxTestsPerRun, setMaxTestsPerRun] = useState(100)
  const [projectId, setProjectId] = useState<number | null>(null)
  const [candidates, setCandidates] = useState<ExecutionCandidate[]>([])
  const [history, setHistory] = useState<ExecutionRun[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [activeRun, setActiveRun] = useState<ExecutionDetail | null>(null)
  const [loadingProjects, setLoadingProjects] = useState(true)
  const [loadingProjectData, setLoadingProjectData] = useState(true)
  const [running, setRunning] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    let active = true
    void Promise.all([projectApi.listApplications(), settingsApi.get()])
      .then(([items, settings]) => {
        if (!active) return
        setProjects(items)
        setProjectId(
          settings.default_project_id !== null && items.some((item) => item.id === settings.default_project_id)
            ? settings.default_project_id
            : items[0]?.id ?? null,
        )
        setDefaultEnvironment(settings.default_environment)
        setMaxTestsPerRun(settings.max_tests_per_run)
        if (items.length === 0) setLoadingProjectData(false)
      })
      .catch((error: unknown) => {
        if (active) {
          setErrorMessage(error instanceof Error ? error.message : 'Unable to load projects.')
          setLoadingProjectData(false)
        }
      })
      .finally(() => {
        if (active) setLoadingProjects(false)
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (projectId === null) return

    let active = true
    void Promise.all([executionApi.listCandidates(projectId), executionApi.listRuns(projectId)])
      .then(([items, runs]) => {
        if (!active) return
        setCandidates(items)
        setHistory(runs)
        setSelectedIds(new Set(items.filter((item) => item.automatable).slice(0, maxTestsPerRun).map((item) => item.test_case_id)))
        setActiveRun(null)
      })
      .catch((error: unknown) => {
        if (active) setErrorMessage(error instanceof Error ? error.message : 'Unable to load execution data.')
      })
      .finally(() => {
        if (active) setLoadingProjectData(false)
      })
    return () => { active = false }
  }, [projectId, maxTestsPerRun])

  const toggleCase = (testCaseId: string) => {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(testCaseId)) next.delete(testCaseId)
      else if (next.size < maxTestsPerRun) next.add(testCaseId)
      return next
    })
  }

  const handleProjectChange = (nextProjectId: number | null) => {
    setProjectId(nextProjectId)
    setLoadingProjectData(nextProjectId !== null)
    setErrorMessage('')
    setCandidates([])
    setHistory([])
    setSelectedIds(new Set())
    setActiveRun(null)
  }

  const handleRun = async () => {
    if (projectId === null || selectedIds.size === 0 || running) return
    setRunning(true)
    setErrorMessage('')
    setActiveRun(null)
    try {
      const run = await executionApi.startRun(projectId, Array.from(selectedIds))
      setActiveRun(run)
      const updatedHistory = await executionApi.listRuns(projectId)
      setHistory(updatedHistory)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'The execution run could not be completed.')
    } finally {
      setRunning(false)
    }
  }

  const openRun = async (runId: number) => {
    setErrorMessage('')
    try {
      setActiveRun(await executionApi.getRun(runId))
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to load execution details.')
    }
  }

  const summary = activeRun
    ? [
        { label: 'Passed', value: activeRun.passed, tone: 'text-emerald-300' },
        { label: 'Failed', value: activeRun.failed, tone: 'text-rose-200' },
        { label: 'Blocked', value: activeRun.blocked, tone: 'text-amber-200' },
        { label: 'Error', value: activeRun.errors, tone: 'text-orange-200' },
        { label: 'Not Automatable', value: activeRun.not_automatable, tone: 'text-slate-300' },
      ]
    : []

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-sky-300">Browser-based validation</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-50">Test Execution</h2>
        </div>
        <button
          type="button"
          onClick={() => void handleRun()}
          disabled={running || loadingProjectData || projectId === null || selectedIds.size === 0}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-sky-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
        >
          {running ? <CircleDashed className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running ? `Running ${selectedIds.size} selected tests...` : `Run Tests (${selectedIds.size})`}
        </button>
      </div>

      {errorMessage ? (
        <div role="alert" className="flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      ) : null}

      <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
        <label htmlFor="execution-project" className="mb-2 block text-xs uppercase tracking-[0.2em] text-slate-400">Project</label>
        <select
          id="execution-project"
          value={projectId ?? ''}
          onChange={(event) => handleProjectChange(Number(event.target.value) || null)}
          disabled={loadingProjects || projects.length === 0 || running}
          className="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-3 text-sm text-slate-100 outline-none focus:border-sky-500"
        >
          <option value="">{loadingProjects ? 'Loading projects...' : 'No projects available'}</option>
          {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
        <p className="mt-3 text-xs text-slate-400">
          Active environment: <span className="font-medium capitalize text-sky-200">{defaultEnvironment}</span>
          <span className="mx-2 text-slate-600">·</span>
          Maximum {maxTestsPerRun} tests per run. These preferences are enforced by the execution API.
        </p>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.65fr)]">
        <section className="overflow-hidden rounded-3xl border border-slate-800 bg-slate-900/70">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">
            <div>
              <h3 className="font-semibold text-slate-100">Available test cases</h3>
              <p className="mt-1 text-xs text-slate-400">Only verified scanner locators are used. Unsupported behavior is never guessed.</p>
            </div>
            <button
              type="button"
              onClick={() => setSelectedIds(new Set(candidates.filter((item) => item.automatable).slice(0, maxTestsPerRun).map((item) => item.test_case_id)))}
              disabled={running || candidates.length === 0}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:border-slate-500 disabled:opacity-50"
            >
              <RefreshCcw className="h-3.5 w-3.5" /> Select automatable
            </button>
          </div>
          {loadingProjects || loadingProjectData ? (
            <div className="flex min-h-48 items-center justify-center gap-2 text-sm text-slate-300"><CircleDashed className="h-4 w-4 animate-spin" /> Loading test cases...</div>
          ) : candidates.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-400">
              {projectId === null ? 'Register a project and generate test cases to begin.' : 'No saved test cases are available for this project.'}
            </div>
          ) : (
            <div className="divide-y divide-slate-800">
              {candidates.map((candidate) => (
                <label key={candidate.test_case_id} className="flex cursor-pointer gap-3 p-4 transition hover:bg-slate-800/40">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(candidate.test_case_id)}
                    onChange={() => toggleCase(candidate.test_case_id)}
                    disabled={running || (!selectedIds.has(candidate.test_case_id) && selectedIds.size >= maxTestsPerRun)}
                    className="mt-1 h-4 w-4 accent-sky-400"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs text-sky-300">{candidate.test_case_id}</span>
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] ${
                        candidate.automatable
                          ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                          : 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                      }`}>{candidate.eligibility}</span>
                    </span>
                    <span className="mt-2 block text-sm font-medium text-slate-100">{candidate.scenario}</span>
                    <span className="mt-1 block text-xs text-slate-400">{candidate.reason ?? candidate.assertion ?? candidate.description}</span>
                  </span>
                </label>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-slate-100">Execution history</h3>
              <p className="mt-1 text-xs text-slate-400">Recorded runs for the selected project</p>
            </div>
            <span className="rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-300">{history.length}</span>
          </div>
          {history.length === 0 ? (
            <p className="rounded-xl border border-dashed border-slate-700 p-4 text-sm text-slate-400">No saved execution runs yet.</p>
          ) : (
            <div className="space-y-2">
              {history.map((run) => (
                <button
                  type="button"
                  key={run.id}
                  onClick={() => void openRun(run.id)}
                  className={`w-full rounded-xl border p-3 text-left transition ${
                    activeRun?.id === run.id ? 'border-sky-500/40 bg-sky-500/10' : 'border-slate-800 bg-slate-950/40 hover:border-slate-600'
                  }`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-medium text-slate-100">Run #{run.id}</span>
                    <span className="text-xs text-slate-400">{run.status}</span>
                  </span>
                  <span className="mt-2 flex justify-between text-xs text-slate-500">
                    <span>{formatDate(run.started_at)}</span>
                    <span>{run.passed}/{run.total_tests} passed</span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>

      {running ? (
        <div role="status" className="flex items-center gap-3 rounded-2xl border border-sky-500/20 bg-sky-500/5 p-4 text-sm text-sky-100">
          <CircleDashed className="h-4 w-4 animate-spin" /> Browser run in progress. Each assertion is checked against the live page state.
        </div>
      ) : null}

      {activeRun ? (
        <section className="space-y-5 rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-sky-300">Run #{activeRun.id}</p>
              <h3 className="mt-2 text-xl font-semibold text-slate-50">Execution summary</h3>
              <p className="mt-1 text-sm text-slate-400">{formatDate(activeRun.started_at)} · {formatDuration(activeRun.duration_ms)}</p>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300">
              <CheckCircle2 className="h-3.5 w-3.5 text-sky-300" /> {activeRun.total_tests} selected
            </span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {summary.map((item) => <CountCard key={item.label} {...item} />)}
          </div>
          <div className={`rounded-2xl border p-4 ${activeRun.quality_gate_passed === true ? 'border-emerald-500/30 bg-emerald-500/5' : activeRun.quality_gate_passed === false ? 'border-rose-500/30 bg-rose-500/5' : 'border-slate-700 bg-slate-950/40'}`}>
            <p className="text-sm font-semibold text-slate-100">
              Quality gate: {activeRun.quality_gate_passed === null ? 'Not evaluated' : activeRun.quality_gate_passed ? 'Passed' : 'Failed'}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              {activeRun.quality_gate_pass_rate === null
                ? 'No executable assertions were available for the pass-rate calculation.'
                : `${activeRun.quality_gate_pass_rate.toFixed(1)}% pass rate · threshold ${activeRun.quality_gate_pass_rate_threshold ?? '—'}% · maximum ${activeRun.quality_gate_failure_threshold ?? '—'} failures/errors`}
            </p>
          </div>
          {activeRun.results.length === 0 ? (
            <p className="text-sm text-slate-400">Detailed results are not available for this run.</p>
          ) : (
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(300px,0.8fr)]">
              <div className="space-y-2">
                {activeRun.results.map((result) => {
                  const candidate = candidates.find((item) => item.test_case_id === result.test_case_id)
                  return (
                    <div key={result.id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/40 p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-slate-200">{candidate?.scenario ?? result.test_case_id}</p>
                        <p className="mt-1 font-mono text-[10px] text-slate-500">{result.test_case_id} · {formatDuration(result.duration_ms)}</p>
                      </div>
                      <StatusBadge status={result.execution_status} />
                    </div>
                  )
                })}
              </div>
              <div className="space-y-3">
                {activeRun.results.map((result) => <ResultDetail key={result.id} result={result} />)}
              </div>
            </div>
          )}
        </section>
      ) : null}
    </div>
  )
}
