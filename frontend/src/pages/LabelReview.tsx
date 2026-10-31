import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { gatesApi } from '../api'
import { PageHeading } from '../ui'

const DEFECT_TYPES = ['scratch', 'dent', 'crack', 'deformation', 'unknown_anomaly', 'other']

export default function LabelReview() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [corrections, setCorrections] = useState<Record<string, string>>({})

  const { data } = useQuery({
    queryKey: ['label', jobId],
    queryFn: () => gatesApi.getLabel(jobId!).then((r) => r.data),
  })

  const submit = useMutation({
    mutationFn: (payload: any) => gatesApi.submitLabel(jobId!, payload),
    onSuccess: () => navigate(`/jobs/${jobId}`),
  })

  const defects = data?.defects ?? []

  const handleSubmit = () => {
    const correctionList = Object.entries(corrections).map(([defect_id, defect_type]) => ({ defect_id, defect_type }))
    submit.mutate({ corrections: correctionList, reviewer_id: 'engineer' })
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeading section="Label review" title="Low-confidence detections" description="Confirm or correct the AI's defect labels before analysis continues." />

      <section className="panel overflow-hidden">
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>Defect</th><th>AI label</th><th className="num">Confidence</th><th>Correct label</th></tr></thead>
            <tbody>
              {defects.map((d: any) => (
                <tr key={d.defect_id}>
                  <td className="mono muted">{d.defect_id.slice(0, 8)}…</td>
                  <td className="capitalize">{d.defect_type}</td>
                  <td className="num mono font-semibold" style={{ color: d.confidence < 0.85 ? 'var(--rose)' : 'var(--mint)' }}>{(d.confidence * 100).toFixed(0)}%</td>
                  <td>
                    <select
                      value={corrections[d.defect_id] ?? d.defect_type}
                      onChange={(e) => setCorrections((prev) => ({ ...prev, [d.defect_id]: e.target.value }))}
                      aria-label={`Correct label for ${d.defect_id}`}
                      className="min-h-[36px] text-xs"
                    >
                      {DEFECT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <button onClick={handleSubmit} disabled={submit.isPending} className="btn-primary">
        {submit.isPending ? 'Submitting…' : 'Confirm labels'}
      </button>
    </div>
  )
}
