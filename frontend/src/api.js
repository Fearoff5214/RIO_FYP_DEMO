export const api = async (path, opts) => {
  const r = await fetch(`/api${path}`, opts)
  if (!r.ok) throw new Error((await r.text()) || r.statusText)
  return r.json()
}

export const post = (path, body) =>
  api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
