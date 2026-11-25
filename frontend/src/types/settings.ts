export type EnvironmentName = 'development' | 'staging' | 'production'

export type EnvironmentUrlMap = Partial<Record<EnvironmentName, string>>

export interface WorkspaceSettings {
  workspace_name: string
  default_environment: EnvironmentName
  default_project_id: number | null
  environment_urls: Record<number, EnvironmentUrlMap>
  configured_environments: Record<number, EnvironmentName[]>
  execution_timeout_ms: number
  max_tests_per_run: number
  quality_gate_pass_rate_threshold: number
  quality_gate_failure_threshold: number
  updated_at: string
}

export type WorkspaceSettingsUpdate = Omit<
  WorkspaceSettings,
  'configured_environments' | 'updated_at'
>
