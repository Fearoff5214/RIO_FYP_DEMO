import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, ArrowUpRight, ClipboardList, Plus } from 'lucide-react'
import { jobsApi, type Job } from '../api'
import { Empty, PageHeading, StatusPill } from '../ui'

const REVIEW: Record<string, { path: string; label: string; tone: string }> = {
  AWAIT_GATE1: { path: 'gate1', label: 'Gate 1', tone: 'status-amber' },
  AWAIT_LABEL_REVIEW: { path: 'label', label: 'Label review', tone: 'status-orange' },
  AWAIT_GATE2: { path: 'gate2', label: 'Gate 2', tone: 'status-violet' },
  AWAIT_GATE3: { path: 'gate3', label: 'Gate 3', tone: 'status-teal' },
}

export default function Jobs() {
  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => jobsApi.list().then((r) => (Array.isArray(r.data) ? r.data : [])),
    refetchInterval: 5_000,
  })

  return (
    <div className="space-y-6">
      <PageHeading
        section="History"
        title="Inspection history"
        description="Review jobs and follow their progress through the quality workflow."
        action={<Link to="/jobs/new" className="btn-primary"><Plus size={16} /> New inspection</Link>}
      />

      <section className="panel overflow-hidden">
        <div className="panel-head">
          <div>
            <h2 className="panel-title">Inspection jobs</h2>
            <p className="panel-sub">Most recent jobs are shown first</p>
          </div>
          <span className="status-pill status-neutral">{jobs.length} records</span>
        </div>

        {isLoading ? (
          <div className="space-y-3 p-5" aria-busy="true">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-10" />)}</div>
        ) : jobs.length === 0 ? (
          <div>
            <Empty icon={<ClipboardList size={19} />} title="No inspections yet" hint="Start an inspection to create the first job record." />
            <div className="pb-10 text-center"><Link to="/jobs/new" className="btn-primary"><Plus size={14} /> Start an inspection</Link></div>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table min-w-[760px]">
              <thead>
                <tr><th>Job</th><th>Part number</th><th>Status</th><th>Stage</th><th>Created</th><th>Review</th><th /></tr>
              </thead>
              <tbody>
                {(jobs as Job[]).map((job) => {
                  const review = REVIEW[job.status]
                  return (
                    <tr key={job.job_id}>
                      <td className="mono muted">{job.job_id.slice(0, 8).toUpperCase()}</td>
                      <td className="font-semibold">{job.part_number ?? '—'}</td>
                      <td><StatusPill status={job.status} /></td>
                      <td className="muted">{job.current_stage ?? '—'}</td>
                      <td className="muted">{new Date(job.created_at).toLocaleString()}</td>
                      <td>
                        {review ? (
                          <Link to={`/jobs/${job.job_id}/${review.path}`} className={`status-pill ${review.tone}`}>{review.label}<ArrowRight size={11} /></Link>
                        ) : <span className="text-faint">—</span>}
                      </td>
                      <td className="num"><Link to={`/jobs/${job.job_id}`} className="link-action">Details <ArrowUpRight size={13} /></Link></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
