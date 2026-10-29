import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { gatesApi, reportsApi } from '../api'

export default function Gate3Approval() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [comments, setComments] = useState('')
  const [decision, setDecision] = useState<'approve' | 'reject'>('approve')

  const { data } = useQuery({
    queryKey: ['gate3', jobId],
    queryFn: () => gatesApi.getGate3(jobId!).then((r) => r.data),
  })

  const submit = useMutation({
    mutationFn: (payload: any) => gatesApi.submitGate3(jobId!, payload),
    onSuccess: () => navigate(`/jobs/${jobId}`),
  })

  const report = data?.report

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-teal-300">Gate 3 — Approver Sign-off</h1>

      {report && (
        <div className="bg-gray-900 rounded-lg p-4 space-y-3">
          <h2 className="font-semibold text-gray-300">Report Downloads</h2>
          <div className="flex gap-3 flex-wrap">
            {report.pdf_uri && (
              <a
                href={reportsApi.downloadUrl(jobId!, 'pdf')}
                download
                className="bg-blue-800 text-blue-200 px-4 py-2 rounded text-sm hover:bg-blue-700"
              >
                📄 PDF
              </a>
            )}
            {report.xlsx_uri && (
              <a
                href={reportsApi.downloadUrl(jobId!, 'xlsx')}
                download
                className="bg-green-800 text-green-200 px-4 py-2 rounded text-sm hover:bg-green-700"
              >
                📊 Excel
              </a>
            )}
            {report.docx_uri && (
              <a
                href={reportsApi.downloadUrl(jobId!, 'docx')}
                download
                className="bg-purple-800 text-purple-200 px-4 py-2 rounded text-sm hover:bg-purple-700"
              >
                📝 Word
              </a>
            )}
          </div>
        </div>
      )}

      <div className="bg-gray-900 rounded-lg p-5 space-y-4">
        <h2 className="font-semibold text-gray-300">Approval Decision</h2>
        <div className="flex gap-3">
          <button
            onClick={() => setDecision('approve')}
            className={`px-6 py-2 rounded font-semibold text-sm ${decision === 'approve' ? 'bg-green-700 text-white' : 'bg-gray-800 text-gray-400'}`}
          >
            ✓ Approve
          </button>
          <button
            onClick={() => setDecision('reject')}
            className={`px-6 py-2 rounded font-semibold text-sm ${decision === 'reject' ? 'bg-red-700 text-white' : 'bg-gray-800 text-gray-400'}`}
          >
            ✗ Reject (Redraft)
          </button>
        </div>

        <div>
          <label className="text-xs text-gray-400 block mb-1">Comments</label>
          <textarea
            value={comments}
            onChange={(e) => setComments(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
            rows={3}
            placeholder="Required if rejecting..."
          />
        </div>

        <button
          onClick={() => submit.mutate({ decision, comments })}
          disabled={submit.isPending}
          className="bg-teal-700 hover:bg-teal-600 text-white px-6 py-2 rounded font-bold disabled:opacity-50"
        >
          {submit.isPending ? 'Submitting...' : 'Submit'}
        </button>
      </div>
    </div>
  )
}
