// Settings › Database drivers. Two questions a consultant needs answered
// before a converted report can reach a live database:
//   1. which JDBC drivers does Report Designer actually have installed, and
//   2. which JNDI connections are wired to use them.
// Selecting a connection loads its details into the form; Save & use writes
// it to the simple-jndi config Report Designer reads, so every converted
// report can bind to it.

import { useEffect, useState } from 'react'

const EMPTY = { name: '', url: '', driver: '', user: '', password: '' }

export default function DatabaseDriversCard() {
  const [info, setInfo] = useState(null)          // /settings/db-drivers
  const [connections, setConnections] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [note, setNote] = useState(null)

  useEffect(() => { refresh() }, [])

  async function refresh() {
    try {
      setInfo(await (await fetch('/settings/db-drivers')).json())
    } catch { setInfo({ prd: null, drivers: [], jndi: [] }) }
    try {
      const c = await (await fetch('/reports/connections')).json()
      setConnections(Array.isArray(c) ? c : [])
    } catch { setConnections([]) }
  }

  function select(c) {
    setError(null); setNote(null)
    setForm({ name: c.name, url: c.url || '', driver: c.driver || '', user: '', password: '' })
  }

  async function saveAndUse() {
    if (!form.name || !form.url) return
    setBusy(true); setError(null); setNote(null)
    try {
      const res = await fetch('/reports/connections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || res.statusText)
      setConnections(data.connections)
      setNote(`Saved "${form.name}" — Report Designer and every converted report can bind to it now.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (info === null) return <section className="card"><h2>Database drivers</h2><p className="muted">Loading…</p></section>

  const drivers = info.drivers || []
  const conns = connections || []

  return (
    <section className="card">
      <h2>Database drivers</h2>
      <p className="muted">
        The JDBC drivers installed in Report Designer, and the JNDI connections
        wired to use them — what databases a converted report can reach.
      </p>

      <h3>Installed JDBC drivers</h3>
      {info.prd ? (
        drivers.length ? (
          <table className="db-table">
            <thead><tr><th>Database</th><th>Driver jar</th><th></th></tr></thead>
            <tbody>
              {drivers.map((d) => (
                <tr key={d.jar}>
                  <td>{d.recognised ? d.database : <span className="muted">unrecognised</span>}</td>
                  <td className="muted cell-clip"><code>{d.jar}</code></td>
                  <td>{d.recognised ? <span className="pill-ok">✓ ready</span> : <span className="muted">?</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">No driver jars found in <code>{info.jdbc_dir}</code>. Drop a JDBC jar there to add a database.</p>
        )
      ) : (
        <p className="muted">No local Report Designer found, so no JDBC drivers to list.</p>
      )}

      <h3>Connections</h3>
      <p className="muted">Select a connection to load its details, or fill the form for a new one.</p>
      {conns.length > 0 && (
        <table className="db-table">
          <thead><tr><th>Name</th><th>URL</th><th></th></tr></thead>
          <tbody>
            {conns.map((c) => (
              <tr key={c.name} className={form.name === c.name ? 'row-selected' : ''}>
                <td><code>{c.name}</code>{c.introspectable === false && <span className="muted"> (no introspection)</span>}</td>
                <td className="muted cell-clip">{c.url}</td>
                <td><button className="linkish" onClick={() => select(c)}>select</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="connection-form">
        <input placeholder="name (e.g. Xtreme)" value={form.name}
               onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input placeholder="jdbc:mysql://localhost:3306/xtreme" value={form.url}
               onChange={(e) => setForm({ ...form, url: e.target.value })} />
        <input placeholder="user" value={form.user}
               onChange={(e) => setForm({ ...form, user: e.target.value })} />
        <input placeholder="password" type="password" value={form.password}
               onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <button className="primary" disabled={busy || !form.name || !form.url} onClick={saveAndUse}>
          {busy ? 'Saving…' : 'Save & use'}
        </button>
      </div>
      {error && <div className="error">{error}</div>}
      {note && <p className="muted">{note}</p>}
      <p className="muted">
        Saved to <code>~/.pentaho/simple-jndi/default.properties</code> — the file
        Report Designer reads. The driver class is inferred from the URL.
      </p>
    </section>
  )
}
