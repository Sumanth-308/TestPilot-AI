import { useEffect, useState } from 'react'

import Sidebar from './components/layout/Sidebar'
import Header from './components/layout/Header'
import DashboardPage from './pages/DashboardPage'
import PlaceholderPage from './pages/PlaceholderPage'
import ProjectsPage from './pages/ProjectsPage'
import ScannerPage from './pages/ScannerPage'
import TestCasesPage from './pages/TestCasesPage'
import TestGeneratorPage from './pages/TestGeneratorPage'
import ExecutionPage from './pages/ExecutionPage'
import BugAnalysisPage from './pages/BugAnalysisPage'
import ReportsPage from './pages/ReportsPage'
import SettingsPage from './pages/SettingsPage'
import { navItems } from './data/dashboard'
import { settingsApi } from './services/settingsApi'
import type { NavItemId } from './types/navigation'

function App() {
  const [activeItem, setActiveItem] = useState<NavItemId>('dashboard')
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false)
  const [inventoryProjectId, setInventoryProjectId] = useState<number | null>(null)
  const [workspaceName, setWorkspaceName] = useState('TestPilot AI')
  const [workspaceSettingsError, setWorkspaceSettingsError] = useState('')

  useEffect(() => {
    let active = true
    void settingsApi.get()
      .then((settings) => {
        if (!active) return
        setWorkspaceName(settings.workspace_name)
        setWorkspaceSettingsError('')
      })
      .catch((error: unknown) => {
        if (active) {
          setWorkspaceSettingsError(error instanceof Error ? error.message : 'Unable to load workspace name.')
        }
      })
    return () => { active = false }
  }, [])

  const handleNavigate = (nextItem: NavItemId) => {
    setActiveItem(nextItem)
    setIsMobileSidebarOpen(false)
  }

  const activeLabel = navItems.find((item) => item.id === activeItem)?.label ?? 'Dashboard'
  const subtitle =
    activeItem === 'dashboard'
      ? 'Welcome back — your quality operations center is ready for the next release.'
      : activeItem === 'projects'
        ? 'Manage application targets, release readiness, and connected testing workflows.'
        : activeItem === 'scanner'
          ? 'Scan one registered web page in a real browser and collect DOM metadata and page-level diagnostics.'
          : activeItem === 'generator'
            ? 'Generate test-case suggestions from a completed application scan.'
            : activeItem === 'test-cases'
              ? 'Browse saved test cases, filter the inventory, and update manual statuses.'
            : activeItem === 'execution'
              ? 'Select saved test cases and run safe, metadata-backed browser assertions.'
              : activeItem === 'bugs'
                ? 'Review evidence-backed failure categories and investigation guidance from recorded execution results.'
                : activeItem === 'reports'
                  ? 'Review saved run history and download project-wise execution data.'
                  : activeItem === 'settings'
                    ? 'Configure workspace defaults, environment targets, execution preferences, and quality gates.'
                    : 'This module is ready for future integration with the backend and product roadmap.'

  const renderPage = () => {
    if (activeItem === 'dashboard') {
      return <DashboardPage onNavigate={handleNavigate} />
    }

    if (activeItem === 'projects') {
      return <ProjectsPage />
    }

    if (activeItem === 'scanner') {
      return <ScannerPage />
    }

    if (activeItem === 'generator') {
      return (
        <TestGeneratorPage
          onOpenSavedTestCases={(projectId) => {
            setInventoryProjectId(projectId)
            handleNavigate('test-cases')
          }}
        />
      )
    }

    if (activeItem === 'test-cases') {
      return <TestCasesPage initialProjectId={inventoryProjectId} />
    }

    if (activeItem === 'execution') {
      return <ExecutionPage />
    }

    if (activeItem === 'bugs') {
      return <BugAnalysisPage />
    }

    if (activeItem === 'reports') {
      return <ReportsPage />
    }

    if (activeItem === 'settings') {
      return <SettingsPage onWorkspaceNameChange={setWorkspaceName} />
    }

    return <PlaceholderPage section={activeItem} />
  }

  return (
    <div className="min-h-screen bg-[#020b16] text-slate-50">
      <div className="flex min-h-screen">
        <Sidebar
          items={navItems}
          activeItem={activeItem}
          workspaceName={workspaceName}
          isMobileOpen={isMobileSidebarOpen}
          onSelect={handleNavigate}
          onClose={() => setIsMobileSidebarOpen(false)}
        />

        <div className="flex min-h-screen flex-1 flex-col">
          <Header
            title={activeLabel}
            subtitle={subtitle}
            onMenuClick={() => setIsMobileSidebarOpen(true)}
          />

          <main className="mx-auto w-full max-w-[1600px] flex-1 p-4 sm:p-6 xl:p-8">
            {workspaceSettingsError && activeItem !== 'settings' ? (
              <div role="alert" className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
                Workspace preferences could not be loaded: {workspaceSettingsError}
              </div>
            ) : null}
            {renderPage()}
          </main>
        </div>
      </div>
    </div>
  )
}

export default App