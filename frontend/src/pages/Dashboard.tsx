import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  ArrowUpRight,
  Clock3,
  ClipboardCheck,
  CircleAlert,
  Plus,
  ScanLine,
  ShieldCheck,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { dashboardApi, jobsApi, type Job, type KPI } from '../api'

const COLORS = ['#507da4', '#b86d67', '#c09350', '#5f927d', '#8882ae']

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

export default function Dashboard() {
  const { data: kpis, isLoading } = useQuery({
    queryKey: ['kpis'],
    queryFn: () => dashboardApi.kpis().then((r) => r.data),
    refetchInterval: 10_000,
  })
  const { data: jobs = [] } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => jobsApi.list().then((r) => r.data),
    refetchInterval: 10_000,
  })

  if (isLoading) {
    return <div className="rounded-lg border border-slate-200 bg-white p-8 text-sm text-slate-500">Loading quality overview…</div>
  }

  const k = kpis as KPI
  const defectData = Object.entries(k?.defect_distribution ?? {}).map(([name, value]) => ({ name, value }))
  const statusData = Object.entries(k?.status_distribution ?? {}).map(([name, value]) => ({ name, value }))

  return (
    <div className="space-y-7">
      <div className="page-heading">
        <div>
          <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold tracking-[0.12em] text-slate-400">
            <span>QUALITY OPERATIONS</span>
            <span className="text-slate-300">/</span>
            <span className="text-slate-500">OVERVIEW</span>
          </div>
          <h1>Inspection overview</h1>
          <p>Monitor inspection performance, review recent activity, and launch a new part verification.</p>
        </div>
        <Link to="/jobs/new" className="btn-primary">
          <Plus size={15} /> New inspection
        </Link>
      </div>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Inspection statistics">
        <KpiCard label="Total inspections" value={k?.total_jobs ?? 0} icon={ClipboardCheck} detail="All recorded inspection jobs" />
        <KpiCard label="Pass rate" value={`${((k?.pass_rate ?? 0) * 100).toFixed(1)}%`} icon={ShieldCheck} detail="Share of inspections passed" />
        <KpiCard label="Defects found" value={k?.failed ?? 0} icon={CircleAlert} detail="Inspections requiring attention" />
        <KpiCard label="Gate backlog" value={k?.gate_backlog ?? 0} icon={Clock3} detail="Awaiting human review" />
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <div className="panel p-5">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="panel-title">Defect distribution</h2>
              <p className="mt-1 text-[11px] text-slate-500">Recorded defect categories across inspections</p>
            </div>
            <div className="rounded-lg bg-slate-50 p-2 text-slate-500"><ScanLine size={17} /></div>
          </div>
          {defectData.length ? (
            <div className="grid grid-cols-1 items-center gap-3 sm:grid-cols-[minmax(150px,0.8fr)_1fr]">
              <ResponsiveContainer width="100%" height={210}>
                <PieChart>
                  <Pie data={defectData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={52} outerRadius={78} paddingAngle={3}>
                    {defectData.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} stroke="#fff" />)}
                  </Pie>
                  <Tooltip contentStyle={{ border: '1px solid #e4eaf1', borderRadius: 8, fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-3">
                {defectData.map((item, index) => (
                  <div key={item.name} className="flex items-center justify-between gap-3 text-xs">
                    <span className="flex min-w-0 items-center gap-2 capitalize text-slate-600">
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                      <span className="truncate">{item.name.replace(/_/g, ' ')}</span>
                    </span>
                    <span className="font-semibold tabular-nums text-slate-700">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyChart message="Defect distribution will appear when inspections record defects." />
          )}
        </div>

        <div className="panel p-5">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="panel-title">Workflow status</h2>
              <p className="mt-1 text-[11px] text-slate-500">Current distribution of inspection jobs</p>
            </div>
            <div className="rounded-lg bg-slate-50 p-2 text-slate-500"><Clock3 size={17} /></div>
          </div>
          {statusData.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={statusData} margin={{ top: 4, right: 6, left: -18, bottom: 4 }}>
                <XAxis dataKey="name" tick={{ fill: '#77899a', fontSize: 9 }} axisLine={{ stroke: '#e5ebf1' }} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fill: '#91a0ad', fontSize: 9 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ border: '1px solid #e4eaf1', borderRadius: 8, fontSize: 11 }} />
                <Bar dataKey="value" fill="#527fa5" radius={[4, 4, 0, 0]} maxBarSize={34} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart message="Job status counts will appear as inspections progress." />
          )}
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="panel-title">Recent inspections</h2>
            <p className="mt-1 text-[11px] text-slate-500">Latest jobs from the inspection workflow</p>
          </div>
          <Link to="/jobs" className="inline-flex items-center gap-1 text-xs font-semibold text-[#426f98] hover:text-[#244e74]">
            View inspection history <ArrowRight size={14} />
          </Link>
        </div>
        {jobs.length === 0 ? (
          <div className="px-5 py-10 text-center">
            <div className="mx-auto mb-3 grid h-10 w-10 place-items-center rounded-full bg-slate-50 text-slate-400"><ClipboardCheck size={18} /></div>
            <p className="text-sm font-semibold text-slate-700">No inspections recorded yet</p>
            <p className="mt-1 text-xs text-slate-500">Start a live inspection to see its progress here.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-left text-xs">
              <thead className="bg-slate-50/80 text-[10px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-semibold">Job reference</th>
                  <th className="px-5 py-3 font-semibold">Part number</th>
                  <th className="px-5 py-3 font-semibold">Workflow status</th>
                  <th className="px-5 py-3 font-semibold">Created</th>
                  <th className="px-5 py-3" />
                </tr>
              </thead>
              <tbody>
                {(jobs as Job[]).slice(0, 5).map((job) => (
                  <tr key={job.job_id} className="border-t border-slate-100 hover:bg-slate-50/60">
                    <td className="px-5 py-3.5 font-mono text-[11px] text-slate-500">{job.job_id.slice(0, 8).toUpperCase()}</td>
                    <td className="px-5 py-3.5 font-semibold text-slate-700">{job.part_number ?? '—'}</td>
                    <td className="px-5 py-3.5">
                      <span className={`status-pill ${STATUS_TONE[job.status] ?? 'status-neutral'}`}>{job.status.replace(/_/g, ' ')}</span>
                    </td>
                    <td className="px-5 py-3.5 text-slate-500">{new Date(job.created_at).toLocaleString()}</td>
                    <td className="px-5 py-3.5 text-right">
                      <Link to={`/jobs/${job.job_id}`} aria-label={`View inspection ${job.job_id}`} className="inline-flex items-center gap-1 font-semibold text-[#426f98] hover:text-[#244e74]">
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

function KpiCard({
  label,
  value,
  icon: Icon,
  detail,
}: {
  label: string
  value: string | number
  icon: typeof ClipboardCheck
  detail: string
}) {
  return (
    <div className="panel flex min-h-[112px] items-start justify-between gap-3 p-4">
      <div>
        <p className="text-[11px] font-medium text-slate-500">{label}</p>
        <p className="mt-2 text-[25px] font-semibold leading-none tracking-tight text-slate-800 tabular-nums">{value}</p>
        <p className="mt-2 text-[10px] text-slate-400">{detail}</p>
      </div>
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-slate-100 bg-slate-50 text-[#557d9f]">
        <Icon size={17} strokeWidth={1.8} />
      </div>
    </div>
  )
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div className="flex h-[210px] flex-col items-center justify-center text-center">
      <ScanLine size={20} className="text-slate-300" />
      <p className="mt-3 max-w-xs text-xs leading-5 text-slate-500">{message}</p>
    </div>
  )
}
