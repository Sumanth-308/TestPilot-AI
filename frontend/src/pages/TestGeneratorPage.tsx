import { AlertCircle, ArrowRight, CircleDashed, FileCheck2, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'

import { projectApi } from '../services/projectApi'
import { scannerApi, type ScanRecord } from '../services/scannerApi'
import { testCaseApi, type TestCaseGenerationResponse } from '../services/testCaseApi'
import type { Application } from '../types/application'

interface TestGeneratorPageProps {
  onOpenSavedTestCases: (projectId: number) => void
}

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Unknown date' : dateFormatter.format(date)
}

export default function TestGeneratorPage({ onOpenSavedTestCases }: TestGeneratorPageProps) {
  const [projects, setProjects] = useState<Application[]>([])
  const [projectId, setProjectId] = useState<number | null>(null)
  const [completedScans, setCompletedScans] = useState<ScanRecord[]>([])
  const [scanId, setScanId] = useState<number | null>(null)
  const [generation, setGeneration] = useState<TestCaseGenerationResponse | null>(null)
  const [isLoadingProjects, setIsLoadingProjects] = useState(true)
  const [isLoadingScans, setIsLoadingScans] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    let active = true
    void projectApi.listApplications()
      .then((items) => {
        if (!active) return
        setProjects(items)
        setProjectId(items[0]?.id ?? null)
        setIsLoadingScans(items.length > 0)
      })
      .catch((error: unknown) => {
        if (active) setErrorMessage(error instanceof Error ? error.message : 'Unable to load registered projects.')
      })
      .finally(() => {
        if (active) setIsLoadingProjects(false)
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (projectId === null) {
      return
    }
    let active = true
    void scannerApi.listProjectScans(projectId)
      .then((scans) => {
        if (!active) return
        const completed = scans.filter((scan) => scan.status === 'completed')
        setCompletedScans(completed)
        setScanId(completed[0]?.id ?? null)
      })
      .catch((error: unknown) => {
        if (active) {
          setCompletedScans([])
          setScanId(null)
          setErrorMessage(error instanceof Error ? error.message : 'Unable to load completed scans.')
        }
      })
      .finally(() => {
        if (active) setIsLoadingScans(false)
      })
    return () => { active = false }
  }, [projectId])

  const handleGenerate = async () => {
    if (projectId === null || scanId === null || isGenerating) return
    setIsGenerating(true)
    setErrorMessage('')
    setGeneration(null)
    try {
      setGeneration(await testCaseApi.generateFromScan(projectId, scanId))
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Test case generation failed.')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleProjectChange = (nextProjectId: number | null) => {
    setProjectId(nextProjectId)
    setCompletedScans([])
    setScanId(null)
    setIsLoadingScans(nextProjectId !== null)
    setGeneration(null)
    setErrorMessage('')
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-[0.24em] text-emerald-300">Scanner-backed generation</p>
        <h2 className="mt-2 text-3xl font-semibold text-slate-50">Test Generator</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
          Generate deterministic test-case suggestions from a completed project scan, then review what was newly saved and what already existed.
        </p>
      </header>

      {errorMessage ? (
        <div role="alert" className="flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      ) : null}

      <section className="grid gap-4 rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/20 md:grid-cols-2">
        <div>
          <label htmlFor="generator-project" className="mb-2 block text-xs uppercase tracking-[0.2em] text-slate-400">Project</label>
          <select
            id="generator-project"
            value={projectId ?? ''}
            onChange={(event) => handleProjectChange(Number(event.target.value) || null)}
            disabled={isLoadingProjects || isGenerating}
            className="w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-500 disabled:opacity-60"
          >
            <option value="">
              {isLoadingProjects
                ? 'Loading projects...'
                : projects.length === 0
                  ? 'No projects available'
                  : 'Select a project'}
            </option>
            {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </div>

        <div>
          <label htmlFor="generator-scan" className="mb-2 block text-xs uppercase tracking-[0.2em] text-slate-400">Completed scan</label>
          <select
            id="generator-scan"
            value={scanId ?? ''}
            onChange={(event) => {
              setScanId(Number(event.target.value) || null)
              setGeneration(null)
              setErrorMessage('')
            }}
            disabled={projectId === null || isLoadingScans || isGenerating || completedScans.length === 0}
            className="w-full rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-3 text-sm text-slate-100 outline-none transition focus:border-sky-500 disabled:opacity-60"
          >
            <option value="">
              {isLoadingScans
                ? 'Loading scans...'
                : completedScans.length
                  ? 'Select a completed scan'
                  : 'No completed scans available'}
            </option>
            {completedScans.map((scan) => (
              <option key={scan.id} value={scan.id}>
                Scan #{scan.id} · {scan.page_title || scan.final_url || 'Untitled page'} · {formatDate(scan.started_at)}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-3 md:col-span-2 md:flex-row md:items-center md:justify-between">
          <p className="text-xs leading-5 text-slate-400">Only completed scans belonging to the selected project are available.</p>
          <button
            type="button"
            onClick={() => void handleGenerate()}
            disabled={isGenerating || isLoadingProjects || isLoadingScans || projectId === null || scanId === null}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
          >
            {isGenerating ? <CircleDashed className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {isGenerating ? 'Generating test cases...' : 'Generate Test Cases'}
          </button>
        </div>
      </section>

      {isLoadingScans ? (
        <div role="status" className="flex min-h-36 items-center justify-center gap-2 rounded-2xl border border-slate-800 bg-slate-900/50 text-sm text-slate-300">
          <CircleDashed className="h-4 w-4 animate-spin" /> Loading completed scans...
        </div>
      ) : !isLoadingProjects && projects.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
          Register an application in Projects before generating test cases.
        </div>
      ) : projectId !== null && completedScans.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 p-6 text-center text-sm text-slate-400">
          This project has no completed scans yet. Scan the application before generating test cases.
        </div>
      ) : null}

      {generation ? (
        <section className="space-y-5 rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-sky-300">Generation result</p>
              <h3 className="mt-2 text-xl font-semibold text-slate-50">Saved test-case preview</h3>
              <p className="mt-1 text-xs text-slate-400">
                Project {generation.summary.project_id} · Scan {generation.summary.scan_id}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onOpenSavedTestCases(generation.summary.project_id)}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 px-3.5 py-2.5 text-sm font-medium text-sky-200 transition hover:bg-sky-500/20"
            >
              <FileCheck2 className="h-4 w-4" /> Open saved Test Cases <ArrowRight className="h-4 w-4" />
            </button>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {[
              { label: 'Generated', value: generation.summary.generated_count },
              { label: 'Saved', value: generation.summary.saved_count },
              { label: 'Newly inserted', value: generation.summary.inserted_count },
              { label: 'Existing duplicates', value: generation.summary.duplicate_count },
              { label: 'Project / Scan', value: `${generation.summary.project_id} / ${generation.summary.scan_id}` },
            ].map((item) => (
              <div key={item.label} className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">{item.label}</p>
                <p className="mt-2 text-xl font-semibold text-slate-100">{item.value}</p>
              </div>
            ))}
          </div>

          {generation.summary.notes?.length ? (
            <ul className="list-disc space-y-1 pl-5 text-xs text-slate-400">
              {generation.summary.notes.map((note) => <li key={note}>{note}</li>)}
            </ul>
          ) : null}

          {generation.test_cases.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-slate-700 p-6 text-center text-sm text-slate-400">
              The selected scan did not produce any test cases.
            </p>
          ) : (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-slate-200">Generated test cases</h4>
              {generation.test_cases.map((testCase) => (
                <article key={testCase.test_case_id} className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <p className="break-all font-mono text-xs text-sky-300">{testCase.test_case_id}</p>
                      <h5 className="mt-2 text-sm font-medium text-slate-100">{testCase.scenario}</h5>
                      <p className="mt-1 text-xs leading-5 text-slate-400">{testCase.description}</p>
                    </div>
                    <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-[0.14em] ${
                      testCase.persistence_status === 'inserted'
                        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                        : 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                    }`}>
                      {testCase.persistence_status === 'inserted' ? 'Newly saved' : 'Already existed'}
                    </span>
                  </div>
                  <p className="mt-3 text-xs text-slate-400">
                    {testCase.category} · {testCase.priority} priority · Expected: {testCase.expected_result}
                  </p>
                </article>
              ))}
            </div>
          )}
        </section>
      ) : null}
    </div>
  )
}
