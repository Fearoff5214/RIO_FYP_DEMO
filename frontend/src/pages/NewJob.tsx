import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { jobsApi } from '../api'

export default function NewJob() {
  const navigate = useNavigate()
  const [partNumber, setPartNumber] = useState('MS-4505-001')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const resp = await jobsApi.create(partNumber)
      navigate(`/jobs/${resp.data.job_id}`)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Failed to create job')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto mt-10">
      <h1 className="text-2xl font-bold text-blue-300 mb-6">New Inspection Job</h1>
      <form onSubmit={handleSubmit} className="bg-gray-900 rounded-lg p-6 space-y-4">
        <div>
          <label className="text-sm text-gray-400 block mb-1">Part Number</label>
          <input
            type="text"
            value={partNumber}
            onChange={(e) => setPartNumber(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white text-sm"
            placeholder="e.g. MS-4505-001"
            required
          />
        </div>
        {error && <div className="text-red-400 text-sm">{error}</div>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-700 hover:bg-blue-600 text-white py-2 rounded font-semibold disabled:opacity-50"
        >
          {loading ? 'Starting...' : 'Start Inspection'}
        </button>
      </form>
    </div>
  )
}
