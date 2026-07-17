import { useCallback, useEffect, useState } from 'react'

const STATUSES = ['converted', 'in_review', 'verified', 'failed']
const STATUS_ICON = { converted: '·', in_review: '⚠', verified: '✓', failed: '✋' }

export default function ProjectPage({ onBack, onOpen }) {
  const [rows, setRows] = useState(null)

  const refresh = useCallback(async () => {
    const res = await fetch('/project')
    if (res.ok) setRows(await res.json())
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

  if (rows === null) return <p className="loading">Loading project…</p>

  if (!rows.length) {
    return (
      <>
      <button className="ghost back-btn" onClick={onBack}>← Back to workflow</button>
      <section className="card">
        <h2>Migration project</h2>
        <p className="hint-line">
          The project store is empty. Batch-convert a folder of exports first:
        </p>
        <pre className="ktr-pre">pdi-migrate batch samples\informatica</pre>
        <p className="hint-line">
          Every mapping lands here with its confidence score and a review status you
          can track through <em>converted → in review → verified</em>.
        </p>
      </section>
      </>
    )
  }

  const counts = rows.reduce((acc, r) => ({ ...acc, [r.status]: (acc[r.status] || 0) + 1 }), {})
  const avg = Math.round(rows.reduce((n, r) => n + r.score, 0) / rows.length)

  return (
    <>
    <button className="ghost back-btn" onClick={onBack}>← Back to workflow</button>
    <section className="card">
      <header>
        <h2>Migration project <span>{rows.length} mappings · avg confidence {avg}/100</span></h2>
        <button className="ghost" onClick={refresh}>↻ Refresh</button>
      </header>
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
              <th>Status</th><th>Updated</th>
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
    </section>
    </>
  )
}
