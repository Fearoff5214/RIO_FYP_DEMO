import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, ArrowUpRight, Clock3, ClipboardCheck, CircleAlert, Plus, ScanLine, ShieldCheck } from 'lucide-react'
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { dashboardApi, jobsApi, type Job, type KPI } from '../api'
import { Empty, PageHeading, StatusPill } from '../ui'

const COLORS = ['#c6ff3d', '#4fd8ff', '#ff8a3d', '#a78bfa', '#ff4d6a']
const tooltipStyle = { background: '#161922', border: '1px solid #343a4a', borderRadius: 10, fontSize: 12, color: '#f1f3f8' }

export default function Dashboard() {
  const { data: kpis, isLoading } = useQuery({
    queryKey: ['kpis'],
    queryFn: () => dashboardApi.kpis().then((r) => r.data),
    refetchInterval: 10_000,
  })
  const { data: jobs = [] } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => jobsApi.list().then((r) => (Array.isArray(r.data) ? r.data : [])),
    refetchInterval: 10_000,
  })

  if (isLoading) {
    return (
      <div className="space-y-7" aria-busy="true" aria-label="Loading quality overview">
        <div className="skeleton h-16 w-full max-w-md" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-[130px]" />)}
        </div>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div className="skeleton h-[300px]" />
          <div className="skeleton h-[300px]" />
        </div>
      </div>
    )
  }

  const k = kpis as KPI
  const defectData = Object.entries(k?.defect_distribution ?? {}).map(([name, value]) => ({ name, value }))
  const statusData = Object.entries(k?.status_distribution ?? {}).map(([name, value]) => ({ name, value }))

  return (
    <div className="space-y-7">
      <PageHeading
        section="Overview"
        title="Inspection overview"
        description="Monitor inspection performance, review recent activity, and launch a new part verification."
        action={<Link to="/jobs/new" className="btn-primary"><Plus size={16} /> New inspection</Link>}
      />

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Inspection statistics">
        <Stat label="Total inspections" value={k?.total_jobs ?? 0} icon={ClipboardCheck} detail="All recorded jobs" color="#c6ff3d" />
        <Stat label="Pass rate" value={`${((k?.pass_rate ?? 0) * 100).toFixed(1)}%`} icon={ShieldCheck} detail="Share of inspections passed" color="#34e0a1" />
        <Stat label="Defects found" value={k?.failed ?? 0} icon={CircleAlert} detail="Inspections needing attention" color="#ff4d6a" />
        <Stat label="Gate backlog" value={k?.gate_backlog ?? 0} icon={Clock3} detail="Awaiting human review" color="#ffc43d" />
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <div className="panel">
          <div className="panel-head">
            <div>
              <h2 className="panel-title">Defect distribution</h2>
              <p className="panel-sub">Recorded defect categories across inspections</p>
            </div>
            <div className="icon-tile"><ScanLine size={17} /></div>
          </div>
          <div className="panel-body">
            {defectData.length ? (
              <div className="grid grid-cols-1 items-center gap-3 sm:grid-cols-[minmax(150px,0.8fr)_1fr]">
                <ResponsiveContainer width="100%" height={210}>
                  <PieChart>
                    <Pie data={defectData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={55} outerRadius={82} paddingAngle={3} stroke="#0f1117" strokeWidth={3}>
                      {defectData.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} itemStyle={{ color: '#f1f3f8' }} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-3">
                  {defectData.map((item, index) => (
                    <div key={item.name} className="flex items-center justify-between gap-3 text-sm">
                      <span className="flex min-w-0 items-center gap-2.5 capitalize text-dim">
                        <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                        <span className="truncate">{item.name.replace(/_/g, ' ')}</span>
                      </span>
                      <span className="mono font-semibold tabular-nums text-ink">{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyChart message="Defect distribution will appear when inspections record defects." />
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <div>
              <h2 className="panel-title">Workflow status</h2>
              <p className="panel-sub">Current distribution of inspection jobs</p>
            </div>
            <div className="icon-tile"><Clock3 size={17} /></div>
          </div>
          <div className="panel-body">
            {statusData.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={statusData} margin={{ top: 4, right: 6, left: -18, bottom: 4 }}>
                  <XAxis dataKey="name" tick={{ fill: '#636c7f', fontSize: 10 }} axisLine={{ stroke: '#252a36' }} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fill: '#636c7f', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                  <Bar dataKey="value" fill="#c6ff3d" radius={[6, 6, 0, 0]} maxBarSize={34} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart message="Job status counts will appear as inspections progress." />
            )}
          </div>
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="panel-head">
          <div>
            <h2 className="panel-title">Recent inspections</h2>
            <p className="panel-sub">Latest jobs from the inspection workflow</p>
          </div>
          <Link to="/jobs" className="link-action">View history <ArrowRight size={14} /></Link>
        </div>
        {jobs.length === 0 ? (
          <Empty icon={<ClipboardCheck size={18} />} title="No inspections recorded yet" hint="Start a live inspection to see its progress here." />
        ) : (
          <div className="table-scroll">
            <table className="data-table min-w-[620px]">
              <thead>
                <tr><th>Job</th><th>Part number</th><th>Status</th><th>Created</th><th /></tr>
              </thead>
              <tbody>
                {(jobs as Job[]).slice(0, 5).map((job) => (
                  <tr key={job.job_id}>
                    <td className="mono muted">{job.job_id.slice(0, 8).toUpperCase()}</td>
                    <td className="font-semibold">{job.part_number ?? '—'}</td>
                    <td><StatusPill status={job.status} /></td>
                    <td className="muted">{new Date(job.created_at).toLocaleString()}</td>
                    <td className="num">
                      <Link to={`/jobs/${job.job_id}`} aria-label={`View inspection ${job.job_id}`} className="link-action">Details <ArrowUpRight size={13} /></Link>
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

function Stat({ label, value, icon: Icon, detail, color }: { label: string; value: string | number; icon: typeof ClipboardCheck; detail: string; color: string }) {
  return (
    <div className="panel stat" style={{ ['--stat-color' as string]: color }}>
      <div className="flex items-start justify-between gap-3">
        <p className="eyebrow">{label}</p>
        <Icon size={18} strokeWidth={1.8} style={{ color }} />
      </div>
      <p className="stat-value">{value}</p>
      <p className="mt-2 text-xs text-faint">{detail}</p>
    </div>
  )
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div className="flex h-[210px] flex-col items-center justify-center text-center">
      <ScanLine size={22} className="text-faint" />
      <p className="mt-3 max-w-xs text-xs leading-5 text-faint">{message}</p>
    </div>
  )
}
