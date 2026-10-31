import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen, Search } from 'lucide-react'
import { kbApi } from '../api'
import { Empty, PageHeading } from '../ui'

export default function KnowledgeBase() {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [searching, setSearching] = useState(false)

  const { data: docs = [], isLoading } = useQuery({
    queryKey: ['kb-docs'],
    queryFn: () => kbApi.list().then((r) => r.data),
  })

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setSearching(true)
    try {
      const resp = await kbApi.search(searchQuery)
      setSearchResults(resp.data.results ?? [])
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeading section="Knowledge" title="Knowledge base" description="Search ingested quality documents for defects, causes and fixes." />

      <section className="panel">
        <div className="panel-head"><h2 className="panel-title">Search</h2></div>
        <div className="panel-body space-y-4">
          <div className="flex gap-2">
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="e.g. bending force deformation"
              aria-label="Search the knowledge base"
            />
            <button onClick={handleSearch} disabled={searching} className="btn-primary shrink-0"><Search size={15} /> {searching ? 'Searching…' : 'Search'}</button>
          </div>

          {searchResults.length > 0 && (
            <div className="space-y-3">
              {searchResults.map((r: any, i: number) => (
                <div key={i} className="rounded-xl border border-line bg-raised p-4">
                  <div className="mb-2 flex justify-between gap-3 text-xs text-faint">
                    <span>{r.defect_type ?? 'general'} · {r.cause ?? 'unknown cause'}</span>
                    <span className="mono">score {r.score?.toFixed(3)}</span>
                  </div>
                  <p className="text-sm leading-6 text-dim">{r.text}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="panel-head"><h2 className="panel-title">Ingested documents ({docs.length})</h2></div>
        {isLoading ? (
          <div className="p-5"><div className="skeleton h-24" /></div>
        ) : docs.length === 0 ? (
          <Empty icon={<BookOpen size={18} />} title="No documents yet" hint="Run python scripts/load_kb.py to load samples." />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Title</th><th>Type</th><th>Ingested</th></tr></thead>
              <tbody>
                {docs.map((d: any) => (
                  <tr key={d.doc_id}>
                    <td>{d.title}</td>
                    <td className="muted">{d.doc_type}</td>
                    <td className="muted">{new Date(d.ingested_at).toLocaleDateString()}</td>
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
