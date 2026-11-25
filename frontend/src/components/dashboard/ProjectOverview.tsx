import { FolderKanban } from 'lucide-react'

import EmptyState from '../ui/EmptyState'
import type { Application } from '../../types/application'

interface ProjectOverviewProps {
  projects: Application[]
}

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
})

const formatDate = (value: string) => {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return 'Unknown date'
  }

  return dateFormatter.format(date)
}

export default function ProjectOverview({ projects }: ProjectOverviewProps) {
  if (!projects.length) {
    return (
      <EmptyState
        icon={FolderKanban}
        title="No projects yet"
        description="Add your first application to start organizing test coverage, automated runs, and quality insights."
      />
    )
  }

  return (
    <div className="space-y-4">
      {projects.map((project) => (
        <div
          key={project.id}
          className="rounded-2xl border border-slate-800 bg-slate-950/40 p-4 transition hover:border-slate-700"
        >
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-base font-semibold text-slate-50">{project.name}</p>
              <p className="mt-2 text-sm text-slate-400">{project.url}</p>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-slate-400">
            <span className="inline-flex items-center rounded-full border border-slate-800 bg-slate-900 px-2.5 py-1">
              Created {formatDate(project.created_at)}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
