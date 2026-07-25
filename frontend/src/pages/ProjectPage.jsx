import React, { useCallback, useEffect, useState } from 'react'
import EffortPanel from '../components/EffortPanel.jsx'
import Explain from '../components/Explain.jsx'

const STATUSES = ['converted', 'in_review', 'verified', 'failed']
const STATUS_ICON = { converted: '·', in_review: '⚠', verified: '✓', failed: '✋' }

const TRIAGE_ICON = { READY: '✓', REVIEW: '⚠', BLOCKED: '✋' }

export default function ProjectPage({ onBack, onOpen }) {
  const [rows, setRows] = useState(null)
  const [reports, setReports] = useState([])
  const [jndi, setJndi] = useState(localStorage.getItem('triageJndi') || '')
  const [triaging, setTriaging] = useState(false)
  const [expanded, setExpanded] = useState(null)     // report file with open detail
  const [parityBusy, setParityBusy] = useState(null) // report file being checked
  const [agentError, setAgentError] = useState('')

  const refresh = useCallback(async () => {
    const res = await fetch('/project')
    if (res.ok) setRows(await res.json())
    const rep = await fetch('/project/reports')
    if (rep.ok) setReports(await rep.json())
  }, [])

  useEffect(() => { refresh() }, [refresh])

  async function updateStatus(row, status) {
    await fetch('/project/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file: row.file, mapping: row.mapping, status }),
    })
    refresh()
  }

  async function updateReportStatus(row, status) {
    await fetch('/project/report-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file: row.file, status }),
    })
    refresh()
  }

  async function runTriage() {
    setTriaging(true)
    setAgentError('')
    localStorage.setItem('triageJndi', jndi)
    try {
      const res = await fetch(`/project/reports/triage?jndi=${encodeURIComponent(jndi)}`,
                              { method: 'POST' })
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText)
      setReports(await res.json())
    } catch (err) {
      setAgentError(`Triage failed: ${err.message}`)
    } finally {
      setTriaging(false)
    }
  }

  async function runParity(row, file) {
    if (!file) return
    setParityBusy(row.file)
    setAgentError('')
    try {
      const body = new FormData()
      body.append('reference', file)
      const res = await fetch(
        `/project/report-parity?file=${encodeURIComponent(row.file)}&jndi=${encodeURIComponent(jndi)}`,
        { method: 'POST', body })
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText)
      refresh()
    } catch (err) {
      setAgentError(`Parity failed for ${row.name}: ${err.message}`)
    } finally {
      setParityBusy(null)
    }
  }

  function triageDetail(row) {
    try {
      return JSON.parse(row.triage_json || '{}')
    } catch {
      return {}
    }
  }

  if (rows === null) return <p className="loading">Loading project…</p>

  if (!rows.length && !reports.length) {
    return (
      <>
      <button className="ghost back-btn" onClick={onBack}>← Back to workflow</button>
      <section className="card">
        <h2>Migration project</h2>
        <p className="hint-line">
          The project store is empty. Batch-convert a folder of exports first:
        </p>
        <pre className="ktr-pre">{'pentaho-migrate batch samples\\informatica\npentaho-migrate report-batch samples\\crystal\\real'}</pre>
        <p className="hint-line">
          Every mapping and report lands here with its metrics and a review status you
          can track through <em>converted → in review → verified</em>.
        </p>
      </section>
      </>
    )
  }

  const counts = rows.reduce((acc, r) => ({ ...acc, [r.status]: (acc[r.status] || 0) + 1 }), {})
  const avg = rows.length ? Math.round(rows.reduce((n, r) => n + r.score, 0) / rows.length) : 0
  const copilotH = Math.round(
    rows.reduce((n, r) => n + (r.copilot_hours || 0), 0)
    + reports.reduce((n, r) => n + (r.copilot_hours || 0), 0))
  const manualH = Math.round(
    rows.reduce((n, r) => n + (r.manual_hours || 0), 0)
    + reports.reduce((n, r) => n + (r.manual_hours || 0), 0))
  const portfolioEffort = manualH > 0 ? {
    copilot_hours: copilotH,
    manual_hours: manualH,
    saved_hours: manualH - copilotH,
    saved_pct: Math.round(((manualH - copilotH) / manualH) * 100),
    assumptions: [
      `Sum of per-artifact estimates: ${rows.length} ETL mapping(s) + ${reports.length} Crystal report(s).`,
      'Per-artifact assumptions are listed on each Validate / Download page.',
      'Typical blended consultant rate $125–$175/h ($1,000–$1,400 per 8h day); adjust the rate to your engagement.',
    ],
  } : null

  return (
    <>
    <button className="ghost back-btn" onClick={onBack}>← Back to workflow</button>
    <section className="card">
      <header>
        <h2>
          Migration project{' '}
          <span>
            {rows.length} mappings{rows.length ? ` · avg confidence ${avg}/100` : ''}
            {reports.length ? ` · ${reports.length} reports` : ''}
          </span>
        </h2>
        <button className="ghost" onClick={refresh}>↻ Refresh</button>
      </header>
      <Explain>
        The whole engagement in one place — every artifact <b>batch-converted</b>
        into the store (<code>pentaho-migrate batch</code> for ETL exports,
        <code> report-batch</code> for Crystal dumps). The effort panel sums the
        per-artifact estimates across <b>both families</b> — the engagement-level
        number. Track each artifact through
        <b> converted → in review → verified</b> as humans work the review
        lists; click an ETL mapping to reopen its full conversion.
      </Explain>
      {portfolioEffort && <EffortPanel effort={portfolioEffort} />}
      {rows.length > 0 && (
        <>
          <p className="summary">
            {STATUSES.map((s) => `${STATUS_ICON[s]} ${s.replace('_', ' ')}: ${counts[s] || 0}`).join(' · ')}
            {' — '}click a mapping to walk through its conversion and reports
          </p>
          <div className="table-scroll">
            <table className="project-table">
              <thead>
                <tr>
                  <th className="num">Score</th><th>Mapping</th><th>Export file</th>
                  <th className="num">Steps</th><th className="num">Auto</th>
                  <th className="num">Review</th><th className="num">Manual</th>
                  <th className="num" title="Estimated hours saved vs a manual rebuild">Saved</th><th>Status</th><th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={`${r.file}:${r.mapping}`}
                    className="row-link"
                    title="Open this mapping in the workflow"
                    onClick={() => onOpen(r)}
                  >
                    <td className="num">
                      <span className={`score-chip grade-${r.grade}`}>{r.score} {r.grade}</span>
                    </td>
                    <td className="cell-clip mapping-link" title={r.mapping}>{r.mapping} →</td>
                    <td className="notes cell-clip" title={r.file}>{r.file}</td>
                    <td className="num">{r.steps}</td>
                    <td className="num">{r.auto}</td>
                    <td className="num">{r.review}</td>
                    <td className="num">{r.manual}</td>
                    <td className="num saved-cell">{r.saved_hours ? `${r.saved_hours}h` : '—'}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <select
                        className="status-select"
                        value={r.status}
                        onChange={(e) => updateStatus(r, e.target.value)}
                      >
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>{s.replace('_', ' ')}</option>
                        ))}
                      </select>
                    </td>
                    <td className="cell-time">{r.updated_at.slice(0, 16)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>

    {reports.length > 0 && (
      <section className="card">
        <header>
          <h2>Crystal reports <span>{reports.length} converted</span></h2>
          <div className="triage-bar">
            <input
              className="jndi-input"
              placeholder="JNDI for SQL check (optional)"
              value={jndi}
              onChange={(e) => setJndi(e.target.value)}
              title="With a JNDI name the triage also EXPLAIN-validates each report's SQL against that live connection"
            />
            <button className="primary" onClick={runTriage} disabled={triaging}>
              {triaging ? 'Triaging…' : '🔎 Run triage'}
            </button>
          </div>
        </header>
        <Explain>
          <b>Run triage</b> sweeps every stored report with the batch-triage
          agent: formula counts, TODO placeholders, <b>layout QA lint</b>
          (page overflow, collisions, font clipping) and — with a JNDI name —
          the report SQL <b>EXPLAIN-validated against the live database</b>.
          Verdicts: <b>✓ READY</b> (convert-and-go), <b>⚠ REVIEW</b> (click
          the chip for the exact review reasons), <b>✋ BLOCKED</b> (SQL fails
          or the dump no longer parses). <b>Parity</b> takes the customer's
          original Crystal export (PDF or CSV) per report and diffs the real
          numbers rendered from the converted .prpt — PASS / NEAR / FAIL.
          Re-run triage after re-converting; verdicts persist in the store.
        </Explain>
        {agentError && <div className="error">{agentError}</div>}
        <div className="table-scroll">
          <table className="project-table">
            <thead>
              <tr>
                <th>Report</th><th>Dump file</th>
                <th title="Batch-triage verdict — click a chip for reasons">Triage</th>
                <th title="Output parity vs the customer's Crystal export (upload PDF/CSV)">Parity</th>
                <th className="num" title="Formulas translated deterministically">✓ auto</th>
                <th className="num" title="Formulas needing a human glance">⚠ review</th>
                <th className="num" title="Formulas to rebuild by hand">✋ manual</th>
                <th className="num" title="TODO placeholders (subreports, images, cross-tabs)">TODOs</th>
                <th className="num" title="Estimated hours saved vs a manual rebuild">Saved</th>
                <th>Status</th><th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => {
                const detail = triageDetail(r)
                const reasons = detail.reasons || []
                return (
                <React.Fragment key={r.file}>
                <tr>
                  <td className="cell-clip" title={r.name}>{r.name}</td>
                  <td className="notes cell-clip" title={r.file}>{r.file}</td>
                  <td>
                    {r.triage_verdict ? (
                      <button
                        className={`triage-chip verdict-${r.triage_verdict.toLowerCase()}`}
                        title={reasons.length ? 'Show review reasons' : 'No findings'}
                        onClick={() => setExpanded(expanded === r.file ? null : r.file)}
                      >
                        {TRIAGE_ICON[r.triage_verdict] || ''} {r.triage_verdict}
                        {reasons.length > 0 && ` (${reasons.length})`}
                      </button>
                    ) : <span className="muted">—</span>}
                  </td>
                  <td>
                    {parityBusy === r.file ? (
                      <span className="muted">checking…</span>
                    ) : r.parity_verdict ? (
                      <span
                        className={`triage-chip parity-${r.parity_verdict.toLowerCase()}`}
                        title={r.parity_note}
                      >
                        {r.parity_verdict}
                      </span>
                    ) : (
                      <label className="parity-upload" title="Upload the customer's Crystal export (PDF or CSV) to diff the numbers">
                        📄 check
                        <input
                          type="file"
                          accept=".pdf,.csv"
                          style={{ display: 'none' }}
                          onChange={(e) => { runParity(r, e.target.files[0]); e.target.value = '' }}
                        />
                      </label>
                    )}
                  </td>
                  <td className="num">{r.formulas_auto}</td>
                  <td className="num">{r.formulas_review}</td>
                  <td className="num">{r.formulas_manual}</td>
                  <td className="num">{r.todos}</td>
                  <td className="num saved-cell">
                    {r.manual_hours > r.copilot_hours
                      ? `${Math.round((r.manual_hours - r.copilot_hours) * 2) / 2}h` : '—'}
                  </td>
                  <td>
                    <select
                      className="status-select"
                      value={r.status}
                      onChange={(e) => updateReportStatus(r, e.target.value)}
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>{s.replace('_', ' ')}</option>
                      ))}
                    </select>
                  </td>
                  <td className="cell-time">{r.updated_at.slice(0, 16)}</td>
                </tr>
                {expanded === r.file && (
                  <tr className="triage-detail-row">
                    <td colSpan={11}>
                      <div className="triage-detail">
                        {detail.sql_status && (
                          <p className={`sql-line sql-${detail.sql_status}`}>
                            SQL vs live DB: <b>{detail.sql_status}</b>
                            {detail.sql_error ? ` — ${detail.sql_error}` : ''}
                          </p>
                        )}
                        {reasons.length ? (
                          <ul>
                            {reasons.map((reason, i) => <li key={i}>{reason}</li>)}
                          </ul>
                        ) : <p className="muted">No findings — ready to hand over.</p>}
                      </div>
                    </td>
                  </tr>
                )}
                </React.Fragment>
              )})}
            </tbody>
          </table>
        </div>
      </section>
    )}
    </>
  )
}
