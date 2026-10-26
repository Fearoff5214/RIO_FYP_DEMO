import { useCallback, useEffect, useState } from 'react'
import { api, post } from './api.js'

export default function Admin() {
  const [learn, setLearn] = useState(null)
  const [outbox, setOutbox] = useState([])
  const [msg, setMsg] = useState('')

  const load = useCallback(() => {
    api('/learning').then(setLearn).catch((e) => setMsg(e.message))
    api('/outbox').then(setOutbox).catch(() => {})
  }, [])
  useEffect(() => {
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [load])

  const act = async (fn) => {
    try {
      setMsg(JSON.stringify(await fn()))
      load()
    } catch (e) {
      setMsg(e.message)
    }
  }
  if (!learn) return <p>{msg || 'Loading…'}</p>
  const cal = learn.calibration

  return (
    <div>
      <h2>Learning and integrations</h2>

      <div className="card">
        <h3>Detector model</h3>
        <p>
          Active: <b>{learn.active}</b> · labels waiting: {learn.pending_labels} / {learn.retrain_min_labels} ·
          auto retrain: {learn.auto_retrain ? 'on' : 'off'}{learn.training.running && ' · training…'}
        </p>
        <table>
          <thead><tr><th>Version</th><th>Status</th><th>mAP50 before → after</th><th>Labels</th><th /></tr></thead>
          <tbody>
            {Object.entries(learn.versions).map(([v, i]) => (
              <tr key={v}>
                <td>{v}</td>
                <td>{i.status}{i.weak_validation ? ' (weak validation)' : ''}</td>
                <td>{i.map50_base ?? '-'} → {i.map50_new ?? '-'}</td>
                <td>{i.n_labels ?? '-'}</td>
                <td>{v !== learn.active && (
                  <button className="secondary" onClick={() => act(() => post('/learning/activate', { version: v }))}>
                    Activate
                  </button>
                )}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <button onClick={() => act(() => post('/learning/retrain', { force: false, epochs: 30 }))}>Retrain now</button>
        {learn.training.last_error && <p className="err">{learn.training.last_error}</p>}
      </div>

      <div className="card">
        <h3>Confidence recalibration</h3>
        {cal ? (
          <p>
            {cal.n} expert decisions · {cal.active ? 'active' : 'collecting'} · acceptance by AI rank:{' '}
            {Object.entries(cal.rank_acc).map(([r, a]) => `#${r} ${(a * 100).toFixed(0)}%`).join(', ')}
          </p>
        ) : <p>No expert decisions yet.</p>}
        <button className="secondary" onClick={() => act(() => post('/learning/recalibrate', {}))}>Recalibrate</button>
      </div>

      <div className="card">
        <h3>Anomaly model</h3>
        <p className="hint">Needs 3+ defect-free photos of the part in data/good/default/.</p>
        <button className="secondary" onClick={() => act(() => post('/anomaly/fit', { part_number: 'default' }))}>
          Fit from data/good/default
        </button>
      </div>

      <div className="card">
        <h3>MES / QMS / ERP / notification outbox</h3>
        <table>
          <thead><tr><th>Job</th><th>System</th><th>Status</th><th>Tries</th><th>Error</th></tr></thead>
          <tbody>
            {outbox.map((o) => (
              <tr key={o.id} className={o.status === 'failed' ? 'bad' : ''}>
                <td>{o.job_id}</td><td>{o.system}</td><td>{o.status}</td><td>{o.attempts}</td><td>{o.last_error}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <button className="secondary" onClick={() => act(() => post('/outbox/retry', {}))}>Retry failed</button>
      </div>

      {msg && <pre>{msg}</pre>}
    </div>
  )
}
