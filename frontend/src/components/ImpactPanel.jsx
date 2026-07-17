import { useState } from 'react'
import Markdown from './Markdown.jsx'

const LEVELS = {
  high:   { color: 'var(--status-serious)', icon: '✋' },
  medium: { color: 'var(--status-warning)', icon: '⚠' },
  low:    { color: 'var(--status-good)', icon: '✓' },
  none:   { color: 'var(--text-muted)', icon: '·' },
}

export function scrollToStepRow(name) {
  const row = document.getElementById(`step-row-${name}`)
  if (!row) return
  row.scrollIntoView({ behavior: 'smooth', block: 'center' })
  row.classList.add('flash')
  setTimeout(() => row.classList.remove('flash'), 2000)
}

export function scrollToImpactEntry(name) {
  const entry = document.getElementById(`impact-${name}`)
  if (!entry) return
  entry.open = true
  entry.scrollIntoView({ behavior: 'smooth', block: 'center' })
  entry.classList.add('flash')
  setTimeout(() => entry.classList.remove('flash'), 2000)
}

function SuggestButton({ pipeline, entry }) {
  const [suggestion, setSuggestion] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function ask() {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pipeline, step: entry.step, impact_entry: entry }),
      })
      const body = await res.json()
      if (!res.ok) throw new Error(body.detail || res.statusText)
      setSuggestion(body)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="suggest">
      {!suggestion && (
        <button className="ghost" onClick={ask} disabled={busy}>
          {busy ? '🤖 Thinking… (local LLM)' : '🤖 Suggest a solution'}
        </button>
      )}
      {error && <div className="error">Suggestion failed: {error}</div>}
      {suggestion && (
        <div className="suggestion">
          <div className="suggestion-head">
            <span>🤖 AI-suggested solution</span>
            <span className="muted">{suggestion.model} · advisory — verify before applying</span>
          </div>
          <Markdown text={suggestion.suggestion} />
        </div>
      )}
    </div>
  )
}

export default function ImpactPanel({ impact, pipeline }) {
  const { summary, entries } = impact
  return (
    <div className="impact">
      <h3 className="subhead">
        Impact analysis — {summary.high} high · {summary.medium} medium · {summary.low} low · {summary.none} none
      </h3>

      {summary.top_risks.length > 0 && (
        <ul className="risk-list">
          {summary.top_risks.map((risk, i) => <li key={i}>⚠ {risk}</li>)}
        </ul>
      )}

      {entries.map((e) => {
        const level = LEVELS[e.impact] ?? LEVELS.none
        return (
          <details className="impact-entry" key={e.step} id={`impact-${e.step}`}>
            <summary>
              <span className="impact-badge" style={{ color: level.color }}>
                {level.icon} {e.impact}
              </span>
              <b>{e.step}</b>
              <span className="muted"> — {e.source_type} → {e.pdi_type ?? 'no mapping'}</span>
              <button
                className="nav jump"
                onClick={(ev) => { ev.preventDefault(); scrollToStepRow(e.step) }}
                title="Jump to this step in the table above"
              >
                ↑ step
              </button>
            </summary>
            <div className="impact-body">
              <h4>What converts automatically</h4>
              <ul>{e.converts.map((c, i) => <li key={i}>{c}</li>)}</ul>
              {e.differences.length > 0 && (
                <>
                  <h4>Behavioral differences (source → PDI)</h4>
                  <ul>{e.differences.map((d, i) => <li key={i}>{d}</li>)}</ul>
                </>
              )}
              {e.actions.length > 0 && (
                <>
                  <h4>Required actions</h4>
                  <ul>{e.actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
                </>
              )}
              <SuggestButton pipeline={pipeline} entry={e} />
            </div>
          </details>
        )
      })}
    </div>
  )
}
