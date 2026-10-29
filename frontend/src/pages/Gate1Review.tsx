import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { gatesApi } from '../api'

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
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-yellow-300">Gate 1 — Dimensional Review</h1>
      <p className="text-gray-400 text-sm">Job: {jobId}</p>

      {/* Summary */}
      <div className="flex gap-4">
        <div className="bg-green-900 text-green-200 px-4 py-2 rounded text-sm font-semibold">
          ✓ {passCount} Within Tolerance
        </div>
        <div className={`${failCount > 0 ? 'bg-red-900 text-red-200' : 'bg-gray-800 text-gray-400'} px-4 py-2 rounded text-sm font-semibold`}>
          ✗ {failCount} Out of Tolerance
        </div>
      </div>

      {/* Measurements table */}
      <div className="bg-gray-900 rounded-lg p-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left py-2">Feature</th>
              <th className="text-right py-2">Nominal</th>
              <th className="text-right py-2">Measured</th>
              <th className="text-right py-2">Deviation</th>
              <th className="text-right py-2">Tol ±</th>
              <th className="text-center py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {measurements.map((m: any) => (
              <tr key={m.feature_id} className={`border-b border-gray-800 ${m.within_tolerance ? '' : 'text-red-300'}`}>
                <td className="py-1.5 font-mono">{m.feature_id}</td>
                <td className="text-right">{m.nominal.toFixed(2)}</td>
                <td className="text-right font-semibold">{m.measured.toFixed(2)}</td>
                <td className="text-right">{m.deviation >= 0 ? '+' : ''}{m.deviation.toFixed(3)}</td>
                <td className="text-right text-gray-500">+{m.tol_plus?.toFixed(2)} / -{m.tol_minus?.toFixed(2)}</td>
                <td className="text-center text-lg">{m.within_tolerance ? '✓' : '✗'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Decision form */}
      <div className="bg-gray-900 rounded-lg p-4 space-y-4">
        <h2 className="font-semibold text-gray-300">Engineer Decision</h2>
        <div className="flex gap-3">
          {(['confirm', 'reject', 'override'] as const).map((d) => (
            <button
              key={d}
              onClick={() => setDecision(d)}
              className={`px-4 py-2 rounded text-sm font-semibold capitalize ${
                decision === d
                  ? d === 'confirm' ? 'bg-green-700 text-white'
                  : d === 'reject' ? 'bg-red-700 text-white'
                  : 'bg-yellow-700 text-white'
                  : 'bg-gray-800 text-gray-400'
              }`}
            >
              {d}
            </button>
          ))}
        </div>

        {(decision === 'override') && (
          <div>
            <label className="text-xs text-gray-400 block mb-1">Reason Code (required for override)</label>
            <input
              value={reasonCode}
              onChange={(e) => setReasonCode(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
              placeholder="e.g. calibration_error, drawing_outdated"
            />
          </div>
        )}

        <div>
          <label className="text-xs text-gray-400 block mb-1">Comments</label>
          <textarea
            value={comments}
            onChange={(e) => setComments(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
            rows={2}
          />
        </div>

        <button
          onClick={() => submit.mutate({ decision, reason_code: reasonCode || undefined, comments })}
          disabled={submit.isPending || (decision === 'override' && !reasonCode)}
          className="bg-blue-700 hover:bg-blue-600 text-white px-6 py-2 rounded font-semibold disabled:opacity-50"
        >
          {submit.isPending ? 'Submitting...' : 'Submit Decision'}
        </button>
      </div>
    </div>
  )
}
