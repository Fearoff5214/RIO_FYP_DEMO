import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT token if present
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export default api

// ── Typed helpers ────────────────────────────────────────────────────────────

export interface Job {
  job_id: string
  part_number: string | null
  status: string
  current_stage: number | null
  thread_id: string | null
  created_at: string
}

export interface KPI {
  total_jobs: number
  passed: number
  failed: number
  pass_rate: number
  defect_distribution: Record<string, number>
  status_distribution: Record<string, number>
  gate_backlog: number
}

export interface Defect {
  defect_id: string
  defect_type: string
  severity: string
  confidence: number
  size_mm2: number | null
}

export interface Measurement {
  feature_id: string
  nominal: number
  measured: number
  deviation: number
  within_tolerance: boolean
}

export interface RootCause {
  rank: number
  cause: string
  effect: string
  precautions: string[]
  confidence_raw: number
  confidence_cal: number
  evidence: object[]
}

export const jobsApi = {
  create: (partNumber: string, imageUris?: string[]) =>
    api.post<Job>('/jobs', { part_number: partNumber, image_uris: imageUris ?? [] }),
  list: () => api.get<Job[]>('/jobs'),
  get: (id: string) => api.get<any>(`/jobs/${id}`),
}

export const gatesApi = {
  getGate1: (jobId: string) => api.get<any>(`/gates/1/${jobId}`),
  submitGate1: (jobId: string, data: any) => api.post(`/gates/1/${jobId}`, data),
  getLabel: (jobId: string) => api.get<any>(`/gates/label/${jobId}`),
  submitLabel: (jobId: string, data: any) => api.post(`/gates/label/${jobId}`, data),
  getGate2: (jobId: string) => api.get<any>(`/gates/2/${jobId}`),
  submitGate2: (jobId: string, data: any) => api.post(`/gates/2/${jobId}`, data),
  getGate3: (jobId: string) => api.get<any>(`/gates/3/${jobId}`),
  submitGate3: (jobId: string, data: any) => api.post(`/gates/3/${jobId}`, data),
}

export const reportsApi = {
  get: (jobId: string) => api.get<any>(`/reports/${jobId}`),
  downloadUrl: (jobId: string, fmt: 'pdf' | 'xlsx' | 'docx') =>
    `/api/v1/reports/${jobId}/download?fmt=${fmt}`,
}

export const dashboardApi = {
  kpis: () => api.get<KPI>('/dashboard/kpis'),
}

export const kbApi = {
  list: () => api.get<any[]>('/kb/documents'),
  search: (q: string) => api.get<any>(`/kb/search?q=${encodeURIComponent(q)}`),
}

export const actionsApi = {
  list: (jobId?: string) => api.get<any[]>(`/actions${jobId ? `?job_id=${jobId}` : ''}`),
  update: (actionId: string, data: any) => api.patch(`/actions/${actionId}`, data),
}
