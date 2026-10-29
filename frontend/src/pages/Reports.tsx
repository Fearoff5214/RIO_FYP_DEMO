import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { reportsApi } from '../api'

export default function Reports() {
  const { jobId } = useParams<{ jobId: string }>()

  const { data: report, isLoading } = useQuery({
    queryKey: ['report', jobId],
    queryFn: () => reportsApi.get(jobId!).then((r) => r.data),
  })

  if (isLoading) return <div className="text-gray-400">Loading...</div>
  if (!report) return <div className="text-gray-500">No report available yet.</div>

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-green-300">Quality Inspection Report</h1>

      <div className="bg-gray-900 rounded-lg p-4 space-y-2 text-sm">
        <Row label="Report ID" value={report.report_id?.slice(0, 16) + '…'} />
        <Row label="Version" value={report.version} />
        <Row label="Status" value={report.status} />
        <Row label="Approved By" value={report.approved_by ?? '—'} />
        <Row label="Approved At" value={report.approved_at ? new Date(report.approved_at).toLocaleString() : '—'} />
      </div>

      <div className="bg-gray-900 rounded-lg p-4 space-y-3">
        <h2 className="font-semibold text-gray-300">Download Report</h2>
        <div className="flex gap-3 flex-wrap">
          {report.pdf_uri && (
            <a
              href={reportsApi.downloadUrl(jobId!, 'pdf')}
              download
              className="bg-blue-800 hover:bg-blue-700 text-blue-200 px-5 py-2 rounded font-semibold"
            >
              📄 PDF
            </a>
          )}
          {report.xlsx_uri && (
            <a
              href={reportsApi.downloadUrl(jobId!, 'xlsx')}
              download
              className="bg-green-800 hover:bg-green-700 text-green-200 px-5 py-2 rounded font-semibold"
            >
              📊 Excel
            </a>
          )}
          {report.docx_uri && (
            <a
              href={reportsApi.downloadUrl(jobId!, 'docx')}
              download
              className="bg-purple-800 hover:bg-purple-700 text-purple-200 px-5 py-2 rounded font-semibold"
            >
              📝 Word
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: any }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className="text-white">{value}</span>
    </div>
  )
}
