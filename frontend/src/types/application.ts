export interface Application {
  id: number
  name: string
  url: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface ApplicationCreate {
  name: string
  url: string
  description?: string | null
}

export interface ApplicationUpdate {
  name?: string
  url?: string
  description?: string | null
}
