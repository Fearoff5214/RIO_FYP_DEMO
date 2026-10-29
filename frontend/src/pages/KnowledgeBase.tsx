import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { kbApi } from '../api'

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
      <h1 className="text-2xl font-bold text-indigo-300">Knowledge Base</h1>

      {/* Search */}
      <div className="bg-gray-900 rounded-lg p-4 space-y-3">
        <h2 className="font-semibold text-gray-300">Search</h2>
        <div className="flex gap-2">
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="e.g. bending force deformation"
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
          />
          <button
            onClick={handleSearch}
            disabled={searching}
            className="bg-indigo-700 hover:bg-indigo-600 text-white px-4 py-2 rounded text-sm"
          >
            {searching ? '...' : 'Search'}
          </button>
        </div>

        {searchResults.length > 0 && (
          <div className="space-y-2 mt-2">
            {searchResults.map((r: any, i: number) => (
              <div key={i} className="bg-gray-800 rounded p-3 text-sm">
                <div className="flex justify-between text-xs text-gray-500 mb-1">
                  <span>{r.defect_type ?? 'general'} · {r.cause ?? 'unknown cause'}</span>
                  <span>score: {r.score?.toFixed(3)}</span>
                </div>
                <p className="text-gray-300">{r.text}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Documents */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h2 className="font-semibold text-gray-300 mb-3">Ingested Documents ({docs.length})</h2>
        {isLoading ? (
          <div className="text-gray-400 text-sm">Loading...</div>
        ) : docs.length === 0 ? (
          <div className="text-gray-500 text-sm">
            No documents yet. Run <code className="bg-gray-800 px-1 rounded">python scripts/load_kb.py</code> to load samples.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left py-2">Title</th>
                <th className="text-left py-2">Type</th>
                <th className="text-left py-2">Ingested</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d: any) => (
                <tr key={d.doc_id} className="border-b border-gray-800">
                  <td className="py-1.5">{d.title}</td>
                  <td className="py-1.5 text-gray-400">{d.doc_type}</td>
                  <td className="py-1.5 text-gray-500 text-xs">
                    {new Date(d.ingested_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
