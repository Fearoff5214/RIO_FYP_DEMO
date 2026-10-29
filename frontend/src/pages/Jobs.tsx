import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { jobsApi, type Job } from '../api'

const STATUS_COLORS: Record<string, string> = {
  CREATED: 'bg-gray-700',
  CAPTURING: 'bg-blue-800',
  DIMENSIONAL: 'bg-blue-700',
  AWAIT_GATE1: 'bg-yellow-700',
  DEFECT_DETECTION: 'bg-purple-700',
  AWAIT_LABEL_REVIEW: 'bg-orange-700',
  RETRIEVAL: 'bg-indigo-700',
  PREDICTION: 'bg-violet-700',
  AWAIT_GATE2: 'bg-yellow-700',
  REPORTING: 'bg-teal-700',
  AWAIT_GATE3: 'bg-yellow-700',
  OUTPUT: 'bg-emerald-700',
  CLOSED: 'bg-green-800',
  ON_HOLD: 'bg-red-800',
  FAILED: 'bg-red-900',
}

export default function Jobs() {
  const { data: jobs = [], isLoading, refetch } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => jobsApi.list().then((r) => r.data),
    refetchInterval: 5_000,
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-blue-300">Inspection Jobs</h1>
        <Link
          to="/jobs/new"
          className="bg-blue-700 hover:bg-blue-600 text-white px-4 py-2 rounded text-sm"
        >
          + New Inspection
        </Link>
      </div>

      {isLoading ? (
        <div className="text-gray-400">Loading...</div>
      ) : jobs.length === 0 ? (
        <div className="text-gray-500 py-10 text-center">
          No jobs yet.{' '}
          <Link to="/jobs/new" className="text-blue-400 underline">
            Start an inspection
          </Link>
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-gray-800">
              <th className="text-left py-2">Job ID</th>
              <th className="text-left py-2">Part</th>
              <th className="text-left py-2">Status</th>
              <th className="text-left py-2">Stage</th>
              <th className="text-left py-2">Created</th>
              <th className="text-left py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {(jobs as Job[]).map((job) => (
              <tr key={job.job_id} className="border-b border-gray-900 hover:bg-gray-900 transition">
                <td className="py-2 font-mono text-xs text-gray-400">{job.job_id.slice(0, 8)}…</td>
                <td className="py-2 font-semibold">{job.part_number ?? '—'}</td>
                <td className="py-2">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      STATUS_COLORS[job.status] ?? 'bg-gray-700'
                    }`}
                  >
                    {job.status}
                  </span>
                </td>
                <td className="py-2 text-gray-400">{job.current_stage ?? '—'}</td>
                <td className="py-2 text-gray-500 text-xs">
                  {new Date(job.created_at).toLocaleString()}
                </td>
                <td className="py-2">
                  <Link to={`/jobs/${job.job_id}`} className="text-blue-400 hover:underline text-xs mr-2">
                    Detail
                  </Link>
                  {job.status === 'AWAIT_GATE1' && (
                    <Link to={`/jobs/${job.job_id}/gate1`} className="text-yellow-400 hover:underline text-xs mr-2">
                      Gate 1
                    </Link>
                  )}
                  {job.status === 'AWAIT_LABEL_REVIEW' && (
                    <Link to={`/jobs/${job.job_id}/label`} className="text-orange-400 hover:underline text-xs mr-2">
                      Label
                    </Link>
                  )}
                  {job.status === 'AWAIT_GATE2' && (
                    <Link to={`/jobs/${job.job_id}/gate2`} className="text-yellow-400 hover:underline text-xs mr-2">
                      Gate 2
                    </Link>
                  )}
                  {job.status === 'AWAIT_GATE3' && (
                    <Link to={`/jobs/${job.job_id}/gate3`} className="text-yellow-400 hover:underline text-xs mr-2">
                      Gate 3
                    </Link>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
