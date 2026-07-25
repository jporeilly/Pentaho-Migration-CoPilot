// Connection picker + manager for a converted report. The dropdown offers
// the JNDI connections discovered from the same simple-jndi config the
// reporting engine reads; ⚙ Manage adds save / edit / delete, persisted to
// the user's ~/.pentaho/simple-jndi/default.properties. Applying a
// connection re-converts the report, so the schema assistant, previews, and
// the .prpt all follow it.

import { useEffect, useState } from 'react'

const EMPTY = { name: '', url: '', driver: '', user: '', password: '' }

export default function ConnectionPanel({ summary, file, onUpdate }) {
  const [available, setAvailable] = useState(null)   // null = loading
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [manage, setManage] = useState(false)
  const [form, setForm] = useState(EMPTY)

  useEffect(() => { refresh() }, [])

  async function refresh() {
    try {
      const res = await fetch('/reports/connections')
      setAvailable(res.ok ? await res.json() : [])
    } catch {
      setAvailable([])
    }
  }

  async function apply(name) {
    if (!file || !name || busy) return
    setError(null)
    setBusy(true)
    try {
      const body = new FormData()
      body.append('dump', file)
      const res = await fetch(`/reports/convert?jndi=${encodeURIComponent(name)}`, {
        method: 'POST',
        body,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || res.statusText)
      onUpdate(data)   // summary.jndi changes -> the schema check re-runs
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function save() {
    setError(null)
    setBusy(true)
    try {
      const res = await fetch('/reports/connections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || res.statusText)
      setAvailable(data.connections)
      setForm(EMPTY)
      if (form.name !== summary.jndi) await apply(form.name)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function remove(name) {
    setError(null)
    try {
      const res = await fetch(`/reports/connections/${encodeURIComponent(name)}`, {
        method: 'DELETE',
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || res.statusText)
      setAvailable(data.connections)
    } catch (err) {
      setError(err.message)
    }
  }

  function editInForm(c) {
    setManage(true)
    setForm({ name: c.name, url: c.url || '', driver: c.driver || '', user: '', password: '' })
  }

  return (
    <div className="connection-panel-wrap">
      <div className="connection-panel">
        <span className="muted">Database connection (JNDI):</span>
        <select
          value={summary.jndi}
          disabled={busy || available === null}
          onChange={(e) => apply(e.target.value)}
        >
          {(available || []).map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}{c.introspectable ? '' : ' (no introspection)'}
            </option>
          ))}
          {(available || []).every((c) => c.name !== summary.jndi) && (
            <option value={summary.jndi}>{summary.jndi}</option>
          )}
        </select>
        <button className="secondary" onClick={() => setManage(!manage)}>
          {manage ? '▾' : '▸'} ⚙ Manage
        </button>
        {busy && <span className="muted">re-converting…</span>}
        {error && <span className="error-text">{error}</span>}
      </div>

      {manage && (
        <div className="connection-manager">
          <table>
            <tbody>
              {(available || []).map((c) => (
                <tr key={c.name}>
                  <td><code>{c.name}</code></td>
                  <td className="muted cell-clip">{c.url}</td>
                  <td>
                    <button className="linkish" onClick={() => editInForm(c)}>edit</button>{' '}
                    <button className="linkish danger" onClick={() => remove(c.name)}>delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="connection-form">
            <input placeholder="name (e.g. CSCU)" value={form.name}
                   onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input placeholder="jdbc:postgresql://host:5432/db" value={form.url}
                   onChange={(e) => setForm({ ...form, url: e.target.value })} />
            <input placeholder="user" value={form.user}
                   onChange={(e) => setForm({ ...form, user: e.target.value })} />
            <input placeholder="password" type="password" value={form.password}
                   onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <button disabled={busy || !form.name || !form.url} onClick={save}>
              Save &amp; use
            </button>
          </div>
          <p className="muted">
            Saved to <code>~/.pentaho/simple-jndi/default.properties</code> — the
            file Report Designer reads. The driver class is inferred from the
            URL; connections defined in the PRD install&apos;s own config can be
            used but not deleted here.
          </p>
        </div>
      )}
    </div>
  )
}
