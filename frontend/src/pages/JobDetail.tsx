import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { jobsApi } from '../api'
import { Loading, PageHeading, Panel, StatusPill } from '../ui'

const GATE_LINKS: Record<string, { path: string; label: string; tone: string }> = {
  AWAIT_GATE1: { path: 'gate1', label: 'Gate 1 review', tone: 'status-amber' },
  AWAIT_LABEL_REVIEW: { path: 'label', label: 'Label review', tone: 'status-orange' },
  AWAIT_GATE2: { path: 'gate2', label: 'Gate 2 expert review', tone: 'status-violet' },
  AWAIT_GATE3: { path: 'gate3', label: 'Gate 3 approval', tone: 'status-teal' },
}

const SEVERITY: Record<string, string> = { critical: 'status-red', major: 'status-orange' }

export default function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>()
  const { data: job, isLoading } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => jobsApi.get(jobId!).then((r) => r.data),
    refetchInterval: 3_000,
  })

  if (isLoading) return <Loading />
  if (!job) return <div className="alert alert-error" role="alert">Job not found</div>

  const gate = GATE_LINKS[job.status]
  const done = job.status === 'CLOSED' || job.status === 'OUTPUT'

  return (
    <div className="space-y-6">
      <PageHeading
        section="Job detail"
        title="Job detail"
        description={jobId}
        action={<StatusPill status={job.status} />}
      />

      {(gate || done) && (
        <div className="flex flex-wrap gap-3">
          {gate && <Link to={`/jobs/${jobId}/${gate.path}`} className="btn-primary">{gate.label} <ArrowRight size={15} /></Link>}
          {done && <Link to={`/jobs/${jobId}/reports`} className="btn-primary">View report <ArrowRight size={15} /></Link>}
        </div>
      )}

      <Panel title="Part">
        <Row label="Part number" value={job.part_number} />
        <Row label="Stage" value={job.current_stage} />
        <Row label="Dimensional" value={job.dimensional_status} />
        <Row label="Defect found" value={job.defect_found?.toString()} />
      </Panel>

      {job.measurements?.length > 0 && (
        <section className="panel overflow-hidden">
          <div className="panel-head"><h2 className="panel-title">Dimensional measurements</h2></div>
          <div className="table-scroll">
            <table className="data-table compact">
              <thead>
                <tr><th>Feature</th><th className="num">Nominal</th><th className="num">Measured</th><th className="num">Deviation</th><th className="ctr">In tol.</th></tr>
              </thead>
              <tbody>
                {job.measurements.map((m: any) => (
                  <tr key={m.feature_id} className={m.within_tolerance ? '' : 'row-bad'}>
                    <td className="mono">{m.feature_id}</td>
                    <td className="num">{m.nominal?.toFixed(2)}</td>
                    <td className="num">{m.measured?.toFixed(2)}</td>
                    <td className="num">{m.deviation >= 0 ? '+' : ''}{m.deviation?.toFixed(3)}</td>
                    <td className="ctr">{m.within_tolerance ? '✓' : '✗'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {job.defects?.length > 0 && (
        <section className="panel overflow-hidden">
          <div className="panel-head"><h2 className="panel-title">Detected defects</h2></div>
          <div className="table-scroll">
            <table className="data-table compact">
              <thead>
                <tr><th>Type</th><th>Severity</th><th className="num">Confidence</th><th className="num">Size mm²</th></tr>
              </thead>
              <tbody>
                {job.defects.map((d: any) => (
                  <tr key={d.defect_id}>
                    <td className="capitalize">{d.defect_type}</td>
                    <td><span className={`status-pill ${SEVERITY[d.severity] ?? 'status-amber'}`}>{d.severity}</span></td>
                    <td className="num">{(d.confidence * 100).toFixed(0)}%</td>
                    <td className="num">{d.size_mm2?.toFixed(1) ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {job.flags?.length > 0 && (
        <Panel title="Flags">
          <div className="flex flex-wrap gap-2">
            {job.flags.map((f: string) => <span key={f} className="status-pill status-red">{f}</span>)}
          </div>
        </Panel>
      )}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string | number | null | undefined }) {
  return <div className="kv"><span>{label}</span><span>{value ?? '—'}</span></div>
}
