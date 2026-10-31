import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { FileSpreadsheet, FileText, FileType2 } from 'lucide-react'
import { gatesApi, reportsApi } from '../api'
import { PageHeading } from '../ui'

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
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeading section="Gate 3" title="Approver sign-off" description="Review the generated report, then approve or send it back for redraft." />

      {report && (
        <section className="panel">
          <div className="panel-head"><h2 className="panel-title">Report downloads</h2></div>
          <div className="panel-body flex flex-wrap gap-3">
            {report.pdf_uri && <a href={reportsApi.downloadUrl(jobId!, 'pdf')} download className="btn-secondary"><FileText size={15} /> PDF</a>}
            {report.xlsx_uri && <a href={reportsApi.downloadUrl(jobId!, 'xlsx')} download className="btn-secondary"><FileSpreadsheet size={15} /> Excel</a>}
            {report.docx_uri && <a href={reportsApi.downloadUrl(jobId!, 'docx')} download className="btn-secondary"><FileType2 size={15} /> Word</a>}
          </div>
        </section>
      )}

      <section className="panel">
        <div className="panel-head"><h2 className="panel-title">Approval decision</h2></div>
        <div className="panel-body space-y-5">
          <div className="seg" role="group" aria-label="Decision">
            <button onClick={() => setDecision('approve')} data-active={decision === 'approve'}>Approve</button>
            <button onClick={() => setDecision('reject')} data-active={decision === 'reject'} data-tone="red">Reject (redraft)</button>
          </div>
          <div>
            <label className="field-label" htmlFor="c3">Comments</label>
            <textarea id="c3" value={comments} onChange={(e) => setComments(e.target.value)} rows={3} placeholder="Required if rejecting…" />
          </div>
          <button onClick={() => submit.mutate({ decision, comments })} disabled={submit.isPending} className="btn-primary">
            {submit.isPending ? 'Submitting…' : 'Submit'}
          </button>
        </div>
      </section>
    </div>
  )
}
