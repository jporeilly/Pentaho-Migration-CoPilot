import { useState } from 'react'
import StatTiles from '../components/StatTiles.jsx'
import Markdown from '../components/Markdown.jsx'
import { buildMarkdownReport } from '../lib/report.js'
import ScorePanel from '../components/ScorePanel.jsx'
import EffortPanel from '../components/EffortPanel.jsx'
import DiffRunner from '../components/DiffRunner.jsx'

function downloadText(name, content) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([content], { type: 'text/plain' }))
  a.download = name
  a.click()
  URL.revokeObjectURL(a.href)
}

export default function ValidatePage({ result, source, onShowPractices }) {
  const { pipeline, report } = result
  const reviewItems = pipeline.steps.filter((s) => s.confidence !== 'auto')
  const [kit, setKit] = useState(null)
  const [busy, setBusy] = useState(false)

  async function generateKit() {
    setBusy(true)
    try {
      const res = await fetch('/sandbox', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pipeline),
      })
      if (res.ok) setKit(await res.json())
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <header>
        <h2>Migration report <span>{pipeline.name}</span></h2>
        <div className="actions">
          <button
            className="primary"
            onClick={async () => {
              const res = await fetch('/report/pdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source, result, rate: Number(localStorage.getItem('consultantRate')) || 150 }),
              })
              if (!res.ok) return
              const a = document.createElement('a')
              a.href = URL.createObjectURL(await res.blob())
              a.download = `${pipeline.name}.report.pdf`
              a.click()
              URL.revokeObjectURL(a.href)
            }}
          >
            ⬇ Report (.pdf)
          </button>
          <button
            className="ghost"
            onClick={() => downloadText(`${pipeline.name}.report.md`, buildMarkdownReport(source, result))}
          >
            ⬇ Report (.md)
          </button>
          <button
            className="ghost"
            onClick={() => downloadText(`${pipeline.name}.report.json`, JSON.stringify({ source, ...result }, null, 2))}
          >
            .json
          </button>
        </div>
      </header>
      <ScorePanel score={result.score} />
      <EffortPanel effort={result.effort} />
      <StatTiles report={report} />

      <h3 className="subhead">
        Human review checklist{' '}
        <button className="nav" onClick={onShowPractices}>📘 best practices</button>
      </h3>
      {reviewItems.length === 0 ? (
        <p className="hint-line">Every step auto-converted — nothing needs review. 🎉</p>
      ) : (
        <ol className="checklist">
          {reviewItems.map((s) => (
            <li key={s.name}>
              <span className={`badge ${s.confidence}`}>
                {s.confidence === 'review' ? '⚠' : '✋'} {s.confidence}
              </span>
              <div>
                <b>{s.name}</b> <span className="muted">({s.source_type} → {s.pdi_type ?? 'no mapping'})</span>
                <div className="notes">
                  {[
                    ...s.notes,
                    ...s.expressions.map((e) =>
                      e.translated != null
                        ? `Verify translation: ${e.field} = ${e.translated}`
                        : `Translate: ${e.field} = ${e.raw}`,
                    ),
                  ].join('\n')}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}

      <h3 className="subhead">Sandbox test kit</h3>
      <p className="hint-line">
        The converted transformation needs a database connection and tables before it can
        run — <b>always against a sandbox, never production</b>. Generate a kit with a
        PDI setup guide, <code>CREATE TABLE</code> DDL inferred from the export's field
        metadata, and seeded synthetic test data shaped to the real column types.
      </p>
      {!kit ? (
        <button className="primary" onClick={generateKit} disabled={busy}>
          {busy ? 'Generating…' : '🧪 Generate sandbox kit'}
        </button>
      ) : (
        <div className="kit">
          <div className="actions">
            <button className="ghost" onClick={() => downloadText('setup.md', kit.guide)}>
              ⬇ setup.md
            </button>
            <button className="ghost" onClick={() => downloadText('setup.sql', kit.ddl)}>
              ⬇ setup.sql
            </button>
            {Object.entries(kit.data).map(([name, content]) => (
              <button key={name} className="ghost" onClick={() => downloadText(name, content)}>
                ⬇ {name}
              </button>
            ))}
          </div>
          <details className="kit-guide" open>
            <summary>Setup guide</summary>
            <Markdown text={kit.guide} />
          </details>
          <details className="kit-guide">
            <summary>setup.sql</summary>
            <pre className="ktr-pre">{kit.ddl}</pre>
          </details>
        </div>
      )}

      <DiffRunner />
    </section>
  )
}
