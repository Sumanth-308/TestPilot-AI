import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  FileCheck2,
  Filter,
  RefreshCcw,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { projectApi } from '../services/projectApi'
import { testCaseApi, type TestCase, type TestCaseCategory, type TestCasePriority, type TestCaseStatus } from '../services/testCaseApi'
import type { Application } from '../types/application'

const categories: TestCaseCategory[] = [
  'Positive',
  'Negative',
  'Boundary',
  'Input Validation',
  'Form Validation',
  'Navigation',
  'Button Interaction',
  'Functional',
]

const priorities: TestCasePriority[] = ['High', 'Medium', 'Low']
const statuses: TestCaseStatus[] = ['Not Executed', 'Passed', 'Failed', 'Blocked']

const statusStyles: Record<TestCaseStatus, string> = {
  'Not Executed': 'border-slate-700 bg-slate-800/80 text-slate-200',
  Passed: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  Failed: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
  Blocked: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
}

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

interface TestCasesPageProps {
  initialProjectId?: number | null
}

function formatDate(value: string | null) {
  if (!value) {
    return 'Unknown'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Unknown'
  }

  return dateFormatter.format(date)
}

function formatJson(value: Record<string, unknown>) {
  return JSON.stringify(value, null, 2)
}

export default function TestCasesPage({ initialProjectId = null }: TestCasesPageProps) {
  const [projects, setProjects] = useState<Application[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null)
  const [testCases, setTestCases] = useState<TestCase[]>([])
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)
  const [categoryFilter, setCategoryFilter] = useState('')
  const [priorityFilter, setPriorityFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [isLoadingProjects, setIsLoadingProjects] = useState(true)
  const [isLoadingCases, setIsLoadingCases] = useState(false)
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  const selectedCase = useMemo(
    () => testCases.find((item) => item.test_case_id === selectedCaseId) ?? null,
    [selectedCaseId, testCases],
  )

  useEffect(() => {
    let active = true
    void projectApi.listApplications()
      .then((data) => {
        if (!active) return
        setProjects(data)
        const selected = data.some((project) => project.id === initialProjectId)
          ? initialProjectId
          : data[0]?.id ?? null
        setSelectedProjectId(selected)
        setIsLoadingCases(selected !== null)
        if (selected === null) {
          setTestCases([])
          setSelectedCaseId(null)
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : 'Unable to load registered projects. Please check the backend connection.',
          )
        }
      })
      .finally(() => {
        if (active) setIsLoadingProjects(false)
      })
    return () => { active = false }
  }, [initialProjectId])

  useEffect(() => {
    if (selectedProjectId === null) {
      return
    }

    let active = true
    void testCaseApi.listProjectTestCases(selectedProjectId, {
      category: categoryFilter || undefined,
      priority: priorityFilter || undefined,
      status: statusFilter || undefined,
    })
      .then((data) => {
        if (!active) return
        setTestCases(data)
        setSelectedCaseId((current) => current && data.some((item) => item.test_case_id === current)
          ? current
          : data[0]?.test_case_id ?? null)
      })
      .catch((error: unknown) => {
        if (active) {
          setTestCases([])
          setSelectedCaseId(null)
          setErrorMessage(error instanceof Error ? error.message : 'Unable to load test cases for this project.')
        }
      })
      .finally(() => {
        if (active) setIsLoadingCases(false)
      })
    return () => { active = false }
  }, [categoryFilter, priorityFilter, selectedProjectId, statusFilter])

  const handleRefresh = async () => {
    if (selectedProjectId === null) {
      return
    }

    setIsLoadingCases(true)
    try {
      const data = await testCaseApi.listProjectTestCases(selectedProjectId, {
        category: categoryFilter || undefined,
        priority: priorityFilter || undefined,
        status: statusFilter || undefined,
      })
      setTestCases(data)
      if (data.length > 0) {
        setSelectedCaseId((current) => current && data.some((item) => item.test_case_id === current) ? current : data[0].test_case_id)
      } else {
        setSelectedCaseId(null)
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to refresh test cases.')
    } finally {
      setIsLoadingCases(false)
    }
  }

  const handleProjectChange = (nextProjectId: number | null) => {
    setSelectedProjectId(nextProjectId)
    setTestCases([])
    setSelectedCaseId(null)
    setIsLoadingCases(nextProjectId !== null)
    setErrorMessage('')
  }

  const handleFilterChange = (filter: 'category' | 'priority' | 'status', value: string) => {
    if (filter === 'category') setCategoryFilter(value)
    if (filter === 'priority') setPriorityFilter(value)
    if (filter === 'status') setStatusFilter(value)
    setIsLoadingCases(true)
    setErrorMessage('')
  }

  const handleStatusUpdate = async (nextStatus: TestCaseStatus) => {
    if (!selectedCase) {
      return
    }

    setIsUpdatingStatus(true)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      const updated = await testCaseApi.updateStatus(selectedCase.test_case_id, nextStatus)
      setTestCases((current) =>
        current.map((item) => (item.test_case_id === updated.test_case_id ? updated : item)),
      )
      setSelectedCaseId(updated.test_case_id)
      setSuccessMessage(`Status updated to ${updated.status}.`)
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : 'The status update was rejected by the backend.',
      )
    } finally {
      setIsUpdatingStatus(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-sky-300">Quality coverage</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-50">Test Cases</h2>
        </div>

        <button
          type="button"
          onClick={() => void handleRefresh()}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-700 bg-slate-900/80 px-3.5 py-2.5 text-sm font-medium text-slate-100 transition hover:border-slate-500 hover:text-white"
          disabled={isLoadingCases}
        >
          <RefreshCcw className={['h-4 w-4', isLoadingCases ? 'animate-spin' : ''].join(' ')} />
          {isLoadingCases ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {errorMessage ? (
        <div role="alert" className="flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      ) : null}

      {successMessage ? (
        <div role="status" className="flex items-start gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-200">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{successMessage}</span>
        </div>
      ) : null}

      <div className="flex flex-col gap-4 rounded-3xl border border-slate-800 bg-slate-900/70 p-4 shadow-xl shadow-slate-950/20 lg:flex-row lg:items-end">
        <div className="flex-1">
          <label htmlFor="test-cases-project" className="mb-2 block text-xs uppercase tracking-[0.2em] text-slate-400">Project</label>
          <select
            id="test-cases-project"
            value={selectedProjectId ?? ''}
            onChange={(event) => handleProjectChange(Number(event.target.value) || null)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-100 outline-none transition focus:border-sky-500"
            disabled={isLoadingProjects || projects.length === 0}
          >
            <option value="">{isLoadingProjects ? 'Loading projects...' : projects.length === 0 ? 'No projects available' : 'Select a project'}</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </div>

        <div className="w-full sm:w-44">
          <label htmlFor="test-cases-category" className="mb-2 block text-xs uppercase tracking-[0.2em] text-slate-400">Category</label>
          <select
            id="test-cases-category"
            value={categoryFilter}
            onChange={(event) => handleFilterChange('category', event.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-100 outline-none transition focus:border-sky-500"
            disabled={!selectedProjectId}
          >
            <option value="">All categories</option>
            {categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </div>

        <div className="w-full sm:w-40">
          <label htmlFor="test-cases-priority" className="mb-2 block text-xs uppercase tracking-[0.2em] text-slate-400">Priority</label>
          <select
            id="test-cases-priority"
            value={priorityFilter}
            onChange={(event) => handleFilterChange('priority', event.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-100 outline-none transition focus:border-sky-500"
            disabled={!selectedProjectId}
          >
            <option value="">All priorities</option>
            {priorities.map((priority) => (
              <option key={priority} value={priority}>
                {priority}
              </option>
            ))}
          </select>
        </div>

        <div className="w-full sm:w-44">
          <label htmlFor="test-cases-status" className="mb-2 block text-xs uppercase tracking-[0.2em] text-slate-400">Status</label>
          <select
            id="test-cases-status"
            value={statusFilter}
            onChange={(event) => handleFilterChange('status', event.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-100 outline-none transition focus:border-sky-500"
            disabled={!selectedProjectId}
          >
            <option value="">All statuses</option>
            {statuses.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.7fr)]">
        <section className="overflow-hidden rounded-3xl border border-slate-800 bg-slate-900/70 shadow-xl shadow-slate-950/20">
          <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950/40 px-5 py-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sky-500/10 text-sky-300 ring-1 ring-inset ring-sky-500/20">
                <FileCheck2 className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-100">Saved test cases</p>
                <p className="text-xs text-slate-400">{selectedProjectId ? 'Project inventory' : 'No project selected'}</p>
              </div>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-200">
              <Filter className="h-3 w-3" />
              {testCases.length}
            </span>
          </div>

          {isLoadingCases ? (
            <div className="flex min-h-[18rem] items-center justify-center gap-3 text-slate-300">
              <CircleDashed className="h-5 w-5 animate-spin" />
              Loading test cases...
            </div>
          ) : selectedProjectId === null || testCases.length === 0 ? (
            <div className="flex min-h-[18rem] flex-col items-center justify-center gap-3 px-6 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-700 bg-slate-950/60 text-slate-400">
                <FileCheck2 className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-slate-100">No test cases available</h3>
                <p className="mt-2 max-w-md text-sm text-slate-400">
                  {selectedProjectId === null
                    ? 'Select a project to review its saved test cases.'
                    : 'There are no generated test cases for the current project and filters.'}
                </p>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-800 text-left text-sm">
                <thead className="bg-slate-950/40 text-slate-300">
                  <tr>
                    <th className="px-4 py-3 font-medium">Test Case ID</th>
                    <th className="px-4 py-3 font-medium">Scenario</th>
                    <th className="px-4 py-3 font-medium">Priority</th>
                    <th className="px-4 py-3 font-medium">Category</th>
                    <th className="px-4 py-3 font-medium">Type</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 bg-slate-900/40 text-slate-100">
                  {testCases.map((item) => (
                    <tr
                      key={item.test_case_id}
                      onClick={() => setSelectedCaseId(item.test_case_id)}
                      className={[
                        'cursor-pointer transition hover:bg-slate-800/70',
                        selectedCaseId === item.test_case_id ? 'bg-sky-500/5' : '',
                      ].join(' ')}
                    >
                      <td className="px-4 py-3 align-top font-mono text-xs text-sky-300">{item.test_case_id}</td>
                      <td className="px-4 py-3 align-top text-slate-100">{item.scenario}</td>
                      <td className="px-4 py-3 align-top">
                        <span className="rounded-full border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-200">
                          {item.priority}
                        </span>
                      </td>
                      <td className="px-4 py-3 align-top text-slate-200">{item.category}</td>
                      <td className="px-4 py-3 align-top text-slate-200">{item.execution_type}</td>
                      <td className="px-4 py-3 align-top">
                        <span className={`rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-[0.2em] ${statusStyles[item.status]}`}>
                          {item.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <aside className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/20">
          {selectedCase ? (
            <div className="space-y-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-sky-300">Selected case</p>
                  <h3 className="mt-2 text-xl font-semibold text-slate-50">{selectedCase.scenario}</h3>
                </div>
                <span className={`rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-[0.2em] ${statusStyles[selectedCase.status]}`}>
                  {selectedCase.status}
                </span>
              </div>

              <div className="space-y-3 rounded-2xl border border-slate-800 bg-slate-950/40 p-3 text-sm">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Priority</p>
                    <p className="mt-1 text-slate-200">{selectedCase.priority}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Category</p>
                    <p className="mt-1 text-slate-200">{selectedCase.category}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Execution</p>
                    <p className="mt-1 text-slate-200">{selectedCase.execution_type}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Updated</p>
                    <p className="mt-1 text-slate-200">{formatDate(selectedCase.updated_at)}</p>
                  </div>
                </div>

                <div>
                  <label htmlFor="test-case-status-update" className="mb-2 block text-[10px] uppercase tracking-[0.2em] text-slate-500">Update status</label>
                  <select
                    id="test-case-status-update"
                    value={selectedCase.status}
                    onChange={(event) => void handleStatusUpdate(event.target.value as TestCaseStatus)}
                    className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-500"
                    disabled={isUpdatingStatus}
                  >
                    {statuses.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="space-y-4 text-sm text-slate-300">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">ID</p>
                  <p className="mt-1 break-all font-mono text-xs text-sky-300">{selectedCase.test_case_id}</p>
                </div>

                <div>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Description</p>
                  <p className="mt-1 leading-6">{selectedCase.description}</p>
                </div>

                <div>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Preconditions</p>
                  <ul className="mt-1 list-disc space-y-1 pl-5 text-slate-200">
                    {selectedCase.preconditions.length > 0 ? (
                      selectedCase.preconditions.map((item) => <li key={item}>{item}</li>)
                    ) : (
                      <li>No preconditions specified.</li>
                    )}
                  </ul>
                </div>

                <div>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Steps</p>
                  <ol className="mt-1 list-decimal space-y-1 pl-5 text-slate-200">
                    {selectedCase.steps.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
                  </ol>
                </div>

                <div>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Test data</p>
                  <pre className="mt-2 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-200">
                    {formatJson(selectedCase.test_data)}
                  </pre>
                </div>

                <div>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Expected result</p>
                  <p className="mt-1 leading-6 text-slate-200">{selectedCase.expected_result}</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex min-h-[20rem] items-center justify-center text-center text-slate-400">
              Select a test case to view full details.
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
