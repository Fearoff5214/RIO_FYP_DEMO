import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { FileSpreadsheet, FileText, FileType2 } from 'lucide-react'
import { reportsApi } from '../api'
import { Loading, PageHeading, Panel } from '../ui'

export default function Reports() {
  const { jobId } = useParams<{ jobId: string }>()

  const { data: report, isLoading } = useQuery({
    queryKey: ['report', jobId],
    queryFn: () => reportsApi.get(jobId!).then((r) => r.data),
  })

  if (isLoading) return <Loading />
  if (!report) return <div className="alert alert-warn">No report available yet.</div>

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeading section="Report" title="Quality inspection report" description={`Job ${jobId}`} />

      <Panel title="Report details">
        <Row label="Report ID" value={report.report_id?.slice(0, 16) + '…'} />
        <Row label="Version" value={report.version} />
        <Row label="Status" value={report.status} />
        <Row label="Approved by" value={report.approved_by ?? '—'} />
        <Row label="Approved at" value={report.approved_at ? new Date(report.approved_at).toLocaleString() : '—'} />
      </Panel>

      <Panel title="Download report">
        <div className="flex flex-wrap gap-3">
          {report.pdf_uri && <a href={reportsApi.downloadUrl(jobId!, 'pdf')} download className="btn-primary"><FileText size={15} /> PDF</a>}
          {report.xlsx_uri && <a href={reportsApi.downloadUrl(jobId!, 'xlsx')} download className="btn-secondary"><FileSpreadsheet size={15} /> Excel</a>}
          {report.docx_uri && <a href={reportsApi.downloadUrl(jobId!, 'docx')} download className="btn-secondary"><FileType2 size={15} /> Word</a>}
        </div>
      </Panel>
    </div>
  )
}

function Row({ label, value }: { label: string; value: any }) {
  return <div className="kv"><span>{label}</span><span>{value}</span></div>
}
