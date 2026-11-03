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
  create: (partNumber: string, imageUris?: string[], verificationId?: string) =>
    api.post<Job>('/jobs', {
      part_number: partNumber,
      image_uris: imageUris ?? [],
      verification_id: verificationId,
    }),
  list: () => api.get<Job[]>('/jobs'),
  get: (id: string) => api.get<any>(`/jobs/${id}`),
  captureImage: (jobId: string, imageId: string) =>
    api.get(`/jobs/${jobId}/images/${imageId}`, { responseType: 'blob' }),
}

export const demoApi = {
  samples: () => api.get<{ name: string; has_defect: boolean }[]>('/demo/samples'),
  sample: (name: string) =>
    api.get<Blob>(`/demo/samples/${encodeURIComponent(name)}`, { responseType: 'blob' }),
}

export const partsApi = {
  list: () => api.get<any[]>('/parts'),
  references: (partNumber: string) =>
    api.get<any>(`/parts/${encodeURIComponent(partNumber)}/references`),
  referenceImage: (partNumber: string, kind: 'cad' | 'image') =>
    api.get(
      `/parts/${encodeURIComponent(partNumber)}/references/${kind}`,
      { responseType: 'blob' },
    ),
  uploadReferences: (partNumber: string, cadImage: File, referenceImage: File) => {
    const form = new FormData()
    form.append('cad_image', cadImage)
    form.append('reference_image', referenceImage)
    return api.put(`/parts/${encodeURIComponent(partNumber)}/references`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  liveDetect: (image: Blob) => {
    const form = new FormData()
    form.append('image', image, 'frame.jpg')
    return api.post<LiveDetection>('/parts/live-detect', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  verify: (partNumber: string, image: Blob) => {
    const form = new FormData()
    form.append('image', image, 'capture.jpg')
    return api.post<any>(`/parts/${encodeURIComponent(partNumber)}/verify`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
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
  rcaUrl: (jobId: string, fmt: 'docx' | 'pdf' | 'md') =>
    `/api/v1/reports/${jobId}/rca?fmt=${fmt}`,
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

export interface LiveDefect {
  defect_id: string
  defect_type: string
  confidence: number
  bbox: { x1: number; y1: number; x2: number; y2: number }
  polygon: number[][]
  note?: string | null
}

export interface LiveDetection {
  width: number
  height: number
  mock: boolean
  defects: LiveDefect[]
}

export interface RcaResult {
  rca_id: string
  model: string
  ai_used: boolean
  flags: string[]
  root_cause: {
    cause: string
    effect: string
    rationale: string
    corrective_actions: string[]
    preventive_actions: string[]
    precautions: string[]
    verification?: string | null
    confidence?: number | null
    citations: string[]
    model_version?: string | null
  }
  top3: any[]
  evidence: { chunk_id: string; text_excerpt?: string }[]
  documents: Record<string, string>
}

export interface RcaStatus {
  provider: string
  model: string | null
  gemini_key_configured: boolean
  ai_enabled: boolean
}

export const rcaApi = {
  status: () => api.get<RcaStatus>('/rca/status'),
  analyze: (payload: { defects: { defect_type: string; confidence: number; note?: string | null }[]; measurements?: any[] }) =>
    api.post<RcaResult>('/rca/analyze', payload, { timeout: 120000 }),
  download: (url: string) => api.get(url.replace('/api/v1', ''), { responseType: 'blob' }),
}
