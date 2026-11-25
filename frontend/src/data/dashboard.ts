import {
  BarChart3,
  Bug,
  FileCheck2,
  FolderKanban,
  Gauge,
  LayoutDashboard,
  PlayCircle,
  Plus,
  ScanSearch,
  Settings,
  Sparkles,
} from 'lucide-react'

import type {
  ActionItem,
  ExecutionRecord,
  NavItem,
  OverviewMetric,
  ProjectRecord,
} from '../types/navigation'

export const navItems: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'projects', label: 'Projects', icon: FolderKanban },
  { id: 'scanner', label: 'Application Scanner', icon: ScanSearch },
  { id: 'generator', label: 'Test Generator', icon: Sparkles },
  { id: 'test-cases', label: 'Test Cases', icon: FileCheck2 },
  { id: 'execution', label: 'Test Execution', icon: PlayCircle },
  { id: 'bugs', label: 'Bug Analysis', icon: Bug },
  { id: 'reports', label: 'Reports', icon: BarChart3 },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export const overviewMetrics: OverviewMetric[] = [
  {
    label: 'Total Projects',
    value: '0',
    helper: 'No application targets created yet',
    icon: FolderKanban,
    tone: 'neutral',
  },
  {
    label: 'Total Test Cases',
    value: '0',
    helper: 'Saved test-case inventory is empty',
    icon: FileCheck2,
    tone: 'neutral',
  },
  {
    label: 'Tests Executed',
    value: '0',
    helper: 'No executions recorded yet',
    icon: PlayCircle,
    tone: 'neutral',
  },
  {
    label: 'Pass Rate',
    value: '—',
    helper: 'Awaiting execution data',
    icon: Gauge,
    tone: 'warning',
  },
]

export const projectRecords: ProjectRecord[] = []

export const recentExecutions: ExecutionRecord[] = []

export const quickActions: ActionItem[] = [
  {
    title: 'Add New Project',
    description: 'Create a new application target',
    icon: Plus,
    accent: 'from-sky-500/20 to-sky-500/5 text-sky-300 border-sky-500/30',
  },
  {
    title: 'Scan Application',
    description: 'Inspect one registered page and its available elements',
    icon: ScanSearch,
    accent: 'from-violet-500/20 to-violet-500/5 text-violet-300 border-violet-500/30',
  },
  {
    title: 'Generate Test Cases',
    description: 'Create deterministic test cases from scan metadata',
    icon: Sparkles,
    accent: 'from-emerald-500/20 to-emerald-500/5 text-emerald-300 border-emerald-500/30',
  },
  {
    title: 'Execute Tests',
    description: 'Run a focused validation suite',
    icon: PlayCircle,
    accent: 'from-amber-500/20 to-amber-500/5 text-amber-300 border-amber-500/30',
  },
]
