import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { gatesApi } from '../api'
import { PageHeading } from '../ui'

export default function Gate1Review() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [decision, setDecision] = useState<'confirm' | 'reject' | 'override'>('confirm')
  const [reasonCode, setReasonCode] = useState('')
  const [comments, setComments] = useState('')

  const { data } = useQuery({
    queryKey: ['gate1', jobId],
    queryFn: () => gatesApi.getGate1(jobId!).then((r) => r.data),
  })

  const submit = useMutation({
    mutationFn: (payload: any) => gatesApi.submitGate1(jobId!, payload),
    onSuccess: () => navigate(`/jobs/${jobId}`),
  })

  const measurements = data?.measurements ?? []
  const passCount = measurements.filter((m: any) => m.within_tolerance).length
  const failCount = measurements.length - passCount

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeading section="Gate 1" title="Dimensional review" description={`Job ${jobId}`} />

      <div className="flex flex-wrap gap-3">
        <span className="status-pill status-green">{passCount} within tolerance</span>
        <span className={`status-pill ${failCount > 0 ? 'status-red' : 'status-neutral'}`}>{failCount} out of tolerance</span>
      </div>

      <section className="panel overflow-hidden">
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr><th>Feature</th><th className="num">Nominal</th><th className="num">Measured</th><th className="num">Deviation</th><th className="num">Tol ±</th><th className="ctr">Status</th></tr>
            </thead>
            <tbody>
              {measurements.map((m: any) => (
                <tr key={m.feature_id} className={m.within_tolerance ? '' : 'row-bad'}>
                  <td className="mono">{m.feature_id}</td>
                  <td className="num">{m.nominal.toFixed(2)}</td>
                  <td className="num font-semibold">{m.measured.toFixed(2)}</td>
                  <td className="num">{m.deviation >= 0 ? '+' : ''}{m.deviation.toFixed(3)}</td>
                  <td className="num muted">+{m.tol_plus?.toFixed(2)} / -{m.tol_minus?.toFixed(2)}</td>
                  <td className="ctr text-lg">{m.within_tolerance ? '✓' : '✗'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head"><h2 className="panel-title">Engineer decision</h2></div>
        <div className="panel-body space-y-5">
          <div className="seg" role="group" aria-label="Decision">
            {(['confirm', 'reject', 'override'] as const).map((d) => (
              <button key={d} onClick={() => setDecision(d)} data-active={decision === d} data-tone={d === 'reject' ? 'red' : d === 'override' ? 'amber' : undefined}>{d}</button>
            ))}
          </div>

          {decision === 'override' && (
            <div>
              <label className="field-label" htmlFor="reason">Reason code (required for override)</label>
              <input id="reason" value={reasonCode} onChange={(e) => setReasonCode(e.target.value)} placeholder="e.g. calibration_error, drawing_outdated" />
            </div>
          )}

          <div>
            <label className="field-label" htmlFor="comments">Comments</label>
            <textarea id="comments" value={comments} onChange={(e) => setComments(e.target.value)} rows={3} />
          </div>

          <button
            onClick={() => submit.mutate({ decision, reason_code: reasonCode || undefined, comments })}
            disabled={submit.isPending || (decision === 'override' && !reasonCode)}
            className="btn-primary"
          >
            {submit.isPending ? 'Submitting…' : 'Submit decision'}
          </button>
        </div>
      </section>
    </div>
  )
}
