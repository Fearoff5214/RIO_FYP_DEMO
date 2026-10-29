import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { actionsApi } from '../api'

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

  if (isLoading) return <div className="text-gray-400">Loading...</div>

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-emerald-300">Corrective Actions</h1>

      {actions.length === 0 ? (
        <div className="text-gray-500 py-10 text-center">No actions yet.</div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left py-2">Job</th>
              <th className="text-left py-2">Description</th>
              <th className="text-left py-2">Owner</th>
              <th className="text-left py-2">Due</th>
              <th className="text-left py-2">Status</th>
              <th className="text-left py-2">Effective</th>
              <th className="text-left py-2"></th>
            </tr>
          </thead>
          <tbody>
            {actions.map((a: any) => (
              <tr key={a.action_id} className="border-b border-gray-800">
                <td className="py-1.5 font-mono text-xs text-gray-400">{a.job_id.slice(0, 8)}…</td>
                <td className="py-1.5 max-w-xs truncate">{a.description}</td>
                <td className="py-1.5 text-gray-400">{a.owner ?? '—'}</td>
                <td className="py-1.5 text-gray-400">{a.due_date ?? '—'}</td>
                <td className="py-1.5">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    a.status === 'DONE' ? 'bg-green-900 text-green-200' :
                    a.status === 'OVERDUE' ? 'bg-red-900 text-red-200' :
                    a.status === 'REOPENED' ? 'bg-orange-900 text-orange-200' :
                    'bg-gray-700 text-gray-300'
                  }`}>{a.status}</span>
                </td>
                <td className="py-1.5">
                  {a.effective === true ? '✓' : a.effective === false ? '✗' : '—'}
                </td>
                <td className="py-1.5 flex gap-2">
                  {a.status !== 'DONE' && (
                    <button
                      onClick={() => update.mutate({ id: a.action_id, data: { status: 'DONE', effective: true } })}
                      className="text-xs text-green-400 hover:underline"
                    >
                      Mark Done
                    </button>
                  )}
                  {a.effective !== false && a.status === 'DONE' && (
                    <button
                      onClick={() => update.mutate({ id: a.action_id, data: { effective: false } })}
                      className="text-xs text-red-400 hover:underline"
                    >
                      Not Effective
                    </button>
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
