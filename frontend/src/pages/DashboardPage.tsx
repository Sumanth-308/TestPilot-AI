import { ArrowRight, FolderKanban, Gauge, PlayCircle, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'

import AnalyticsPanel from '../components/dashboard/AnalyticsPanel'
import ProjectOverview from '../components/dashboard/ProjectOverview'
import QuickActions from '../components/dashboard/QuickActions'
import TestExecutionTable from '../components/dashboard/TestExecutionTable'
import OverviewCard from '../components/ui/OverviewCard'
import SectionCard from '../components/ui/SectionCard'
import { quickActions } from '../data/dashboard'
import { executionApi } from '../services/executionApi'
import { projectApi } from '../services/projectApi'
import type { Application } from '../types/application'
import type { DashboardSummary } from '../types/execution'
import type { NavItemId, OverviewMetric } from '../types/navigation'

interface DashboardPageProps {
  onNavigate?: (item: NavItemId) => void
}

export default function DashboardPage({ onNavigate }: DashboardPageProps) {
  const [applications, setApplications] = useState<Application[]>([])
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    const loadApplications = async () => {
      setErrorMessage('')
      setIsLoading(true)

      try {
        const [projectData, dashboardData] = await Promise.all([
          projectApi.listApplications(),
          executionApi.getDashboardSummary(),
        ])
        setApplications(projectData)
        setSummary(dashboardData)
      } catch (error) {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : 'Unable to load applications right now. Please try again.',
        )
      } finally {
        setIsLoading(false)
      }
    }

    void loadApplications()
  }, [])

  const recentExecutions = (summary?.recent_runs ?? []).map((run) => ({
    id: String(run.id),
    name: `Run #${run.id}`,
    status: run.status === 'running'
      ? 'Running' as const
      : run.status === 'error'
        ? 'Error' as const
        : run.failed + run.blocked + run.errors > 0
          ? 'Failed' as const
          : run.not_automatable > 0
            ? 'Completed' as const
            : 'Passed' as const,
    passed: run.passed,
    failed: run.failed + run.blocked + run.errors,
    duration: run.duration_ms < 1000 ? `${run.duration_ms} ms` : `${(run.duration_ms / 1000).toFixed(2)} s`,
    timestamp: new Date(run.started_at).toLocaleString(),
  }))

  const metrics: OverviewMetric[] = [
    {
      label: 'Total Projects',
      value: isLoading ? '...' : errorMessage ? '—' : String(summary?.project_count ?? applications.length),
      helper: isLoading
        ? 'Loading registered applications...'
        : errorMessage
          ? 'Unable to load applications.'
          : (summary?.project_count ?? applications.length) === 0
            ? 'No application targets created yet'
            : `${summary?.project_count ?? applications.length} application target${(summary?.project_count ?? applications.length) === 1 ? '' : 's'} registered`,
      icon: FolderKanban,
      tone: 'neutral',
    },
    {
      label: 'Total Test Cases',
      value: isLoading ? '...' : errorMessage ? '—' : String(summary?.test_case_count ?? 0),
      helper: errorMessage ? 'Unable to load test-case totals.' : summary?.test_case_count ? 'Saved test cases across registered projects' : 'No saved test cases yet',
      icon: Sparkles,
      tone: 'neutral',
    },
    {
      label: 'Tests Executed',
      value: isLoading ? '...' : errorMessage ? '—' : String(summary?.tests_executed ?? 0),
      helper: errorMessage ? 'Unable to load execution totals.' : summary?.tests_executed ? `${summary.passed} passed · ${summary.failed + summary.blocked + summary.errors} failed, blocked, or errored` : 'No browser execution results recorded',
      icon: PlayCircle,
      tone: 'neutral',
    },
    {
      label: 'Pass Rate',
      value: errorMessage || summary?.pass_rate === null || summary?.pass_rate === undefined ? '—' : `${summary.pass_rate}%`,
      helper: errorMessage ? 'Unable to load execution results.' : summary?.tests_executed ? 'Based on saved browser assertions' : 'Awaiting real execution results',
      icon: Gauge,
      tone: !errorMessage && summary?.pass_rate !== null && summary?.pass_rate !== undefined ? 'success' : 'warning',
    },
  ]

  return (
    <div className="space-y-6">
      {errorMessage ? (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <span>{errorMessage}</span>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric) => (
          <OverviewCard key={metric.label} metric={metric} />
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.5fr_0.9fr]">
        <SectionCard
          title="Project overview"
          description="Track the applications currently registered in TestPilot AI."
          action={
            <button
              type="button"
              onClick={() => onNavigate?.('projects')}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-950/50 px-3 py-2 text-sm text-slate-200 transition hover:border-slate-500 hover:text-slate-50"
            >
              View all
              <ArrowRight className="h-4 w-4" />
            </button>
          }
        >
          <ProjectOverview projects={applications} />
        </SectionCard>

        <SectionCard
          title="Quick actions"
          description="Launch the next quality workflow."
        >
          <QuickActions
            actions={quickActions}
            onAction={(action) => {
              const destinations: Record<string, NavItemId> = {
                'Add New Project': 'projects',
                'Scan Application': 'scanner',
                'Generate Test Cases': 'generator',
                'Execute Tests': 'execution',
              }
              const destination = destinations[action.title]
              if (destination) onNavigate?.(destination)
            }}
          />
        </SectionCard>
      </div>

      <div className="grid gap-6 2xl:grid-cols-[1.5fr_1fr]">
        <SectionCard
          title="Test execution activity"
          description="Latest run outcomes and execution metrics."
          action={
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-emerald-300">
              <Sparkles className="h-3 w-3" />
              {summary?.recent_runs.length ?? 0} recent runs
            </div>
          }
        >
          <TestExecutionTable runs={recentExecutions} />
        </SectionCard>

        <SectionCard
          title="Testing analytics"
          description="Operational health for execution and quality trends."
        >
          {summary ? (
            <AnalyticsPanel
              runCount={summary.total_runs}
              passed={summary.passed}
              failed={summary.failed}
              blocked={summary.blocked}
              errors={summary.errors}
            />
          ) : <p className="text-sm text-slate-400">{errorMessage ? 'Analytics are unavailable until the backend can be reached.' : 'Loading execution data...'}</p>}
        </SectionCard>
      </div>
    </div>
  )
}
