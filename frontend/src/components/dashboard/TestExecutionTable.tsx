import { Activity, Clock3, FileX2 } from 'lucide-react'

import EmptyState from '../ui/EmptyState'
import type { ExecutionRecord } from '../../types/navigation'

interface TestExecutionTableProps {
  runs: ExecutionRecord[]
}

const statusStyles: Record<ExecutionRecord['status'], string> = {
  Passed: 'bg-emerald-500/10 text-emerald-300 ring-1 ring-inset ring-emerald-500/20',
  Failed: 'bg-rose-500/10 text-rose-300 ring-1 ring-inset ring-rose-500/20',
  Running: 'bg-sky-500/10 text-sky-300 ring-1 ring-inset ring-sky-500/20',
  Error: 'bg-orange-500/10 text-orange-300 ring-1 ring-inset ring-orange-500/20',
  Completed: 'bg-slate-500/10 text-slate-300 ring-1 ring-inset ring-slate-500/20',
}

export default function TestExecutionTable({ runs }: TestExecutionTableProps) {
  if (!runs.length) {
    return (
      <EmptyState
        icon={Activity}
        title="No test runs yet"
        description="Execute your first validation suite to track pass/fail outcomes, runtime performance, and quality trends."
      />
    )
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-800">
      <div className="overflow-x-auto">
        <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
          <thead className="bg-slate-950/90 text-slate-400">
            <tr>
              <th className="px-4 py-3 font-medium">Run</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Passed</th>
              <th className="px-4 py-3 font-medium">Failed / blocked / error</th>
              <th className="px-4 py-3 font-medium">Duration</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="border-t border-slate-800 bg-slate-900/40 text-slate-200">
                <td className="px-4 py-3">
                  <div>
                    <p className="font-medium text-slate-100">{run.name}</p>
                    <p className="mt-1 text-xs text-slate-500">{run.timestamp}</p>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={[
                      'inline-flex items-center rounded-full px-2 py-1 text-[10px] font-medium uppercase tracking-[0.12em]',
                      statusStyles[run.status],
                    ].join(' ')}
                  >
                    {run.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-300">{run.passed}</td>
                <td className="px-4 py-3 text-slate-300">
                  <span className="inline-flex items-center gap-1">
                    {run.failed > 0 ? <FileX2 className="h-3.5 w-3.5 text-rose-300" /> : null}
                    {run.failed}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-300">
                  <span className="inline-flex items-center gap-1.5">
                    <Clock3 className="h-3.5 w-3.5 text-slate-500" />
                    {run.duration}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
