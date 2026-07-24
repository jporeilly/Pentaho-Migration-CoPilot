import { useCallback, useEffect, useState } from 'react'
import EffortPanel from '../components/EffortPanel.jsx'
import Explain from '../components/Explain.jsx'

const STATUSES = ['converted', 'in_review', 'verified', 'failed']
const STATUS_ICON = { converted: '·', in_review: '⚠', verified: '✓', failed: '✋' }

export default function ProjectPage({ onBack, onOpen }) {
  const [rows, setRows] = useState(null)
  const [reports, setReports] = useState([])

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
        <header><h2>Crystal reports <span>{reports.length} converted</span></h2></header>
        <div className="table-scroll">
          <table className="project-table">
            <thead>
              <tr>
                <th>Report</th><th>Dump file</th>
                <th className="num" title="Formulas translated deterministically">✓ auto</th>
                <th className="num" title="Formulas needing a human glance">⚠ review</th>
                <th className="num" title="Formulas to rebuild by hand">✋ manual</th>
                <th className="num" title="TODO placeholders (subreports, images, conditional formatting)">TODOs</th>
                <th className="num" title="Estimated hours saved vs a manual rebuild">Saved</th>
                <th>Status</th><th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.file}>
                  <td className="cell-clip" title={r.name}>{r.name}</td>
                  <td className="notes cell-clip" title={r.file}>{r.file}</td>
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
              ))}
            </tbody>
          </table>
        </div>
      </section>
    )}
    </>
  )
}
