import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { jobsApi } from '../api'

export default function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>()
  const { data: job, isLoading } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => jobsApi.get(jobId!).then((r) => r.data),
    refetchInterval: 3_000,
  })

  if (isLoading) return <div className="text-gray-400">Loading...</div>
  if (!job) return <div className="text-red-400">Job not found</div>

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-blue-300">Job Detail</h1>
          <p className="text-gray-500 text-sm font-mono">{jobId}</p>
        </div>
        <span className="bg-blue-900 text-blue-200 px-3 py-1 rounded text-sm font-semibold">
          {job.status}
        </span>
      </div>

      {/* Part info */}
      <Section title="Part">
        <Row label="Part Number" value={job.part_number} />
        <Row label="Stage" value={job.current_stage} />
        <Row label="Dimensional" value={job.dimensional_status} />
        <Row label="Defect Found" value={job.defect_found?.toString()} />
      </Section>

      {/* Quick gate links */}
      <div className="flex gap-3 flex-wrap">
        {job.status === 'AWAIT_GATE1' && (
          <Link to={`/jobs/${jobId}/gate1`} className="bg-yellow-700 text-white px-4 py-2 rounded text-sm">
            → Gate 1 Review
          </Link>
        )}
        {job.status === 'AWAIT_LABEL_REVIEW' && (
          <Link to={`/jobs/${jobId}/label`} className="bg-orange-700 text-white px-4 py-2 rounded text-sm">
            → Label Review
          </Link>
        )}
        {job.status === 'AWAIT_GATE2' && (
          <Link to={`/jobs/${jobId}/gate2`} className="bg-purple-700 text-white px-4 py-2 rounded text-sm">
            → Gate 2 Expert
          </Link>
        )}
        {job.status === 'AWAIT_GATE3' && (
          <Link to={`/jobs/${jobId}/gate3`} className="bg-teal-700 text-white px-4 py-2 rounded text-sm">
            → Gate 3 Approval
          </Link>
        )}
        {(job.status === 'CLOSED' || job.status === 'OUTPUT') && (
          <Link to={`/jobs/${jobId}/reports`} className="bg-green-800 text-white px-4 py-2 rounded text-sm">
            → View Report
          </Link>
        )}
      </div>

      {/* Measurements */}
      {job.measurements?.length > 0 && (
        <Section title="Dimensional Measurements">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500">
                <th className="text-left py-1">Feature</th>
                <th className="text-right py-1">Nominal</th>
                <th className="text-right py-1">Measured</th>
                <th className="text-right py-1">Deviation</th>
                <th className="text-center py-1">OK?</th>
              </tr>
            </thead>
            <tbody>
              {job.measurements.map((m: any) => (
                <tr key={m.feature_id} className={m.within_tolerance ? '' : 'text-red-400'}>
                  <td className="py-0.5">{m.feature_id}</td>
                  <td className="text-right">{m.nominal?.toFixed(2)}</td>
                  <td className="text-right">{m.measured?.toFixed(2)}</td>
                  <td className="text-right">{m.deviation >= 0 ? '+' : ''}{m.deviation?.toFixed(3)}</td>
                  <td className="text-center">{m.within_tolerance ? '✓' : '✗'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}

      {/* Defects */}
      {job.defects?.length > 0 && (
        <Section title="Detected Defects">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500">
                <th className="text-left py-1">Type</th>
                <th className="text-left py-1">Severity</th>
                <th className="text-right py-1">Confidence</th>
                <th className="text-right py-1">Size mm²</th>
              </tr>
            </thead>
            <tbody>
              {job.defects.map((d: any) => (
                <tr key={d.defect_id}>
                  <td className="py-0.5 capitalize">{d.defect_type}</td>
                  <td>
                    <span className={`px-1 rounded text-xs ${
                      d.severity === 'critical' ? 'bg-red-900 text-red-200' :
                      d.severity === 'major' ? 'bg-orange-900 text-orange-200' :
                      'bg-yellow-900 text-yellow-200'
                    }`}>{d.severity}</span>
                  </td>
                  <td className="text-right">{(d.confidence * 100).toFixed(0)}%</td>
                  <td className="text-right">{d.size_mm2?.toFixed(1) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}

      {/* Flags */}
      {job.flags?.length > 0 && (
        <Section title="Flags">
          <div className="flex gap-2 flex-wrap">
            {job.flags.map((f: string) => (
              <span key={f} className="bg-red-900 text-red-200 px-2 py-0.5 rounded text-xs">{f}</span>
            ))}
          </div>
        </Section>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wide">{title}</h2>
      {children}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="flex justify-between text-sm py-0.5">
      <span className="text-gray-500">{label}</span>
      <span className="text-white">{value ?? '—'}</span>
    </div>
  )
}
