import { useQuery } from '@tanstack/react-query'
import { dashboardApi, type KPI } from '../api'
import { PieChart, Pie, Cell, Tooltip, BarChart, Bar, XAxis, YAxis, ResponsiveContainer } from 'recharts'

const COLORS = ['#3B82F6', '#EF4444', '#F59E0B', '#10B981', '#8B5CF6']

export default function Dashboard() {
  const { data: kpis, isLoading } = useQuery({
    queryKey: ['kpis'],
    queryFn: () => dashboardApi.kpis().then((r) => r.data),
    refetchInterval: 10_000,
  })

  if (isLoading) return <div className="text-gray-400">Loading dashboard...</div>

  const k = kpis as KPI

  const defectData = Object.entries(k?.defect_distribution ?? {}).map(([name, value]) => ({
    name,
    value,
  }))

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-blue-300">Quality Dashboard</h1>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard label="Total Inspections" value={k?.total_jobs ?? 0} color="blue" />
        <KpiCard
          label="Pass Rate"
          value={`${((k?.pass_rate ?? 0) * 100).toFixed(1)}%`}
          color="green"
        />
        <KpiCard label="Defects Found" value={k?.failed ?? 0} color="red" />
        <KpiCard label="Gate Backlog" value={k?.gate_backlog ?? 0} color="yellow" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {defectData.length > 0 && (
          <div className="bg-gray-900 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-400 mb-3">Defect Distribution</h2>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={defectData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80}>
                  {defectData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {Object.keys(k?.status_distribution ?? {}).length > 0 && (
          <div className="bg-gray-900 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-400 mb-3">Job Status Distribution</h2>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={Object.entries(k.status_distribution).map(([name, value]) => ({ name, value }))}>
                <XAxis dataKey="name" tick={{ fill: '#9CA3AF', fontSize: 10 }} />
                <YAxis tick={{ fill: '#9CA3AF', fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#3B82F6" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}

function KpiCard({
  label,
  value,
  color,
}: {
  label: string
  value: string | number
  color: 'blue' | 'green' | 'red' | 'yellow'
}) {
  const colors = {
    blue: 'border-blue-700 text-blue-300',
    green: 'border-green-700 text-green-300',
    red: 'border-red-700 text-red-300',
    yellow: 'border-yellow-700 text-yellow-300',
  }
  return (
    <div className={`bg-gray-900 border rounded-lg p-4 ${colors[color]}`}>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-gray-500 mt-1">{label}</div>
    </div>
  )
}
