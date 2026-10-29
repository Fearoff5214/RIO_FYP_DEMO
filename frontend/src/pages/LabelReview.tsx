import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { gatesApi } from '../api'

const DEFECT_TYPES = ['scratch', 'dent', 'crack', 'deformation', 'unknown_anomaly', 'other']

export default function LabelReview() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [corrections, setCorrections] = useState<Record<string, string>>({})

  const { data } = useQuery({
    queryKey: ['label', jobId],
    queryFn: () => gatesApi.getLabel(jobId!).then((r) => r.data),
  })

  const submit = useMutation({
    mutationFn: (payload: any) => gatesApi.submitLabel(jobId!, payload),
    onSuccess: () => navigate(`/jobs/${jobId}`),
  })

  const defects = data?.defects ?? []

  const handleCorrection = (defectId: string, newType: string) => {
    setCorrections((prev) => ({ ...prev, [defectId]: newType }))
  }

  const handleSubmit = () => {
    const correctionList = Object.entries(corrections).map(([defect_id, defect_type]) => ({
      defect_id,
      defect_type,
    }))
    submit.mutate({ corrections: correctionList, reviewer_id: 'engineer' })
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-orange-300">Label Review — Low Confidence Detections</h1>

      <div className="bg-gray-900 rounded-lg p-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left py-2">Defect ID</th>
              <th className="text-left py-2">AI Label</th>
              <th className="text-right py-2">Confidence</th>
              <th className="text-left py-2">Correct Label</th>
            </tr>
          </thead>
          <tbody>
            {defects.map((d: any) => (
              <tr key={d.defect_id} className="border-b border-gray-800">
                <td className="py-2 font-mono text-xs text-gray-400">{d.defect_id.slice(0, 8)}…</td>
                <td className="py-2 capitalize">{d.defect_type}</td>
                <td className={`py-2 text-right ${d.confidence < 0.85 ? 'text-red-400' : 'text-green-400'}`}>
                  {(d.confidence * 100).toFixed(0)}%
                </td>
                <td className="py-2">
                  <select
                    value={corrections[d.defect_id] ?? d.defect_type}
                    onChange={(e) => handleCorrection(d.defect_id, e.target.value)}
                    className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs"
                  >
                    {DEFECT_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button
        onClick={handleSubmit}
        disabled={submit.isPending}
        className="bg-orange-700 hover:bg-orange-600 text-white px-6 py-2 rounded font-semibold disabled:opacity-50"
      >
        {submit.isPending ? 'Submitting...' : 'Confirm Labels'}
      </button>
    </div>
  )
}
