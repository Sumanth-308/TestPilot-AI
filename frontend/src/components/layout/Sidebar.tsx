import { X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { executionApi } from '../../services/executionApi'
import type { NavItem, NavItemId } from '../../types/navigation'

interface SidebarProps {
  items: NavItem[]
  activeItem: NavItemId
  workspaceName: string
  isMobileOpen: boolean
  onSelect: (id: NavItemId) => void
  onClose: () => void
}

export default function Sidebar({
  items,
  activeItem,
  workspaceName,
  isMobileOpen,
  onSelect,
  onClose,
}: SidebarProps) {
  const [backendStatus, setBackendStatus] = useState<'checking' | 'connected' | 'unavailable'>('checking')

  useEffect(() => {
    let active = true
    void executionApi.getBackendHealth()
      .then((health) => {
        if (active) setBackendStatus(health.status === 'healthy' ? 'connected' : 'unavailable')
      })
      .catch(() => {
        if (active) setBackendStatus('unavailable')
      })
    return () => { active = false }
  }, [])

  const statusLabel = {
    checking: 'Checking',
    connected: 'Connected',
    unavailable: 'Unavailable',
  }[backendStatus]

  const statusTone = {
    checking: 'bg-slate-500/10 text-slate-300',
    connected: 'bg-emerald-500/10 text-emerald-300',
    unavailable: 'bg-rose-500/10 text-rose-300',
  }[backendStatus]

  const indicatorTone = {
    checking: 'bg-slate-400',
    connected: 'bg-emerald-400',
    unavailable: 'bg-rose-400',
  }[backendStatus]

  return (
    <>
      {isMobileOpen ? (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={onClose}
          className="fixed inset-0 z-30 bg-slate-950/70 backdrop-blur-sm lg:hidden"
        />
      ) : null}

      <aside
        className={[
          'fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-slate-800 bg-slate-950/95 p-5 shadow-2xl shadow-slate-950/50 backdrop-blur-xl transition-transform duration-300 lg:static lg:translate-x-0',
          isMobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        ].join(' ')}
      >
        <div className="mb-8 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-500/15 text-sm font-semibold text-sky-300 shadow-lg shadow-sky-500/10 ring-1 ring-inset ring-sky-500/25">
              TP
            </div>
            <div>
              <p className="max-w-40 truncate text-base font-semibold text-slate-50" title={workspaceName}>{workspaceName}</p>
              <p className="text-[11px] uppercase tracking-[0.2em] text-slate-400">
                Platform
              </p>
            </div>
          </div>

          <button
            type="button"
            aria-label="Close sidebar"
            onClick={onClose}
            className="rounded-lg border border-slate-700 p-2 text-slate-300 transition hover:border-slate-500 hover:text-slate-50 lg:hidden"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="min-h-0 flex-1 space-y-2 overflow-y-auto">
          {items.map(({ id, label, icon: Icon }) => {
            const isActive = id === activeItem

            return (
              <button
                key={id}
                type="button"
                onClick={() => {
                  onSelect(id)
                  onClose()
                }}
                className={[
                  'flex w-full items-center justify-between rounded-xl border px-3 py-2.5 text-left text-sm font-medium transition-all duration-200',
                  isActive
                    ? 'border-sky-500/40 bg-sky-500/10 text-sky-200 shadow-lg shadow-sky-900/20'
                    : 'border-transparent bg-transparent text-slate-300 hover:border-slate-700 hover:bg-slate-900 hover:text-slate-100',
                ].join(' ')}
              >
                <span className="flex items-center gap-3">
                  <Icon className="h-4 w-4" />
                  {label}
                </span>
                {isActive ? <span className="h-2.5 w-2.5 rounded-full bg-sky-400" /> : null}
              </button>
            )
          })}
        </nav>

        <div className="mt-auto rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
          <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">
            System status
          </p>
          <div className="mt-3 flex items-center justify-between text-sm text-slate-200">
            <span>Backend</span>
            <span className={`inline-flex items-center gap-2 rounded-full px-2 py-1 text-[11px] font-medium ${statusTone}`}>
              <span className={`h-2 w-2 rounded-full ${indicatorTone}`} />
              {statusLabel}
            </span>
          </div>
        </div>
      </aside>
    </>
  )
}
