// Reports flow, step 2: per-formula translation status. Same confidence
// language as the ETL Map page: auto / review / manual, never guessed.

import { useState } from 'react'
import Explain from '../components/Explain.jsx'

const BADGES = { auto: '✓', review: '⚠', manual: '✋' }

const TIPS = {
  auto: 'Translated deterministically to OpenFormula — no review expected.',
  review: 'Translated, but a mapping deserves a human glance (see notes).',
  manual: 'Not mechanically translatable — rebuild by hand in PRD (the original Crystal text is preserved below).',
}

export default function ReportsFormulasPage({ summary, file, onUpdate }) {
  const [filter, setFilter] = useState('all')
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState('')
  const [error, setError] = useState(null)
  const formulas = summary.formulas
  const counts = formulas.reduce((acc, f) => {
    acc[f.status] = (acc[f.status] || 0) + 1
    return acc
  }, {})
  const visible = filter === 'all' ? formulas : formulas.filter((f) => f.status === filter)

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

  async function translate() {
    setBusy(true)
    setError(null)
    setProgress('starting…')
    try {
      const form = new FormData()
      form.append('dump', file)
      const start = await fetch(`/reports/translate/start?jndi=${encodeURIComponent(summary.jndi)}`, {
        method: 'POST',
        body: form,
      })
      const started = await start.json()
      if (!start.ok) throw new Error(started.detail || start.statusText)

      // poll the background job — each poll is its own short request,
      // so long local-LLM runs can never hit a browser fetch timeout
      for (;;) {
        await sleep(1500)
        const res = await fetch(`/reports/translate/status?job=${started.job}`)
        const state = await res.json()
        if (!res.ok) throw new Error(state.detail || res.statusText)
        if (state.status === 'error') throw new Error(state.detail || 'translation failed')
        if (state.status === 'done') {
          onUpdate(state.result)
          break
        }
        if (state.total) setProgress(`${state.done}/${state.total}`)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
      setProgress('')
    }
  }

  return (
    <>
      <div className="reports-formulas-head">
        <h2 className="subhead">Formula translation</h2>
        {counts.manual > 0 && file && (
          <button className="primary" onClick={translate} disabled={busy}>
            {busy
              ? `Translating ${progress}… (local LLM)`
              : `✨ AI-assist ${counts.manual} manual formula${counts.manual > 1 ? 's' : ''}`}
          </button>
        )}
      </div>
      {error && <div className="error">Translation failed: {error}</div>}
      <Explain>
        Crystal formulas are translated to PRD&apos;s <b>OpenFormula</b> language.
        <b> ✓ auto</b> = translated deterministically by rules, no review
        expected. <b>⚠ review</b> = the PRD result shown needs a human glance:
        a translated formula with a caveat, a <b>Select Case</b> rewritten as
        nested IF, or a known idiom (running totals, whole-formula aggregates)
        rebuilt as a <b>report function</b> generated in the bundle — every
        ✨ AI translation also lands here, never higher. <b>✋ manual</b> = not
        mechanically translatable (variables, arrays); the original Crystal
        text is preserved and the notes say what to build instead. The tool
        never guesses: anything uncertain is flagged, not hidden.
      </Explain>

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
                    <td className="cell-status">
                      <span className={`badge ${f.status}`} title={TIPS[f.status]}>
                        {BADGES[f.status]} {f.status}
                      </span>
                    </td>
                    <td>
                      {/* the PRD side: OpenFormula translation, or the report
                          function generated in the bundle */}
                      {f.source === 'llm' && (
                        <div className={`llm-chip conf-${f.llm_confidence}`}
                             title="Translated by the local LLM — the confidence is the model's own estimate; always verify in PRD">
                          ✨ LLM-translated · confidence: {f.llm_confidence}
                        </div>
                      )}
                      {f.prd && (
                        <div>
                          <code>{f.prd}</code>
                          {!f.translation && (
                            <span className="muted"> — report function generated in the bundle (Data tab → Functions in PRD)</span>
                          )}
                        </div>
                      )}
                      {f.notes.length > 0 && (
                        <div className={`muted ${f.prd ? 'formula-note' : ''}`}>
                          {f.notes.join('; ')}
                        </div>
                      )}
                      {/* the Crystal source IS what you review — show it on
                          every row that needs a human (review + manual) */}
                      {f.status !== 'auto' && (
                        <pre className="formula-original">{f.original}</pre>
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
