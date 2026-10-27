import { useEffect, useState } from 'react'
import { api, post } from './api.js'

const LABEL = {
  calibrating: 'Learning the empty view - keep parts out of sight',
  empty: 'Ready - show a part',
  settling: 'Hold still...',
  triggered: 'Part captured - remove it for the next one',
  error: 'Stopped',
  off: 'Not watching',
}

export default function Watch({ part, device, onOpen }) {
  const [st, setSt] = useState({ running: false, state: 'off', jobs: [] })
  const [boxes, setBoxes] = useState(true)
  const [err, setErr] = useState('')

  useEffect(() => {
    const tick = () => api('/watch').then(setSt).catch(() => {})
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [])

  const start = () => {
    setErr('')
    post('/watch/start', { part_number: part, device, live_boxes: boxes }).then(setSt).catch((e) => setErr(e.message))
  }
  const stop = () => post('/watch/stop', {}).then(() => setSt({ running: false, state: 'off', jobs: st.jobs }))

  return (
    <div className="card">
      <h4>Watch mode</h4>
      <p className="hint">Inspects automatically when a part is placed in view and held still. No button per part.</p>
      {!st.running ? (
        <>
          <label><span><input type="checkbox" checked={boxes} onChange={(e) => setBoxes(e.target.checked)} /> Show live defect boxes</span></label>
          <button type="button" onClick={start}>Start watching {part}</button>
        </>
      ) : (
        <>
          <img className="preview" alt="watch" src="/api/watch/stream" />
          <p>{LABEL[st.state]}</p>
          <button type="button" className="secondary" onClick={stop}>Stop watching</button>
        </>
      )}
      {st.error && <p className="err">{st.error}</p>}
      {err && <p className="err">{err}</p>}
      {st.jobs?.length > 0 && (
        <p className="hint">Started: {st.jobs.map((j) => (
          <a key={j} href="#" onClick={(e) => { e.preventDefault(); onOpen(j) }}>{j} </a>
        ))}</p>
      )}
    </div>
  )
}
