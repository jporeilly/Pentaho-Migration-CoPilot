import { useState } from 'react'
import StatTiles from '../components/StatTiles.jsx'
import StepsTable from '../components/StepsTable.jsx'
import CompareView from '../components/CompareView.jsx'
import ImpactPanel from '../components/ImpactPanel.jsx'

export default function MapPage({ result, onUpdate }) {
  const { pipeline, report } = result
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState('')
  const [error, setError] = useState(null)

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

  async function translate() {
    setBusy(true)
    setError(null)
    setProgress('starting…')
    try {
      const start = await fetch('/translate/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pipeline),
      })
      const started = await start.json()
      if (!start.ok) throw new Error(started.detail || start.statusText)

      // poll the background job — each poll is its own short request,
      // so long translations can never hit a browser fetch timeout
      for (;;) {
        await sleep(1500)
        const res = await fetch(`/translate/status?job=${started.job}`)
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
    <section className="card">
      <header>
        <h2>Mapping decisions <span>{pipeline.name}</span></h2>
        {report.untranslated_expressions > 0 && (
          <button className="primary" onClick={translate} disabled={busy}>
            {busy
              ? `Translating ${progress}… (local LLM)`
              : `✨ Translate ${report.untranslated_expressions} expressions`}
          </button>
        )}
      </header>
      {error && <div className="error">Translation failed: {error}</div>}
      <p className="hint-line">
        How each source component maps to PDI: source structure above its converted
        counterpart, per-step confidence, and a detailed impact analysis of the
        behavioral differences.
      </p>
      <StatTiles report={report} />
      <CompareView pipeline={pipeline} />
      <StepsTable steps={pipeline.steps} />
      <ImpactPanel impact={result.impact} pipeline={pipeline} />
    </section>
  )
}
