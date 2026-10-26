import { useCallback, useEffect, useState } from 'react'
import { api, post } from './api.js'
import Admin from './Admin.jsx'
import NewJob from './NewJob.jsx'

function Defects({ list }) {
  return (
    <table>
      <thead><tr><th>Class</th><th>Conf</th><th>Severity</th></tr></thead>
      <tbody>{list.map((d, i) => (
        <tr key={i}><td>{d.cls}</td><td>{(d.conf * 100).toFixed(0)}%</td><td>{d.severity || '-'}</td></tr>
      ))}</tbody>
    </table>
  )
}

function Gate({ pending, send }) {
  const [v, setV] = useState({})
  const set = (k) => (e) => setV({ ...v, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const g = pending.gate

  if (g === 'part_number') return (
    <div className="card gate"><h3>Part not found</h3><p>{pending.message}</p>
      <input placeholder="Part number" onChange={set('pn')} />
      <button onClick={() => send({ part_number: v.pn })}>Retry</button></div>
  )
  if (g === 'operator') return (
    <div className="card gate"><h3>Operator alert · image quality</h3><p>{pending.message}</p>
      <table><thead><tr><th>Blur</th><th>Glare</th><th>Exposure</th><th>Problems</th></tr></thead>
        <tbody>{pending.quality.map((q, i) => (
          <tr key={i} className={q.ok ? '' : 'bad'}><td>{q.blur}</td><td>{q.glare}</td><td>{q.exposure}</td>
            <td>{q.problems.join(', ') || 'ok'}</td></tr>))}</tbody></table>
      <p className="hint">Fix lighting or focus, then retake. Accepting a poor image is recorded in the report.</p>
      <button onClick={() => send({ action: 'retake' })}>Retake</button>
      <button className="secondary" onClick={() => send({ action: 'accept' })}>Accept as is</button>
      <button className="secondary" onClick={() => send({ action: 'abort' })}>Abort job</button></div>
  )
  if (g === 'engineer') return (
    <div className="card gate"><h3>Gate 1 · Engineer: dimensional result</h3>
      <b className={pending.dimensional.status === 'PASS' ? 'ok' : 'err'}>{pending.dimensional.status}</b>
      <table><thead><tr><th>Feature</th><th>Nominal</th><th>Measured</th><th>Dev</th><th>Tol</th></tr></thead>
        <tbody>{pending.dimensional.features.map((f) => (
          <tr key={f.feature} className={f.pass ? '' : 'bad'}><td>{f.feature}</td><td>{f.nominal}</td>
            <td>{f.measured}</td><td>{f.deviation}</td><td>±{f.tolerance}</td></tr>))}</tbody></table>
      <input placeholder="Recalibrated px/mm (if rejecting)" onChange={set('scale')} />
      <button onClick={() => send({ confirm: true, reviewer: v.who || 'engineer' })}>Confirm</button>
      <button className="secondary" onClick={() =>
        send({ confirm: false, scale_override: v.scale ? Number(v.scale) : null, reviewer: v.who || 'engineer' })}>
        Reject and re-measure</button></div>
  )
  if (g === 'label_review') return (
    <div className="card gate"><h3>Label review · low confidence (&lt; {pending.threshold * 100}%)</h3>
      <Defects list={pending.defects} />
      <p>Corrections go to the training set.</p>
      <label>Corrected class (applies to all; blank = keep)
        <input onChange={set('cls')} /></label>
      <button onClick={() => send({ reviewer: 'reviewer', defects: pending.defects.map((d) =>
        v.cls ? { ...d, cls: v.cls, conf: 1, source: 'human' } : d) })}>Confirm</button>
      <button className="secondary" onClick={() => send({ reviewer: 'reviewer', defects: [] })}>
        No defect (false alarm)</button></div>
  )
  if (g === 'expert') return (
    <div className="card gate"><h3>Gate 2 · Expert: choose root cause</h3>
      {pending.candidates.map((c) => (
        <label key={c.rank} className="cand">
          <input type="radio" name="rank" onChange={() => setV({ ...v, rank: c.rank })} />
          <div><b>#{c.rank} · {c.confidence}%</b> {c.cause}<br /><i>Effect:</i> {c.effect}<br />
            <i>Precautions:</i> {c.precautions.join('; ')}</div></label>))}
      {!pending.candidates.length && <p>No candidates from the knowledge base. Write the RCA below.</p>}
      <input placeholder="Edit cause / free text" onChange={set('text')} />
      <input placeholder="Reason" onChange={set('reason')} />
      <button disabled={!v.rank} onClick={() => send({ action: v.text ? 'edit' : 'select', rank: v.rank,
        text: v.text, reason: v.reason, reviewer: 'expert' })}>Finalize</button>
      <button className="secondary" onClick={() => send({ action: 'reject_all', text: v.text,
        reason: v.reason, reviewer: 'expert' })}>Reject all</button></div>
  )
  if (g === 'approver') return (
    <div className="card gate"><h3>Gate 3 · Approver sign-off ({pending.result})</h3>
      <p>{Object.entries(pending.report_paths).map(([k]) => (
        <a key={k} href={`#`} onClick={(e) => { e.preventDefault(); window.open(pending._dl(k)) }}>{k.toUpperCase()} </a>))}</p>
      <input placeholder="Comments (required to reject)" onChange={set('comments')} />
      <button onClick={() => send({ approved: true, approver: 'approver' })}>Approve and sign</button>
      <button className="secondary" onClick={() => send({ approved: false, comments: v.comments || '' })}>
        Reject, redraft</button></div>
  )
  return <pre>{JSON.stringify(pending, null, 2)}</pre>
}

function Job({ id }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const load = useCallback(() => api(`/jobs/${id}`).then(setD).catch((e) => setErr(e.message)), [id])
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t) }, [load])
  if (!d) return <p>{err || 'Loading…'}</p>
  const { job, graph, audit } = d
  const st = graph.state
  const pending = graph.pending && {
    ...graph.pending, _dl: (fmt) => `/api/jobs/${id}/report/${fmt}`,
  }
  const send = async (answer) => { try { await post(`/jobs/${id}/gate`, answer); load() } catch (e) { setErr(e.message) } }
  return (
    <div>
      <h2>Job {id} <small>{job.part_number} · {job.status}</small></h2>
      {err && <p className="err">{err}</p>}
      {pending && <Gate pending={pending} send={send} />}
      {st.defects && <div className="card"><h3>Defects</h3><Defects list={st.defects} /></div>}
      {st.flags?.length > 0 && <p className="err">Flags: {st.flags.join(', ')}</p>}
      {job.result.report_paths && <div className="card"><h3>Reports</h3>
        {Object.keys(job.result.report_paths).map((k) => (
          <a key={k} href={`/api/jobs/${id}/report/${k}`}>{k.toUpperCase()} </a>))}</div>}
      <details><summary>Audit trail ({audit.length})</summary>
        <table><tbody>{audit.map((a) => (
          <tr key={a.id}><td>{new Date(a.ts * 1000).toLocaleTimeString()}</td><td>{a.stage}</td><td>{a.event}</td></tr>))}
        </tbody></table></details>
    </div>
  )
}

export default function App() {
  const [jobs, setJobs] = useState([])
  const [sel, setSel] = useState(null)
  const [admin, setAdmin] = useState(false)
  const refresh = useCallback(() => api('/jobs').then(setJobs).catch(() => {}), [])
  useEffect(() => { refresh(); const t = setInterval(refresh, 5000); return () => clearInterval(t) }, [refresh])
  return (
    <div className="layout">
      <aside>
        <h1>Novaliseo<br /><small>AI Quality Inspection</small></h1>
        <NewJob onCreated={(id) => { setSel(id); setAdmin(false); refresh() }} />
        <button className="secondary" onClick={() => setAdmin(!admin)}>
          {admin ? 'Back to jobs' : 'Learning and integrations'}
        </button>
        <h3>Jobs</h3>
        <ul>{jobs.map((j) => (
          <li key={j.id} className={j.id === sel ? 'active' : ''} onClick={() => { setSel(j.id); setAdmin(false) }}>
            {j.part_number} <small>{j.status}</small></li>))}</ul>
      </aside>
      <main>{admin ? <Admin /> : sel ? <Job id={sel} key={sel} /> : <p>Select or create a job.</p>}</main>
    </div>
  )
}
