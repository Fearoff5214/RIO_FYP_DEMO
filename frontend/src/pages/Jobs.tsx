import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, ArrowUpRight, ClipboardList, Plus } from 'lucide-react'
import { jobsApi, type Job } from '../api'

const STATUS_TONE: Record<string, string> = {
  CREATED: 'status-neutral',
  CAPTURING: 'status-blue',
  DIMENSIONAL: 'status-blue',
  AWAIT_GATE1: 'status-amber',
  DEFECT_DETECTION: 'status-violet',
  AWAIT_LABEL_REVIEW: 'status-amber',
  RETRIEVAL: 'status-blue',
  PREDICTION: 'status-violet',
  AWAIT_GATE2: 'status-amber',
  REPORTING: 'status-teal',
  AWAIT_GATE3: 'status-amber',
  OUTPUT: 'status-green',
  CLOSED: 'status-green',
  ON_HOLD: 'status-red',
  FAILED: 'status-red',
}

export default function Jobs() {
  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => jobsApi.list().then((r) => r.data),
    refetchInterval: 5_000,
  })

  return (
    <div className="space-y-6">
      <div className="page-heading">
        <div>
          <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold tracking-[0.12em] text-slate-400">
            <span>QUALITY OPERATIONS</span><span className="text-slate-300">/</span><span className="text-slate-500">HISTORY</span>
          </div>
          <h1>Inspection history</h1>
          <p>Review jobs and follow their progress through the quality workflow.</p>
        </div>
        <Link to="/jobs/new" className="btn-primary"><Plus size={15} /> New inspection</Link>
      </div>

      <section className="panel overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="panel-title">Inspection jobs</h2>
            <p className="mt-1 text-[11px] text-slate-500">Most recent jobs are shown first</p>
          </div>
          <span className="status-pill status-neutral">{jobs.length} records</span>
        </div>

        {isLoading ? (
          <div className="space-y-3 p-5" aria-busy="true">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-9" />)}</div>
        ) : jobs.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <div className="mx-auto mb-3 grid h-11 w-11 place-items-center rounded-full bg-slate-50 text-slate-400"><ClipboardList size={19} /></div>
            <p className="text-sm font-semibold text-slate-700">No inspections yet</p>
            <p className="mt-1 text-xs text-slate-500">Start an inspection to create the first job record.</p>
            <Link to="/jobs/new" className="btn-primary mt-4"><Plus size={14} /> Start an inspection</Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-xs">
              <thead className="bg-slate-50/80 text-[10px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-semibold">Job reference</th>
                  <th className="px-5 py-3 font-semibold">Part number</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold">Stage</th>
                  <th className="px-5 py-3 font-semibold">Created</th>
                  <th className="px-5 py-3 font-semibold">Review</th>
                  <th className="px-5 py-3" />
                </tr>
              </thead>
              <tbody>
                {(jobs as Job[]).map((job) => (
                  <tr key={job.job_id} className="border-t border-slate-100 hover:bg-slate-50/70">
                    <td className="px-5 py-3.5 font-mono text-[11px] text-slate-500">{job.job_id.slice(0, 8).toUpperCase()}</td>
                    <td className="px-5 py-3.5 font-semibold text-slate-700">{job.part_number ?? '—'}</td>
                    <td className="px-5 py-3.5">
                      <span className={`status-pill ${STATUS_TONE[job.status] ?? 'status-neutral'}`}>{job.status.replace(/_/g, ' ')}</span>
                    </td>
                    <td className="px-5 py-3.5 text-slate-500">{job.current_stage ?? '—'}</td>
                    <td className="px-5 py-3.5 text-slate-500">{new Date(job.created_at).toLocaleString()}</td>
                    <td className="px-5 py-3.5">
                      {job.status === 'AWAIT_GATE1' && <ReviewLink to={`/jobs/${job.job_id}/gate1`} label="Gate 1" tone="status-amber" />}
                      {job.status === 'AWAIT_LABEL_REVIEW' && <ReviewLink to={`/jobs/${job.job_id}/label`} label="Label review" tone="status-amber" />}
                      {job.status === 'AWAIT_GATE2' && <ReviewLink to={`/jobs/${job.job_id}/gate2`} label="Gate 2" tone="status-violet" />}
                      {job.status === 'AWAIT_GATE3' && <ReviewLink to={`/jobs/${job.job_id}/gate3`} label="Gate 3" tone="status-teal" />}
                      {!['AWAIT_GATE1', 'AWAIT_LABEL_REVIEW', 'AWAIT_GATE2', 'AWAIT_GATE3'].includes(job.status) && <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <Link to={`/jobs/${job.job_id}`} className="inline-flex items-center gap-1 font-semibold text-[#426f98] hover:text-[#244e74]">
                        Details <ArrowUpRight size={13} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

function ReviewLink({ to, label, tone }: { to: string; label: string; tone: string }) {
  return (
    <Link to={to} className={`status-pill ${tone} hover:brightness-[0.98]`}>
      {label}<ArrowRight size={11} />
    </Link>
  )
}
