import type { OverviewMetric } from '../../types/navigation'

interface OverviewCardProps {
  metric: OverviewMetric
}

export default function OverviewCard({ metric }: OverviewCardProps) {
  const Icon = metric.icon

  const toneStyles = {
    neutral: 'bg-slate-950/60 text-slate-200',
    success: 'bg-emerald-500/10 text-emerald-300',
    warning: 'bg-amber-500/10 text-amber-300',
  }

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-lg shadow-slate-950/20 transition duration-200 hover:-translate-y-0.5 hover:border-slate-700 hover:shadow-slate-950/30">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-slate-400">{metric.label}</p>
          <p className="mt-4 text-3xl font-semibold tracking-tight text-white">{metric.value}</p>
        </div>

        <div
          className={[
            'flex h-11 w-11 items-center justify-center rounded-xl border border-slate-700',
            toneStyles[metric.tone ?? 'neutral'],
          ].join(' ')}
        >
          <Icon className="h-5 w-5" />
        </div>
      </div>

      <p className="mt-4 text-sm text-slate-400">{metric.helper}</p>
    </div>
  )
}
