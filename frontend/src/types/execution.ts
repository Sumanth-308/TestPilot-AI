import type { TestCase } from '../services/testCaseApi'

export type ExecutionStatus = 'Passed' | 'Failed' | 'Blocked' | 'Error' | 'Not Automatable'
export type AutomationEligibility =
  | 'Automatable'
  | 'Not Automatable'
  | 'Ambiguous locator'
  | 'Locator metadata missing'

export interface ExecutionCandidate extends TestCase {
  automatable: boolean
  eligibility: AutomationEligibility
  reason: string | null
  action: string
  assertion?: string
}

export interface FailureAnalysis {
  failure_category: string
  error_summary: string
  diagnostic_details: string
  likely_cause: string
  suggested_investigation_steps: string[]
}

export interface ExecutionResult {
  id: number
  execution_run_id: number
  test_case_id: string
  execution_status: ExecutionStatus
  action_performed: string
  assertion_performed: string | null
  expected_result: string | null
  actual_result: string | null
  error_message: string | null
  failure_details: { category?: string; details?: string } | null
  duration_ms: number
  screenshot_path: string | null
  started_at: string
  completed_at: string
  analysis: FailureAnalysis | null
}

export interface ExecutionRun {
  id: number
  project_id: number
  project_name: string | null
  scan_id: number | null
  status: 'running' | 'completed' | 'error'
  total_tests: number
  passed: number
  failed: number
  blocked: number
  errors: number
  not_automatable: number
  environment: 'development' | 'staging' | 'production'
  quality_gate_passed: boolean | null
  quality_gate_pass_rate: number | null
  quality_gate_pass_rate_threshold: number | null
  quality_gate_failure_threshold: number | null
  started_at: string
  completed_at: string | null
  duration_ms: number
  failure_summaries?: string[]
}

export interface ExecutionDetail extends ExecutionRun {
  results: ExecutionResult[]
}

export interface DashboardSummary {
  project_count: number
  test_case_count: number
  total_runs: number
  tests_executed: number
  pass_rate: number | null
  passed: number
  failed: number
  blocked: number
  errors: number
  recent_runs: ExecutionRun[]
}

export interface ProjectReport {
  project_id: number
  project_name: string
  total_test_cases: number
  total_runs: number
  passed: number
  failed: number
  blocked: number
  errors: number
  not_automatable: number
}

export interface ExecutionReport {
  projects: ProjectReport[]
  runs: ExecutionRun[]
}

export interface BugFinding extends ExecutionResult {
  project_id: number
  project_name: string
  scenario: string
  run_started_at: string
  failure_category: string
  error_summary: string
  diagnostic_details: string
  likely_cause: string
  suggested_investigation_steps: string[]
}
