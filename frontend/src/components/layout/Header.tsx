import { Bell, Menu, Search } from 'lucide-react'

interface HeaderProps {
  title: string
  subtitle: string
  onMenuClick: () => void
}

export default function Header({ title, subtitle, onMenuClick }: HeaderProps) {
  return (
    <header className="border-b border-slate-800 bg-slate-950/70 px-4 py-4 backdrop-blur-xl sm:px-6 xl:px-8">
      <div className="mx-auto flex max-w-[1600px] items-center gap-4">
        <button
          type="button"
          onClick={onMenuClick}
          className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-700 bg-slate-900 text-slate-200 transition hover:border-slate-500 hover:text-slate-50 lg:hidden"
          aria-label="Open navigation"
        >
          <Menu className="h-4 w-4" />
        </button>

        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h1 className="text-xl font-semibold text-white sm:text-2xl">{title}</h1>
          <p className="text-sm text-slate-400">{subtitle}</p>
        </div>

        <div className="hidden items-center gap-3 md:flex">
          <label className="flex w-[320px] items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-400 transition focus-within:border-sky-500/80 focus-within:ring-1 focus-within:ring-sky-500/30">
            <Search className="h-4 w-4" />
            <input
              type="text"
              placeholder="Search projects, suites, issues..."
              className="w-full border-0 bg-transparent text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
            />
          </label>

          <button
            type="button"
            aria-label="Notifications"
            className="relative inline-flex h-11 w-11 items-center justify-center rounded-xl border border-slate-700 bg-slate-900 text-slate-200 transition hover:border-slate-500 hover:text-slate-50"
          >
            <Bell className="h-4 w-4" />
            <span className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full bg-sky-400 ring-2 ring-slate-900" />
          </button>
        </div>
      </div>
    </header>
  )
}
