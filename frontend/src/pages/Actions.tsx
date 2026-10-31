import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings2 } from 'lucide-react'
import { actionsApi } from '../api'
import { Empty, Loading, PageHeading } from '../ui'

const TONE: Record<string, string> = {
  DONE: 'status-green',
  OVERDUE: 'status-red',
  REOPENED: 'status-orange',
}

export default function Actions() {
  const qc = useQueryClient()
  const { data: actions = [], isLoading } = useQuery({
    queryKey: ['actions'],
    queryFn: () => actionsApi.list().then((r) => r.data),
  })

  const update = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => actionsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['actions'] }),
  })

  if (isLoading) return <Loading />

  return (
    <div className="space-y-6">
      <PageHeading section="Actions" title="Corrective actions" description="Track corrective and preventive actions raised from inspections." />

      <section className="panel overflow-hidden">
        {actions.length === 0 ? (
          <Empty icon={<Settings2 size={18} />} title="No actions yet" hint="Actions appear here after a root cause is finalized." />
        ) : (
          <div className="table-scroll">
            <table className="data-table min-w-[760px]">
              <thead>
                <tr><th>Job</th><th>Description</th><th>Owner</th><th>Due</th><th>Status</th><th>Effective</th><th /></tr>
              </thead>
              <tbody>
                {actions.map((a: any) => (
                  <tr key={a.action_id}>
                    <td className="mono muted">{a.job_id.slice(0, 8)}…</td>
                    <td className="max-w-xs truncate">{a.description}</td>
                    <td className="muted">{a.owner ?? '—'}</td>
                    <td className="muted">{a.due_date ?? '—'}</td>
                    <td><span className={`status-pill ${TONE[a.status] ?? 'status-neutral'}`}>{a.status}</span></td>
                    <td>{a.effective === true ? '✓' : a.effective === false ? '✗' : '—'}</td>
                    <td>
                      <div className="flex gap-3">
                        {a.status !== 'DONE' && (
                          <button className="link-action" onClick={() => update.mutate({ id: a.action_id, data: { status: 'DONE', effective: true } })}>Mark done</button>
                        )}
                        {a.effective !== false && a.status === 'DONE' && (
                          <button className="link-action" style={{ color: 'var(--rose)' }} onClick={() => update.mutate({ id: a.action_id, data: { effective: false } })}>Not effective</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
