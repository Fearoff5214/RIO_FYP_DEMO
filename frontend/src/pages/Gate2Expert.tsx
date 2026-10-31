import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { gatesApi } from '../api'
import { PageHeading } from '../ui'

export default function Gate2Expert() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [selectedRank, setSelectedRank] = useState(1)
  const [decision, setDecision] = useState<'accept' | 'edit' | 'reject_all'>('accept')
  const [editedCause, setEditedCause] = useState('')
  const [corrective, setCorrective] = useState('')
  const [preventive, setPreventive] = useState('')

  const { data } = useQuery({
    queryKey: ['gate2', jobId],
    queryFn: () => gatesApi.getGate2(jobId!).then((r) => r.data),
  })

  const submit = useMutation({
    mutationFn: (payload: any) => gatesApi.submitGate2(jobId!, payload),
    onSuccess: () => navigate(`/jobs/${jobId}`),
  })

  const top3 = data?.top3 ?? []

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeading
        section="Gate 2"
        title="Expert root cause review"
        description="The AI recommends its top three root causes. Select one, then finalize."
        action={<span className="status-pill status-violet">AI top 3</span>}
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {top3.map((c: any) => {
          const pct = c.confidence_cal * 100
          const color = c.confidence_cal >= 0.85 ? '#34e0a1' : c.confidence_cal >= 0.7 ? '#ffc43d' : '#ff4d6a'
          return (
            <button
              key={c.rank}
              type="button"
              onClick={() => setSelectedRank(c.rank)}
              aria-pressed={selectedRank === c.rank}
              className="choice-card text-left"
            >
              <div className="mb-3 flex items-center justify-between">
                <span className="eyebrow">Rank {c.rank}</span>
                <span className="mono text-sm font-bold" style={{ color }}>{pct.toFixed(0)}%</span>
              </div>
              <div className="meter mb-4" style={{ ['--meter' as string]: color }}><i style={{ width: `${Math.min(100, pct)}%` }} /></div>
              <h3 className="mb-1 text-[15px] font-semibold text-ink">{c.cause}</h3>
              <p className="mb-3 text-xs leading-5 text-dim">{c.effect}</p>
              <ul className="space-y-1 text-xs text-faint">
                {c.precautions?.slice(0, 3).map((p: string, i: number) => <li key={i}>• {p}</li>)}
              </ul>
            </button>
          )
        })}
      </div>

      <section className="panel">
        <div className="panel-head"><h2 className="panel-title">Finalized root cause</h2></div>
        <div className="panel-body space-y-5">
          <div className="seg" role="group" aria-label="Decision">
            {(['accept', 'edit', 'reject_all'] as const).map((d) => (
              <button key={d} onClick={() => setDecision(d)} data-active={decision === d} data-tone={d === 'reject_all' ? 'red' : d === 'edit' ? 'amber' : undefined}>
                {d === 'reject_all' ? 'Reject all' : d}
              </button>
            ))}
          </div>

          {decision === 'edit' && (
            <div>
              <label className="field-label" htmlFor="edited">Edited root cause</label>
              <input id="edited" value={editedCause} onChange={(e) => setEditedCause(e.target.value)} />
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="field-label" htmlFor="corr">Corrective actions (one per line)</label>
              <textarea id="corr" value={corrective} onChange={(e) => setCorrective(e.target.value)} rows={4} placeholder={'Action 1\nAction 2'} />
            </div>
            <div>
              <label className="field-label" htmlFor="prev">Preventive actions (one per line)</label>
              <textarea id="prev" value={preventive} onChange={(e) => setPreventive(e.target.value)} rows={4} />
            </div>
          </div>

          <button
            onClick={() =>
              submit.mutate({
                decision,
                selected_rank: selectedRank,
                edited_cause: decision === 'edit' ? editedCause : undefined,
                corrective: corrective.split('\n').filter(Boolean),
                preventive: preventive.split('\n').filter(Boolean),
                reviewer_id: 'expert',
              })
            }
            disabled={submit.isPending || (decision === 'edit' && !editedCause)}
            className="btn-primary"
          >
            {submit.isPending ? 'Submitting…' : 'Approve & finalize'}
          </button>
        </div>
      </section>
    </div>
  )
}
