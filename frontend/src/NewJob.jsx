import { useState } from 'react'
import { api, post } from './api.js'
import Watch from './Watch.jsx'

export default function NewJob({ onCreated }) {
  const [part, setPart] = useState('SM-1001')
  const [files, setFiles] = useState([])
  const [mode, setMode] = useState('upload')
  const [devices, setDevices] = useState(null)
  const [device, setDevice] = useState(1)
  const [preview, setPreview] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const run = async (fn) => {
    setBusy(true)
    setErr('')
    try {
      onCreated((await fn()).job_id)
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setBusy(false)
    }
  }

  const submit = (e) => {
    e.preventDefault()
    if (mode === 'camera') return run(() => post('/jobs/from-camera', { part_number: part, device, frames: 1 }))
    const fd = new FormData()
    fd.append('part_number', part)
    files.forEach((f) => fd.append('files', f))
    return run(() => api('/jobs', { method: 'POST', body: fd }))
  }

  const detect = () =>
    api('/camera/devices')
      .then((d) => {
        setDevices(d)
        if (d.length) setDevice(d[d.length - 1].index)
      })
      .catch((ex) => setErr(ex.message))

  return (
    <form onSubmit={submit} className="card">
      <h3>New inspection</h3>
      <div className="tabs">
        <button type="button" className={mode === 'upload' ? '' : 'secondary'} onClick={() => setMode('upload')}>
          Upload
        </button>
        <button type="button" className={mode === 'camera' ? '' : 'secondary'} onClick={() => setMode('camera')}>
          Phone camera
        </button>
      </div>
      <label>Part number <input value={part} onChange={(e) => setPart(e.target.value)} required /></label>
      {mode === 'upload' ? (
        <label>Images <input type="file" multiple accept="image/*" required
          onChange={(e) => setFiles([...e.target.files])} /></label>
      ) : (
        <div className="card">
          <p className="hint">Open Iriun Webcam on the phone and the laptop; the phone shows up as a camera.</p>
          <button type="button" className="secondary" onClick={detect}>Find cameras</button>
          {devices && (devices.length ? (
            <label>Camera
              <select value={device} onChange={(e) => { setDevice(Number(e.target.value)); setPreview(false) }}>
                {devices.map((d) => <option key={d.index} value={d.index}>#{d.index} · {d.width}×{d.height}</option>)}
              </select>
            </label>
          ) : <p className="err">No cameras found.</p>)}
          <button type="button" className="secondary" onClick={() => setPreview(!preview)}>
            {preview ? 'Stop preview' : 'Live preview'}
          </button>
          {preview && (
            <img className="preview" alt="live camera" src={`/api/camera/stream?device=${device}`}
              onError={() => { setPreview(false); setErr('Camera not available') }} />
          )}
        </div>
      )}
      {mode === 'camera' && <Watch part={part} device={device} onOpen={onCreated} />}
      <button disabled={busy}>{busy ? 'Working…' : mode === 'camera' ? 'Capture and inspect' : 'Start'}</button>
      {err && <p className="err">{err}</p>}
    </form>
  )
}
