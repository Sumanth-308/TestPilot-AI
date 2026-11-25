import { BarChart3, CircleDashed } from 'lucide-react'

interface AnalyticsPanelProps {
  runCount: number
  passed: number
  failed: number
  blocked: number
  errors: number
}

export default function AnalyticsPanel({ runCount, passed, failed, blocked, errors }: AnalyticsPanelProps) {
  const totalFailures = failed + blocked + errors

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-slate-200">Execution insights</p>
            <p className="mt-1 text-xs text-slate-500">{runCount} saved run{runCount === 1 ? '' : 's'}</p>
          </div>
          <BarChart3 className="h-4 w-4 text-slate-400" />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-xl bg-slate-900/70 p-3">
            <p className="text-xs text-slate-500">Passed</p>
            <p className="mt-1 font-semibold text-emerald-300">{passed}</p>
          </div>
          <div className="rounded-xl bg-slate-900/70 p-3">
            <p className="text-xs text-slate-500">Failed / blocked / error</p>
            <p className="mt-1 font-semibold text-rose-200">{totalFailures}</p>
          </div>
        </div>
        <p className="mt-2 text-xs leading-6 text-slate-500">
          Counts include saved browser execution results across all runs.
        </p>
      </div>

      <div className="flex items-center gap-2 rounded-2xl border border-dashed border-slate-700 bg-slate-950/20 px-4 py-3 text-sm text-slate-400">
        <CircleDashed className="h-4 w-4 text-slate-500" />
        {runCount ? `${blocked} blocked · ${errors} errors recorded.` : 'No execution data has been recorded yet.'}
      </div>
    </div>
  )
}
