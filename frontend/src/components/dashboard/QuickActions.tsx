import type { ActionItem } from '../../types/navigation'

interface QuickActionsProps {
  actions: ActionItem[]
  onAction?: (action: ActionItem) => void
}

export default function QuickActions({ actions, onAction }: QuickActionsProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
      {actions.map(({ title, description, icon: Icon, accent }) => {
        return (
          <button
            key={title}
            type="button"
            onClick={() => onAction?.({ title, description, icon: Icon, accent })}
            className={[
              'group rounded-2xl border bg-gradient-to-br p-4 text-left transition duration-200',
              accent,
              'hover:-translate-y-0.5 hover:border-slate-600',
            ].join(' ')}
          >
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-current/30 bg-slate-950/30">
                <Icon className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-base font-semibold text-white">{title}</p>
                <p className="mt-1 text-sm text-slate-300/80">
                  {description}
                </p>
              </div>
            </div>
          </button>
        )
      })}
    </div>
  )
}
