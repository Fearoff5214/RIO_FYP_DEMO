import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { gatesApi } from '../api'

export default function Gate2Expert() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [selectedRank, setSelectedRank] = useState(1)
  const [decision, setDecision] = useState<'accept' | 'edit' | 'reject_all'>('accept')
  const [editedCause, setEditedCause] = useState('')
  const [corrective, setCorrective] = useState('')
  const [preventive, setPreventive] = useState('')

  const { data } = useQuery({
    queryKey: ['gate2', jobId],
    queryFn: () => gatesApi.getGate2(jobId!).then((r) => r.data),
  })

  const submit = useMutation({
    mutationFn: (payload: any) => gatesApi.submitGate2(jobId!, payload),
    onSuccess: () => navigate(`/jobs/${jobId}`),
  })

  const top3 = data?.top3 ?? []

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-purple-300">Gate 2 — Expert Root Cause Review</h1>
        <span className="bg-purple-900 text-purple-200 px-2 py-0.5 rounded text-xs">AI Recommended Top 3 Root Causes</span>
      </div>

      {/* Top 3 cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {top3.map((c: any) => (
          <div
            key={c.rank}
            onClick={() => setSelectedRank(c.rank)}
            className={`bg-gray-900 rounded-lg p-4 cursor-pointer border-2 transition ${
              selectedRank === c.rank ? 'border-purple-500' : 'border-transparent hover:border-gray-700'
            }`}
          >
            <div className="flex justify-between items-start mb-2">
              <span className="text-xs text-gray-500">Rank {c.rank}</span>
              <span className={`text-sm font-bold ${c.confidence_cal >= 0.85 ? 'text-green-400' : c.confidence_cal >= 0.70 ? 'text-yellow-400' : 'text-red-400'}`}>
                {(c.confidence_cal * 100).toFixed(0)}%
              </span>
            </div>
            <h3 className="font-semibold text-white text-sm mb-1">{c.cause}</h3>
            <p className="text-xs text-gray-400 mb-2">{c.effect}</p>
            <div className="text-xs text-gray-500 space-y-0.5">
              {c.precautions?.slice(0, 3).map((p: string, i: number) => (
                <div key={i}>• {p}</div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Decision panel */}
      <div className="bg-gray-900 rounded-lg p-5 space-y-4">
        <h2 className="font-semibold text-gray-300">Finalized Root Cause</h2>

        <div className="flex gap-3">
          {(['accept', 'edit', 'reject_all'] as const).map((d) => (
            <button
              key={d}
              onClick={() => setDecision(d)}
              className={`px-4 py-2 rounded text-sm font-semibold ${
                decision === d
                  ? d === 'accept' ? 'bg-green-700 text-white'
                  : d === 'edit' ? 'bg-yellow-700 text-white'
                  : 'bg-red-700 text-white'
                  : 'bg-gray-800 text-gray-400'
              }`}
            >
              {d === 'reject_all' ? 'Reject All' : d.charAt(0).toUpperCase() + d.slice(1)}
            </button>
          ))}
        </div>

        {decision === 'edit' && (
          <div>
            <label className="text-xs text-gray-400 block mb-1">Edited Root Cause</label>
            <input
              value={editedCause}
              onChange={(e) => setEditedCause(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
            />
          </div>
        )}

        <div>
          <label className="text-xs text-gray-400 block mb-1">Corrective Actions (one per line)</label>
          <textarea
            value={corrective}
            onChange={(e) => setCorrective(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
            rows={3}
            placeholder="Action 1&#10;Action 2"
          />
        </div>

        <div>
          <label className="text-xs text-gray-400 block mb-1">Preventive Actions (one per line)</label>
          <textarea
            value={preventive}
            onChange={(e) => setPreventive(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
            rows={3}
          />
        </div>

        <button
          onClick={() =>
            submit.mutate({
              decision,
              selected_rank: selectedRank,
              edited_cause: decision === 'edit' ? editedCause : undefined,
              corrective: corrective.split('\n').filter(Boolean),
              preventive: preventive.split('\n').filter(Boolean),
              reviewer_id: 'expert',
            })
          }
          disabled={submit.isPending || (decision === 'edit' && !editedCause)}
          className="bg-purple-700 hover:bg-purple-600 text-white px-6 py-2 rounded font-bold disabled:opacity-50"
        >
          {submit.isPending ? 'Submitting...' : '✓ APPROVED & FINALIZED'}
        </button>
      </div>
    </div>
  )
}
