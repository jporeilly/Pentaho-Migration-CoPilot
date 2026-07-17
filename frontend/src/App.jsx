import { useEffect, useState } from 'react'
import DropZone from './components/DropZone.jsx'
import PipelineCard from './components/PipelineCard.jsx'
import ChangelogModal from './components/ChangelogModal.jsx'
import SettingsPage from './components/SettingsPage.jsx'

export default function App() {
  const [results, setResults] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [version, setVersion] = useState('')
  const [showChangelog, setShowChangelog] = useState(false)
  const [view, setView] = useState('convert')

  useEffect(() => {
    fetch('/health')
      .then((r) => r.json())
      .then((h) => setVersion(h.version))
      .catch(() => {})
  }, [])

  async function convert(file) {
    setError(null)
    setLoading(true)
    try {
      const form = new FormData()
      form.append('export', file)
      const res = await fetch('/convert', { method: 'POST', body: form })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || res.statusText)
      }
      setResults(await res.json())
    } catch (err) {
      setResults([])
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadSample() {
    const res = await fetch('/sample')
    const blob = await res.blob()
    convert(new File([blob], 'm_load_sales.xml', { type: 'text/xml' }))
  }

  return (
    <div className="app">
      <header className="masthead">
        <h1>
          Migration <em>Copilot</em>
          {version && (
            <button
              className="version"
              onClick={() => setShowChangelog(true)}
              title="What's new — view the changelog"
            >
              v{version}
            </button>
          )}
        </h1>
        <span className="links">
          Informatica PowerCenter → Pentaho Data Integration · <a href="/docs">API docs</a> ·{' '}
          <button
            className={`nav${view === 'settings' ? ' active' : ''}`}
            onClick={() => setView(view === 'settings' ? 'convert' : 'settings')}
          >
            ⚙ Settings
          </button>
        </span>
      </header>
      {showChangelog && <ChangelogModal onClose={() => setShowChangelog(false)} />}
      <p className="tagline">
        Phase 0 internal tool — parse, map, and generate .ktr with per-step confidence.
      </p>

      {view === 'settings' ? (
        <SettingsPage />
      ) : (
        <>
          <DropZone onFile={convert} onSample={loadSample} />
          {error && <div className="error">Conversion failed: {error}</div>}
          {loading && <p className="loading">Converting…</p>}
          {results.map((r) => (
            <PipelineCard key={r.pipeline.name} result={r} />
          ))}
        </>
      )}
    </div>
  )
}
