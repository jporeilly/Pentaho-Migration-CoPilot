import { useEffect, useState } from 'react'
import Stepper, { REPORT_STEPS } from './components/Stepper.jsx'
import PageNav from './components/PageNav.jsx'
import DocModal from './components/DocModal.jsx'
import SourceBadge from './components/SourceBadge.jsx'
import SettingsPage from './components/SettingsPage.jsx'
import UploadPage from './pages/UploadPage.jsx'
import ProjectPage from './pages/ProjectPage.jsx'
import ParsePage from './pages/ParsePage.jsx'
import MapPage from './pages/MapPage.jsx'
import GeneratePage from './pages/GeneratePage.jsx'
import ValidatePage from './pages/ValidatePage.jsx'
import ReportsInspectPage from './pages/ReportsInspectPage.jsx'
import ReportsFormulasPage from './pages/ReportsFormulasPage.jsx'
import ReportsDownloadPage from './pages/ReportsDownloadPage.jsx'

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
  const [view, setView] = useState('workflow')  // workflow | project | settings
  const [report, setReport] = useState(null)    // reports family: /reports/convert response
  const [reportFile, setReportFile] = useState(null)
  const [crystalSamples, setCrystalSamples] = useState([])

  useEffect(() => {
    fetch('/health')
      .then((r) => r.json())
      .then((h) => setVersion(h.version))
      .catch(() => {})
    fetch('/reports/samples')
      .then((r) => r.json())
      .then((s) => setCrystalSamples(Array.isArray(s) ? s : []))
      .catch(() => {})
  }, [])

  const maxStep = report ? 3 : results.length ? 4 : 0
  const result = results[selected]

  async function convert(file) {
    // an .rpt is a binary the ETL endpoint can never parse - route it
    // straight to the reports pipeline, which extracts it server-side
    if (/\.rpt$/i.test(file.name)) return convertReport(file)
    setError(null)
    setLoading(true)
    try {
      const form = new FormData()
      form.append('export', file)
      const res = await fetch('/convert', { method: 'POST', body: form })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const detail = body.detail || res.statusText
        if (detail.includes('Reports pipeline')) {
          // detect_parser recognized a Crystal RptToXml dump — route it there
          setLoading(false)
          return convertReport(file)
        }
        throw new Error(detail)
      }
      const data = await res.json()
      setReport(null)
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

  async function convertReport(file, jndi = '') {
    setError(null)
    setLoading(true)
    try {
      const form = new FormData()
      form.append('dump', file)
      const res = await fetch(`/reports/convert?jndi=${encodeURIComponent(jndi)}`, {
        method: 'POST',
        body: form,
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || res.statusText)
      setResults([])
      setSource(null)
      setReport(data)
      setReportFile(file)
      setFileName(file.name)
      setStep((s) => (s > 0 && s <= 3 ? s : 1))
    } catch (err) {
      setReport(null)
      setError(err.message)
      setStep(0)
    } finally {
      setLoading(false)
    }
  }

  async function loadSample() {
    const res = await fetch('/sample', { cache: 'no-store' })
    const blob = await res.blob()
    convert(new File([blob], 'm_load_sales.xml', { type: 'text/xml' }))
  }

  async function loadTalendSample() {
    const res = await fetch('/sample-talend', { cache: 'no-store' })
    const blob = await res.blob()
    convert(new File([blob], 'branch_balances_0.1.item', { type: 'text/xml' }))
  }

  async function loadCrystalSample(sample) {
    // default to the account statement when the picker passed nothing
    const name = sample?.name || 'Statement_of_Account'
    const jndi = sample?.jndi || 'Xtreme'
    const res = await fetch(`/reports/sample?name=${encodeURIComponent(name)}`,
                            { cache: 'no-store' })
    const blob = await res.blob()
    // A real harvested report, not an authored dump - its .rpt ships beside it
    // (the filename stem finds it), so the same report opens in the Crystal
    // viewer first, and its generated SQL binds to the datasource it names.
    convertReport(new File([blob], `${name}.xml`, { type: 'text/xml' }), jndi)
  }

  async function openFromProject(row) {
    setError(null)
    setLoading(true)
    setView('workflow')
    try {
      const res = await fetch(
        `/project/open?file=${encodeURIComponent(row.file)}&mapping=${encodeURIComponent(row.mapping)}`,
      )
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || res.statusText)
      setSource(data.source)
      setResults(data.results)
      setFileName(row.file)
      setSelected(0)
      setStep(1)
    } catch (err) {
      setResults([])
      setSource(null)
      setStep(0)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function reset() {
    setResults([])
    setSource(null)
    setReport(null)
    setReportFile(null)
    setFileName('')
    setStep(0)
    setError(null)
  }

  return (
    <div className="app">
      <header className="masthead">
        <h1>
          Pentaho Migration <em>Copilot</em>
          {version && (
            <button className="version" onClick={() => setShowChangelog(true)} title="What's new — view the changelog">
              v{version}
            </button>
          )}
        </h1>
        <span className="links">
          {(report
            ? 'Crystal → PRD'
            : results.length
              ? 'Informatica · Talend → PDI'
              : 'Informatica · Talend → PDI · Crystal → PRD')}{' '}·{' '}
          <a href="/docs" target="_blank" rel="noreferrer">API docs</a> ·{' '}
          <button
            className={`nav${view === 'project' ? ' active' : ''}`}
            onClick={() => setView(view === 'project' ? 'workflow' : 'project')}
          >
            📁 Project
          </button>{' '}
          ·{' '}
          <button
            className={`nav${view === 'settings' ? ' active' : ''}`}
            onClick={() => setView(view === 'settings' ? 'workflow' : 'settings')}
          >
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

      {view === 'settings' ? (
        <SettingsPage onBack={() => setView('workflow')} />
      ) : view === 'project' ? (
        <ProjectPage
          onBack={() => setView('workflow')}
          onOpen={openFromProject}
          context={report ? 'crystal'
            : results.length ? (results[0].pipeline.source_tool === 'talend' ? 'talend' : 'informatica')
            : null}
        />
      ) : (
        <>
          <Stepper step={step} maxStep={maxStep} onStep={setStep} steps={report ? REPORT_STEPS : undefined} />

          {report && (
            <div className="workbench-bar">
              <SourceBadge tool="crystal" />
              <span className="file-chip" title={fileName}>📄 {fileName}</span>
              <span className="score-chip" title="Formula translation: auto / review / manual">
                formulas {report.summary.counts.auto}✓ · {report.summary.counts.review}⚠ · {report.summary.counts.manual}✋
              </span>
              <span className="spacer" />
              <button className="ghost" onClick={reset}>New upload</button>
            </div>
          )}

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
              onTalendSample={loadTalendSample}
              onCrystalSample={loadCrystalSample}
              crystalSamples={crystalSamples}
              error={error}
              loading={loading}
              source={results.length === 0 ? source : null}
              family={report ? 'reports' : results.length ? 'etl' : null}
              onShowPractices={() => setShowPractices(true)}
            />
          )}
          {report ? (
            <>
              {step === 1 && (
                <ReportsInspectPage summary={report.summary} file={reportFile} onUpdate={setReport} />
              )}
              {step === 2 && (
                <ReportsFormulasPage
                  summary={report.summary}
                  file={reportFile}
                  onUpdate={setReport}
                />
              )}
              {step === 3 && (
                <ReportsDownloadPage
                  report={report}
                  file={reportFile}
                  loading={loading}
                  onReconvert={(jndi) => convertReport(reportFile, jndi)}
                />
              )}
              {step > 0 && <PageNav step={step} maxStep={maxStep} onStep={setStep} />}
            </>
          ) : (
            <>
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
          {step === 4 && result && (
            <ValidatePage result={result} source={source} onShowPractices={() => setShowPractices(true)} />
          )}

          {results.length > 0 && step > 0 && (
            <PageNav step={step} maxStep={maxStep} onStep={setStep} />
          )}
            </>
          )}
        </>
      )}
    </div>
  )
}
