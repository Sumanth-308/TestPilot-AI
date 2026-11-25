import type { LucideIcon } from 'lucide-react'

export type NavItemId =
  | 'dashboard'
  | 'projects'
  | 'scanner'
  | 'generator'
  | 'test-cases'
  | 'execution'
  | 'bugs'
  | 'reports'
  | 'settings'

export interface NavItem {
  id: NavItemId
  label: string
  icon: LucideIcon
}

export interface OverviewMetric {
  label: string
  value: string
  helper: string
  icon: LucideIcon
  tone?: 'neutral' | 'success' | 'warning'
}

export interface ProjectRecord {
  name: string
  url: string
  createdAt: string
}

export interface ExecutionRecord {
  id: string
  name: string
  status: 'Passed' | 'Failed' | 'Running' | 'Error' | 'Completed'
  passed: number
  failed: number
  duration: string
  timestamp: string
}

export interface ActionItem {
  title: string
  description: string
  icon: LucideIcon
  accent: string
}
