import { useEffect, useState } from 'react'
import Stepper from './components/Stepper.jsx'
import PageNav from './components/PageNav.jsx'
import DocModal from './components/DocModal.jsx'
import SourceBadge from './components/SourceBadge.jsx'
import SettingsPage from './components/SettingsPage.jsx'
import UploadPage from './pages/UploadPage.jsx'
import ParsePage from './pages/ParsePage.jsx'
import MapPage from './pages/MapPage.jsx'
import GeneratePage from './pages/GeneratePage.jsx'
import ValidatePage from './pages/ValidatePage.jsx'

export default function App() {
  const [results, setResults] = useState([])
  const [source, setSource] = useState(null)
  const [fileName, setFileName] = useState('')
  const [selected, setSelected] = useState(0)
  const [step, setStep] = useState(0)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [version, setVersion] = useState('')
  const [showChangelog, setShowChangelog] = useState(false)
  const [showPractices, setShowPractices] = useState(false)
  const [showSettings, setShowSettings] = useState(false)

  useEffect(() => {
    fetch('/health')
      .then((r) => r.json())
      .then((h) => setVersion(h.version))
      .catch(() => {})
  }, [])

  const maxStep = results.length ? 4 : 0
  const result = results[selected]

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
      const data = await res.json()
      setSource(data.source)
      setResults(data.results)
      setFileName(file.name)
      setSelected(0)
      if (data.results.length) setStep(1)
    } catch (err) {
      setResults([])
      setSource(null)
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

  function reset() {
    setResults([])
    setSource(null)
    setFileName('')
    setStep(0)
    setError(null)
  }

  return (
    <div className="app">
      <header className="masthead">
        <h1>
          Migration <em>Copilot</em>
          {version && (
            <button className="version" onClick={() => setShowChangelog(true)} title="What's new — view the changelog">
              v{version}
            </button>
          )}
        </h1>
        <span className="links">
          Informatica PowerCenter → Pentaho Data Integration ·{' '}
          <a href="/brief" target="_blank" rel="noreferrer">Technical brief</a> ·{' '}
          <button className="nav" onClick={() => setShowPractices(true)}>📘 Best practices</button>{' '}
          · <a href="/docs">API docs</a> ·{' '}
          <button className={`nav${showSettings ? ' active' : ''}`} onClick={() => setShowSettings(!showSettings)}>
            ⚙ Settings
          </button>
        </span>
      </header>
      {showChangelog && (
        <DocModal title="Changelog" url="/changelog" onClose={() => setShowChangelog(false)} />
      )}
      {showPractices && (
        <DocModal title="Migration best practices" url="/best-practices" onClose={() => setShowPractices(false)} />
      )}

      {showSettings ? (
        <SettingsPage onBack={() => setShowSettings(false)} />
      ) : (
        <>
          <Stepper step={step} maxStep={maxStep} onStep={setStep} />

          {results.length > 0 && (
            <div className="workbench-bar">
              {result && <SourceBadge tool={result.pipeline.source_tool} />}
              <span className="file-chip" title={fileName}>📄 {fileName}</span>
              {result?.score && (
                <span className={`score-chip grade-${result.score.grade}`}
                      title={result.score.verdict}>
                  confidence {result.score.score}/100 · {result.score.grade}
                </span>
              )}
              {results.length > 1 && (
                <label className="mapping-select">
                  Mapping
                  <select value={selected} onChange={(e) => setSelected(Number(e.target.value))}>
                    {results.map((r, i) => (
                      <option key={r.pipeline.name} value={i}>
                        {r.pipeline.name} ({r.pipeline.steps.length} steps)
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <span className="spacer" />
              {results.length > 1 && (
                <button
                  className="ghost"
                  onClick={() =>
                    results.forEach((r) => {
                      const a = document.createElement('a')
                      a.href = URL.createObjectURL(new Blob([r.ktr], { type: 'application/xml' }))
                      a.download = `${r.pipeline.name}.ktr`
                      a.click()
                      URL.revokeObjectURL(a.href)
                    })
                  }
                >
                  ⬇ All .ktr ({results.length})
                </button>
              )}
              <button className="ghost" onClick={reset}>New upload</button>
            </div>
          )}

          {step === 0 && (
            <UploadPage
              onFile={convert}
              onSample={loadSample}
              error={error}
              loading={loading}
              source={results.length === 0 ? source : null}
            />
          )}
          {step === 1 && result && <ParsePage result={result} source={source} />}
          {step === 2 && result && (
            <MapPage
              result={result}
              onUpdate={(updated) =>
                setResults(results.map((r, i) => (i === selected ? updated : r)))
              }
            />
          )}
          {step === 3 && result && <GeneratePage result={result} />}
          {step === 4 && result && <ValidatePage result={result} source={source} />}

          {results.length > 0 && step > 0 && (
            <PageNav step={step} maxStep={maxStep} onStep={setStep} />
          )}
        </>
      )}
    </div>
  )
}
