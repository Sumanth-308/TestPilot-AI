import { ArrowRight, Sparkles } from 'lucide-react'

import type { NavItemId } from '../types/navigation'

const copyMap: Record<NavItemId, { heading: string; body: string; badge: string }> = {
  dashboard: {
    heading: 'Dashboard',
    body: 'A high-level view of your product health, execution status, and release readiness.',
    badge: 'Overview',
  },
  projects: {
    heading: 'Projects',
    body: 'Organize application targets, ownership, and release loops across your testing portfolio.',
    badge: 'Portfolio',
  },
  scanner: {
    heading: 'Application Scanner',
    body: 'Inspect one registered page and collect its available DOM metadata and page-level diagnostics.',
    badge: 'Discovery',
  },
  generator: {
    heading: 'Test Generator',
    body: 'Create deterministic test-case suggestions from metadata in a completed scan.',
    badge: 'Automation',
  },
  'test-cases': {
    heading: 'Test Cases',
    body: 'Review saved test case inventory, update execution status, and keep the project quality record current.',
    badge: 'Coverage',
  },
  execution: {
    heading: 'Test Execution',
    body: 'Coordinate validation runs, monitor queue health, and keep release gate checks visible.',
    badge: 'Operations',
  },
  bugs: {
    heading: 'Bug Analysis',
    body: 'Review failing paths, root-cause signals, and quality trends as issues are surfaced.',
    badge: 'Diagnostics',
  },
  reports: {
    heading: 'Reports',
    body: 'Consolidate pass rates, issue summaries, and test coverage views into a portfolio snapshot.',
    badge: 'Insights',
  },
  settings: {
    heading: 'Settings',
    body: 'Manage workspace preferences, environment controls, and quality workflow configuration.',
    badge: 'Configuration',
  },
}

interface PlaceholderPageProps {
  section: NavItemId
}

export default function PlaceholderPage({ section }: PlaceholderPageProps) {
  const config = copyMap[section]

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="w-full max-w-2xl rounded-3xl border border-slate-800 bg-slate-900/70 p-8 text-center shadow-2xl shadow-slate-950/40">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-sky-500/30 bg-sky-500/10 text-sky-300">
          <Sparkles className="h-7 w-7" />
        </div>

        <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-950/60 px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-slate-300">
          {config.badge}
        </div>

        <h2 className="mt-6 text-3xl font-semibold text-white">{config.heading}</h2>
        <p className="mt-4 text-base leading-7 text-slate-400">{config.body}</p>

        <button
          type="button"
          className="mt-8 inline-flex items-center gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-2.5 text-sm font-medium text-sky-200 transition hover:border-sky-500/50 hover:bg-sky-500/20"
        >
          Prepare this module
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
