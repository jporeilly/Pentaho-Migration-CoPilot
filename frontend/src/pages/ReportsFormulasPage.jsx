// Reports flow, step 2: per-formula translation status. Same confidence
// language as the ETL Map page: auto / review / manual, never guessed.

import { useState } from 'react'

const BADGES = { auto: '✓', review: '⚠', manual: '✋' }

const TIPS = {
  auto: 'Translated deterministically to OpenFormula — no review expected.',
  review: 'Translated, but a mapping deserves a human glance (see notes).',
  manual: 'Not mechanically translatable — rebuild by hand in PRD (the original Crystal text is preserved below).',
}

export default function ReportsFormulasPage({ summary }) {
  const [filter, setFilter] = useState('all')
  const formulas = summary.formulas
  const counts = formulas.reduce((acc, f) => {
    acc[f.status] = (acc[f.status] || 0) + 1
    return acc
  }, {})
  const visible = filter === 'all' ? formulas : formulas.filter((f) => f.status === filter)

  return (
    <>
      <h2 className="subhead">Formula translation</h2>

      {formulas.length > 0 ? (
        <>
          <div className="filters">
            <button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>
              All {formulas.length}
            </button>
            {Object.entries(BADGES).map(([key, icon]) => (
              <button key={key} className={filter === key ? 'active' : ''} onClick={() => setFilter(key)}>
                {icon} {key} {counts[key] || 0}
              </button>
            ))}
          </div>

          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Formula</th><th>Status</th><th>Result / notes</th></tr>
              </thead>
              <tbody>
                {visible.map((f) => (
                  <tr key={f.name}>
                    <td className="cell-clip">{'{@'}{f.name}{'}'}</td>
                    <td>
                      <span className={`badge ${f.status}`} title={TIPS[f.status]}>
                        {BADGES[f.status]} {f.status}
                      </span>
                    </td>
                    <td>
                      {f.status === 'manual' ? (
                        <>
                          <span className="muted">{f.notes.join('; ')}</span>
                          <pre className="formula-original">{f.original}</pre>
                        </>
                      ) : (
                        <>
                          <code>{f.translation}</code>
                          {f.notes.length > 0 && (
                            <div className="muted formula-note">{f.notes.join('; ')}</div>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p className="muted">This report has no formulas.</p>
      )}

      {summary.todos.length > 0 && (
        <div className="card">
          <header><h2>Other manual work</h2></header>
          <ul className="notes">
            {summary.todos.map((t, i) => <li key={i}>{t}</li>)}
          </ul>
        </div>
      )}
    </>
  )
}
