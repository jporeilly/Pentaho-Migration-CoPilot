import { useState } from 'react'
import StatTiles from '../components/StatTiles.jsx'
import StepsTable from '../components/StepsTable.jsx'

export default function MapPage({ result, onUpdate }) {
  const { pipeline, report } = result
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function translate() {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pipeline),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || res.statusText)
      }
      onUpdate(await res.json())
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <header>
        <h2>Mapping decisions <span>{pipeline.name}</span></h2>
        {report.untranslated_expressions > 0 && (
          <button className="primary" onClick={translate} disabled={busy}>
            {busy
              ? 'Translating… (local LLM, this can take a while)'
              : `✨ Translate ${report.untranslated_expressions} expressions`}
          </button>
        )}
      </header>
      {error && <div className="error">Translation failed: {error}</div>}
      <StatTiles report={report} />
      <StepsTable steps={pipeline.steps} />
    </section>
  )
}
