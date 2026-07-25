// Schema-aware SQL agent: deterministic validation banner (EXPLAIN against
// the live JNDI target) + a schema-grounded chat that proposes corrected SQL
// as a reviewable diff. Proposals are never auto-applied — the Apply button
// re-converts with the override and records it as a review item.

import { useEffect, useRef, useState } from 'react'

export default function SqlAssistant({ summary, file, onUpdate }) {
  const [check, setCheck] = useState(null)        // {ok, error} | {unavailable}
  const [checking, setChecking] = useState(false)
  const [schema, setSchema] = useState(null)      // null | {tables} | {error}
  const [showSchema, setShowSchema] = useState(false)
  const [preview, setPreview] = useState(null)    // null | {columns, rows} | {error}
  const [previewing, setPreviewing] = useState(false)
  const [messages, setMessages] = useState([])    // {role, content, sql?}
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState(null)
  const endRef = useRef(null)

  const params = summary.parameters.map((p) => ({ name: p.name, default: p.default }))

  async function runCheck() {
    setChecking(true)
    try {
      const res = await fetch('/reports/sql/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jndi: summary.jndi, sql: summary.sql, parameters: params }),
      })
      const data = await res.json()
      setCheck(res.ok ? data : { ok: false, error: data.detail || res.statusText })
    } catch (err) {
      setCheck({ ok: false, error: err.message })
    } finally {
      setChecking(false)
    }
  }

  useEffect(() => { runCheck(); setSchema(null); setPreview(null) }, [summary.sql, summary.jndi]) // eslint-disable-line react-hooks/exhaustive-deps

  async function runPreview() {
    if (preview && !preview.error) { setPreview(null); return }  // toggle off
    setPreviewing(true)
    setPreview(null)
    try {
      const res = await fetch('/reports/sql/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jndi: summary.jndi, sql: summary.sql, parameters: params }),
      })
      const data = await res.json()
      setPreview(res.ok ? data : { error: data.detail || res.statusText })
    } catch (err) {
      setPreview({ error: err.message })
    } finally {
      setPreviewing(false)
    }
  }

  async function toggleSchema() {
    const next = !showSchema
    setShowSchema(next)
    if (next && schema === null) {
      try {
        const res = await fetch(`/reports/schema?jndi=${encodeURIComponent(summary.jndi)}`)
        const data = await res.json()
        setSchema(res.ok ? data : { error: data.detail || res.statusText })
      } catch (err) {
        setSchema({ error: err.message })
      }
    }
  }
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  async function ask(e) {
    e?.preventDefault()
    const q = question.trim()
    if (!q || asking) return
    setError(null)
    setAsking(true)
    setMessages((m) => [...m, { role: 'user', content: q }])
    setQuestion('')
    try {
      const res = await fetch('/reports/sql/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jndi: summary.jndi,
          sql: summary.sql,
          question: q,
          parameters: params,
          history: messages.map(({ role, content }) => ({ role, content })),
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || res.statusText)
      setMessages((m) => [...m, { role: 'assistant', content: data.reply, sql: data.sql || '' }])
    } catch (err) {
      setError(err.message)
      setMessages((m) => m.slice(0, -1))
      setQuestion(q)
    } finally {
      setAsking(false)
    }
  }

  async function applySql(sql) {
    if (!file || applying) return
    setError(null)
    setApplying(true)
    try {
      const form = new FormData()
      form.append('dump', file)
      form.append('sql_override', sql)
      const res = await fetch(`/reports/convert?jndi=${encodeURIComponent(summary.jndi)}`, {
        method: 'POST',
        body: form,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || res.statusText)
      onUpdate(data) // summary.sql changes -> the validation banner re-runs
    } catch (err) {
      setError(err.message)
    } finally {
      setApplying(false)
    }
  }

  const banner = checking
    ? { cls: 'review', text: '… checking SQL against the live database' }
    : !check
      ? null
      : check.ok
        ? { cls: 'auto', text: `✓ SQL validates against ${summary.jndi} (EXPLAIN passed on the live database)` }
        : check.checked_sql === ''
          ? { cls: 'review', text: `⚠ schema check unavailable — ${check.error}` }
          : { cls: 'manual', text: `✗ SQL fails against ${summary.jndi}: ${check.error}` }

  return (
    <div className="sql-assistant">
      {banner && <div className={`sql-verdict badge ${banner.cls}`}>{banner.text}</div>}

      {check?.ok !== false || check?.checked_sql !== '' ? (
        <div>
          <button className="schema-toggle" onClick={toggleSchema}>
            {showSchema ? '▾' : '▸'} 📚 Browse the {summary.jndi} schema
          </button>
          {'  '}
          <button className="schema-toggle" onClick={runPreview} disabled={previewing}>
            {previewing ? '… running' : preview && !preview.error ? '▾ ▶ Run query (first 50 rows)' : '▸ ▶ Run query (first 50 rows)'}
          </button>
          {preview?.error && <p className="muted">preview unavailable — {preview.error}</p>}
          {preview?.columns && (
            <div className="table-scroll data-preview">
              <table>
                <thead>
                  <tr>{preview.columns.map((c) => <th key={c}>{c}</th>)}</tr>
                </thead>
                <tbody>
                  {preview.rows.map((row, i) => (
                    <tr key={i}>{row.map((v, j) => <td key={j}>{v}</td>)}</tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">
                {preview.rows.length} row{preview.rows.length === 1 ? '' : 's'}
                {preview.truncated ? ' (more available — showing the first 50)' : ''} —
                parameters substituted with their defaults
              </p>
            </div>
          )}
          {showSchema && schema === null && <p className="muted">loading…</p>}
          {showSchema && schema?.error && (
            <p className="muted">schema unavailable — {schema.error}</p>
          )}
          {showSchema && schema?.tables && (
            <div className="schema-browser">
              {schema.tables.map((t) => (
                <details key={`${t.schema}.${t.name}`}>
                  <summary>
                    <code>{t.schema}.{t.name}</code>
                    <span className="muted"> · {t.columns.length} columns</span>
                  </summary>
                  <table>
                    <tbody>
                      {t.columns.map((c) => (
                        <tr key={c.name}>
                          <td>
                            <code>{c.name}</code>
                            {c.key?.includes('PK') && <span className="key-badge pk" title="primary key">🔑 PK</span>}
                            {c.key?.includes('FK') && (
                              <span className="key-badge fk" title={`foreign key → ${c.references || ''}`}>
                                → {c.references || 'FK'}
                              </span>
                            )}
                          </td>
                          <td className="muted">{c.type}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </details>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {messages.length > 0 && (
        <div className="sql-chat-log">
          {messages.map((m, i) => (
            <div key={i} className={`sql-chat-msg ${m.role}`}>
              <div className="sql-chat-text">{m.content}</div>
              {m.sql && (
                <div className="sql-chat-proposal">
                  <pre className="sql-pre">{m.sql}</pre>
                  <button
                    className="secondary"
                    disabled={applying || !file}
                    onClick={() => applySql(m.sql)}
                    title="Re-convert this report with the proposed SQL — recorded as a review item in the conversion report"
                  >
                    {applying ? '… re-converting' : 'Apply & re-convert'}
                  </button>
                </div>
              )}
            </div>
          ))}
          <div ref={endRef} />
        </div>
      )}

      <form className="sql-chat-input" onSubmit={ask}>
        <input
          type="text"
          value={question}
          placeholder={`Ask about the ${summary.jndi} schema or this SQL — e.g. "why does this query fail?"`}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={asking}
        />
        <button type="submit" disabled={asking || !question.trim()}>
          {asking ? '…' : '✨ Ask'}
        </button>
      </form>
      {error && <p className="error-text">{error}</p>}
    </div>
  )
}
