import {
  AlertCircle,
  BriefcaseBusiness,
  CheckCircle2,
  ExternalLink,
  Loader2,
  PencilLine,
  Plus,
  RefreshCcw,
  Trash2,
} from 'lucide-react'
import type { ChangeEvent, FormEvent } from 'react'
import { useEffect, useState } from 'react'

import { projectApi } from '../services/projectApi'
import type { Application, ApplicationCreate, ApplicationUpdate } from '../types/application'

type FormState = {
  name: string
  url: string
  description: string
}

const emptyForm: FormState = {
  name: '',
  url: '',
  description: '',
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

export default function ProjectsPage() {
  const [applications, setApplications] = useState<Application[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [formData, setFormData] = useState<FormState>(emptyForm)
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  const loadApplications = async (showLoader = true) => {
    setErrorMessage('')

    if (showLoader) {
      setIsLoading(true)
    } else {
      setIsRefreshing(true)
    }

    try {
      const data = await projectApi.listApplications()
      setApplications(data)
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to load applications. Please check the backend connection and try again.',
      )
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }

  useEffect(() => {
    const fetchApplications = async () => {
      await loadApplications(true)
    }

    void fetchApplications()
  }, [])

  const resetForm = () => {
    setFormData(emptyForm)
    setEditingId(null)
  }

  const handleChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = event.target
    setFormData((current) => ({
      ...current,
      [name]: value,
    }))
  }

  const validateForm = () => {
    if (!formData.name.trim()) {
      return 'Application name is required.'
    }

    if (!formData.url.trim()) {
      return 'Application URL is required.'
    }

    try {
      const parsedUrl = new URL(formData.url.trim())

      if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') {
        return 'Application URL must use http:// or https://.'
      }
    } catch {
      return 'Please enter a valid URL starting with http:// or https://.'
    }

    return ''
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (isSubmitting) {
      return
    }

    const validationError = validateForm()

    if (validationError) {
      setErrorMessage(validationError)
      setSuccessMessage('')
      return
    }

    const normalizedName = formData.name.trim()
    const normalizedUrl = formData.url.trim()
    const normalizedDescription = formData.description.trim()

    setIsSubmitting(true)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      if (editingId !== null) {
        const payload: ApplicationUpdate = {
          name: normalizedName,
          url: normalizedUrl,
          description: normalizedDescription,
        }

        await projectApi.updateApplication(editingId, payload)
        setSuccessMessage('Application updated successfully.')
      } else {
        const payload: ApplicationCreate = {
          name: normalizedName,
          url: normalizedUrl,
          description: normalizedDescription || undefined,
        }

        await projectApi.createApplication(payload)
        setSuccessMessage('Application created successfully.')
      }

      resetForm()
      await loadApplications(false)
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'The application could not be saved. Please try again.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleEdit = (application: Application) => {
    setEditingId(application.id)
    setFormData({
      name: application.name,
      url: application.url,
      description: application.description ?? '',
    })
    setErrorMessage('')
    setSuccessMessage('')
  }

  const handleDelete = async (application: Application) => {
    const confirmed = window.confirm(`Delete "${application.name}"? This action cannot be undone.`)

    if (!confirmed) {
      return
    }

    try {
      await projectApi.deleteApplication(application.id)

      if (editingId === application.id) {
        resetForm()
      }

      setApplications((current) => current.filter((item) => item.id !== application.id))
      setSuccessMessage(`Application "${application.name}" deleted successfully.`)
      setErrorMessage('')
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'The application could not be deleted. Please try again.',
      )
      setSuccessMessage('')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-sky-300">Application portfolio</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate-50">Projects</h2>
        </div>

        <button
          type="button"
          onClick={() => void loadApplications(false)}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-700 bg-slate-900/80 px-3.5 py-2.5 text-sm font-medium text-slate-100 transition hover:border-slate-500 hover:text-white"
          disabled={isRefreshing}
        >
          <RefreshCcw className={['h-4 w-4', isRefreshing ? 'animate-spin' : ''].join(' ')} />
          {isRefreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {errorMessage ? (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      ) : null}

      {successMessage ? (
        <div className="flex items-start gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-200">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{successMessage}</span>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/30">
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-500/10 text-sky-300 ring-1 ring-inset ring-sky-500/20">
              <BriefcaseBusiness className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-200">
                {editingId !== null ? 'Edit application' : 'Add application'}
              </p>
              <p className="text-xs text-slate-400">
                {editingId !== null ? 'Update the selected target.' : 'Register a new app for testing.'}
              </p>
            </div>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="project-name" className="mb-2 block text-sm font-medium text-slate-200">
                Application name
              </label>
              <input
                id="project-name"
                name="name"
                type="text"
                value={formData.name}
                onChange={handleChange}
                placeholder="Example: Checkout Portal"
                className="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3.5 py-2.5 text-sm text-slate-50 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
                disabled={isSubmitting}
              />
            </div>

            <div>
              <label htmlFor="project-url" className="mb-2 block text-sm font-medium text-slate-200">
                Application URL
              </label>
              <input
                id="project-url"
                name="url"
                type="url"
                value={formData.url}
                onChange={handleChange}
                placeholder="https://example.com"
                className="w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3.5 py-2.5 text-sm text-slate-50 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
                disabled={isSubmitting}
              />
            </div>

            <div>
              <label htmlFor="project-description" className="mb-2 block text-sm font-medium text-slate-200">
                Description
              </label>
              <textarea
                id="project-description"
                name="description"
                value={formData.description}
                onChange={handleChange}
                rows={5}
                placeholder="Optional project summary or business context"
                className="w-full resize-none rounded-xl border border-slate-700 bg-slate-950/70 px-3.5 py-2.5 text-sm text-slate-50 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
                disabled={isSubmitting}
              />
            </div>

            <div className="flex flex-col gap-3 pt-2 sm:flex-row">
              <button
                type="submit"
                disabled={isSubmitting}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : editingId !== null ? <PencilLine className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
                {isSubmitting ? 'Saving...' : editingId !== null ? 'Update application' : 'Add application'}
              </button>

              {editingId !== null ? (
                <button
                  type="button"
                  onClick={resetForm}
                  className="inline-flex items-center justify-center rounded-xl border border-slate-700 bg-slate-950/60 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-slate-500 hover:text-slate-50"
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
              ) : null}
            </div>
          </form>
        </section>

        <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/30">
          <div className="mb-5 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-slate-200">Application list</p>
              <p className="text-xs text-slate-400">{applications.length} total</p>
            </div>
          </div>

          {isLoading ? (
            <div className="flex min-h-[220px] items-center justify-center gap-3 text-sm text-slate-300">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading applications...
            </div>
          ) : applications.length === 0 ? (
            <div className="flex min-h-[220px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-700 bg-slate-950/40 px-6 text-center">
              <BriefcaseBusiness className="h-10 w-10 text-slate-500" />
              <h3 className="mt-4 text-lg font-medium text-slate-100">No applications yet</h3>
              <p className="mt-2 max-w-md text-sm text-slate-400">
                Add your first application target to begin managing testing workflows.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {applications.map((application) => (
                <article
                  key={application.id}
                  className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4"
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="truncate text-base font-semibold text-slate-50">{application.name}</h3>
                      </div>

                      <a
                        href={application.url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-flex items-center gap-2 text-sm text-sky-300 transition hover:text-sky-200"
                      >
                        {application.url}
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleEdit(application)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900/70 px-2.5 py-1.5 text-xs font-medium text-slate-100 transition hover:border-slate-500 hover:text-white"
                      >
                        <PencilLine className="h-3.5 w-3.5" />
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDelete(application)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2.5 py-1.5 text-xs font-medium text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/15"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Delete
                      </button>
                    </div>
                  </div>

                  <p className="mt-3 text-sm leading-6 text-slate-300">
                    {application.description ? application.description : 'No description provided.'}
                  </p>

                  <div className="mt-4 flex items-center justify-between text-xs text-slate-400">
                    <span>Created</span>
                    <time>{formatDate(application.created_at)}</time>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
