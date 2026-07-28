// Reports flow, step 3: download the .prpt bundle + the conversion report.
// The bundle travels base64 in the conversion response; a Blob turns it into
// a real file download client-side.

import { useRef, useState } from 'react'
import Markdown from '../components/Markdown.jsx'
import EffortPanel from '../components/EffortPanel.jsx'
import Explain from '../components/Explain.jsx'

function downloadBase64(b64, filename) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([bytes], { type: 'application/zip' }))
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

function downloadHtml(html, filename) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

function downloadPdf(base64, filename) {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }))
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

function downloadText(text, filename) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }))
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

export default function ReportsDownloadPage({ report, file, onReconvert, loading }) {
  const [jndi, setJndi] = useState(report.summary.jndi)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [previewError, setPreviewError] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [previewPages, setPreviewPages] = useState(null)
  const previewToken = useRef(0)
  const [prdBusy, setPrdBusy] = useState(false)
  const [prdNote, setPrdNote] = useState(null)
  const [gateBusy, setGateBusy] = useState(false)
  const [gateStage, setGateStage] = useState(null)   // {stage, stages}
  const [gate, setGate] = useState(null)
  const [gateError, setGateError] = useState(null)
  const mdName = report.filename.replace(/\.prpt$/, '.conversion.md')

  function closePreview() {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(null)
    setPreviewPages(null)
    // a render already in flight must not pop the panel back open behind the
    // consultant after they have dismissed it
    previewToken.current += 1
    setPreviewBusy(false)
  }

  async function openPdfPreview() {
    const token = ++previewToken.current
    setPreviewBusy(true)
    setPreviewError(null)
    try {
      const form = new FormData()
      form.append('dump', file)
      // The PDF itself, so the browser's own viewer gives the WHOLE report
      // with page navigation and the outline panel - which is where the
      // group tree recreated from Crystal actually shows up. Rasterized
      // pages were capped at twelve and had no navigation at all.
      const res = await fetch(`/reports/preview?jndi=${encodeURIComponent(jndi)}`, {
        method: 'POST',
        body: form,
      })
      if (res.ok) {
        const url = URL.createObjectURL(await res.blob())
        if (token !== previewToken.current) { URL.revokeObjectURL(url); return }
        setPreviewPages(null)
        setPreviewUrl((old) => { if (old) URL.revokeObjectURL(old); return url })
        return
      }
      // fallback for a pane with no PDF plugin: pages as images
      const fallback = await fetch(
        `/reports/preview?jndi=${encodeURIComponent(jndi)}&format=pages`,
        { method: 'POST', body: form })
      if (!fallback.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || res.statusText)
      }
      setPreviewUrl(null)
      setPreviewPages((await fallback.json()).pages)
    } catch (err) {
      setPreviewError(err.message)
    } finally {
      setPreviewBusy(false)
    }
  }

  async function openInPrd() {
    setPrdBusy(true)
    setPrdNote(null)
    setPreviewError(null)
    try {
      const form = new FormData()
      form.append('dump', file)
      const res = await fetch(`/reports/open-prd?jndi=${encodeURIComponent(jndi)}`, {
        method: 'POST',
        body: form,
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail || res.statusText)
      setPrdNote(body.embedded_rows
        ? `Report Designer is opening with ${body.embedded_rows.toLocaleString()} embedded data rows - first launch takes a moment.`
        : 'Report Designer is opening - first launch takes a moment.')
    } catch (err) {
      setPreviewError(err.message)
    } finally {
      setPrdBusy(false)
    }
  }

  async function runReleaseCheck() {
    setGateBusy(true)
    setGate(null)
    setPreviewError(null)
    try {
      const form = new FormData()
      form.append('dump', file)
      const rate = localStorage.getItem('consultantRate') || '150'
      const res = await fetch(
        `/reports/release-check/start?jndi=${encodeURIComponent(jndi)}&rate=${encodeURIComponent(rate)}`, {
        method: 'POST',
        body: form,
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail || res.statusText)
      // staged background job - poll for the progress bar
      for (;;) {
        await new Promise((r) => setTimeout(r, 2000))
        const s = await fetch(`/reports/release-check/status?job=${body.job}`)
        const state = await s.json()
        if (!s.ok) throw new Error(state.detail || s.statusText)
        setGateStage({ stage: state.stage, stages: state.stages })
        if (state.status === 'done') { setGate(state.result); break }
        if (state.status === 'error') throw new Error(state.detail || 'release check failed')
      }
    } catch (err) {
      // the check could not run (no original / no viewer on this machine) -
      // say so and UNLOCK the downloads rather than deadlock the user
      setGateError(err.message)
    } finally {
      setGateBusy(false)
      setGateStage(null)
    }
  }

  // Downloads unlock once the release check has COMPLETED - or provably
  // cannot run on this machine (no original / no viewer), in which case
  // blocking forever would just strand the consultant.
  const downloadsLocked = Boolean(file) && !gate && !gateError
  const lockHint = downloadsLocked
    ? 'Run the 🛡 Release check first - downloads unlock when it completes'
    : undefined

  return (
    <>
      <EffortPanel effort={report.summary.effort} />
      <div className="card">
        <header><h2>Download</h2></header>
        <Explain>
          The <b>.prpt</b> is a native Pentaho Report Designer bundle — open it
          in PRD, or publish it to the Pentaho Server once its JNDI connection
          exists there. The <b>conversion report</b> is the work list: every
          formula that needs review, every TODO placeholder, and the datasource
          steps. <b>🔍 PDF preview</b> renders the bundle through the real
          Pentaho Reporting engine in a popup — with the <b>embedded saved
          data</b> when the original .rpt carried its rows, otherwise with an
          empty dataset (layout only). <b>🔍 Open in Report Designer</b>
          launches the converted report straight into PRD on this machine. Changing the <b>JNDI name</b>
          re-converts in place.
        </Explain>
        <div className="actions">
          <button className="primary" disabled={downloadsLocked} title={lockHint}
            onClick={() => downloadBase64(report.prpt_base64, report.filename)}>
            ⬇ {report.filename}
          </button>
          <button className="ghost" disabled={downloadsLocked} title={lockHint}
            onClick={() => downloadText(report.report_markdown, mdName)}>
            ⬇ Conversion report (.md)
          </button>
          {file && (
            <button className="ghost" onClick={openPdfPreview} disabled={previewBusy}
              title="Render the .prpt through the real Pentaho Reporting engine with an empty dataset — needs a local Report Designer install">
              {previewBusy ? 'Rendering…' : '🔍 PDF preview'}
            </button>
          )}
          {file && (
            <button className="ghost" onClick={runReleaseCheck} disabled={gateBusy}
              title="Render the ORIGINAL .rpt and the converted .prpt, compare them, and produce the consultant report - needs the original beside the dump">
              {gateBusy ? 'Comparing…' : '🛡 Release check'}
            </button>
          )}
          {file && (
            <button className="ghost" onClick={openInPrd} disabled={prdBusy}
              title="Convert and open the result straight in the local Pentaho Report Designer (local machine only)">
              {prdBusy ? 'Launching…' : '🔍 Open in Report Designer'}
            </button>
          )}
          <span className="spacer" />
          <label className="jndi-field" title="The JNDI connection name the .prpt will reference on the Pentaho server">
            JNDI datasource
            <input
              value={jndi}
              onChange={(e) => setJndi(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && jndi !== report.summary.jndi && onReconvert(jndi)}
            />
          </label>
          <button
            className="ghost"
            disabled={loading || jndi === report.summary.jndi}
            onClick={() => onReconvert(jndi)}
          >
            {loading ? 'Re-converting…' : 'Apply'}
          </button>
        </div>
        {previewError && <div className="error">{previewError}</div>}
        {gateError && <div className="error">Release check could not run: {gateError} — downloads are unlocked.</div>}
        {prdNote && <p className="muted">{prdNote}</p>}
        {downloadsLocked && (
          <p className="muted">
            🛡 Run the <b>Release check</b> to unlock the downloads — it compares
            the rendered conversion against the original and produces the
            consultant report.
          </p>
        )}
        <p className="muted">
          Open the .prpt in Pentaho Report Designer, work through the conversion report
          below, then publish to the Pentaho Server.
        </p>
      </div>

      {gateStage && (
        <div className="card">
          <header><h2>Release check <span>comparing renders…</span></h2></header>
          <div className="gate-progress">
            {gateStage.stages.filter((s) => s !== 'done').map((s) => {
              const idx = gateStage.stages.indexOf(gateStage.stage)
              const mine = gateStage.stages.indexOf(s)
              return (
                <div key={s}
                  className={'gate-step' + (mine < idx ? ' done' : mine === idx ? ' active' : '')}>
                  {mine < idx ? '✓ ' : ''}{s}
                </div>
              )
            })}
          </div>
          <p className="muted">
            Rendering the original through the SAP viewer and the conversion
            through the Pentaho engine — a minute or two for a long report.
          </p>
        </div>
      )}

      {gate && (
        <div className="card">
          <header>
            <h2>
              Release check{' '}
              <span className={gate.verdict === 'SHIP' ? 'gate-ship' : 'gate-review'}>
                {gate.verdict === 'SHIP' ? '✅ SHIP' : '⚠ REVIEW'}
              </span>
            </h2>
            <div className="actions">
              {gate.consultant_report_html && (
                <button className="primary" onClick={() => downloadHtml(
                  gate.consultant_report_html,
                  report.filename.replace(/\.prpt$/, '.consultant.html'))}>
                  ⬇ Consultant report (.html)
                </button>
              )}
              {gate.consultant_report_pdf && (
                <button className="ghost" onClick={() => downloadPdf(
                  gate.consultant_report_pdf,
                  report.filename.replace(/\.prpt$/, '.consultant.pdf'))}>
                  ⬇ .pdf
                </button>
              )}
              <button className="ghost" onClick={() => downloadText(
                gate.consultant_report_markdown,
                report.filename.replace(/\.prpt$/, '.consultant.md'))}>
                ⬇ .md
              </button>
            </div>
          </header>
          <p className="muted">
            Rendered original ({gate.original_pages} pages, SAP viewer) vs
            converted ({gate.converted_pages} pages, Pentaho engine).
            {gate.groups_checked > 0 &&
              ` Statement pagination: ${gate.groups_matching} of ${gate.groups_checked} groups take the same number of pages as the original` +
              (gate.groups_with_breaks
                ? `, and ${gate.groups_breaking_alike} of ${gate.groups_with_breaks} multi-page ones break in the same place.`
                : '.')}
            {gate.llm_annotated > 0 && ` ${gate.llm_annotated} finding(s) annotated by the LLM.`}
          </p>
          {gate.findings.length === 0 ? (
            <p className="muted">No differences above threshold.</p>
          ) : (
            <ul className="notes">
              {gate.findings.map((f, i) => (
                <li key={i}>
                  <b>{f.severity === 'error' ? '✋' : f.severity === 'warning' ? '⚠' : 'ℹ'} [{f.code}]</b> {f.message}
                  {f.resolution && <div className="gate-resolution">→ {f.resolution}</div>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {(previewBusy || previewPages || previewUrl) && (
        <div className="modal-overlay" onClick={closePreview}>
          <div className="modal pdf-modal" role="dialog" aria-modal="true"
            aria-label="PDF preview" onClick={(e) => e.stopPropagation()}>
            <header>
              <h3>Preview <span className="muted">— rendered by the Pentaho Reporting engine</span></h3>
              <div className="pdf-modal-actions">
                {previewPages && (
                  <span className="muted">
                    first {previewPages.length} page(s) — this browser has no
                    inline PDF viewer, so there is no outline panel
                  </span>
                )}
                <button className="ghost" onClick={closePreview} aria-label="Close">✕ Close</button>
              </div>
            </header>
            {previewBusy && !previewUrl && !previewPages ? (
              <div className="pdf-rendering">
                <span className="spinner" aria-hidden="true" />
                <p>Rendering through the Pentaho Reporting engine…</p>
                <p className="muted">
                  The whole report, with its data — a few seconds.
                </p>
              </div>
            ) : previewPages ? (
              <div className="pdf-pages">
                {previewPages.map((src, i) => (
                  <img key={i} src={src} alt={`page ${i + 1}`} loading="lazy" />
                ))}
              </div>
            ) : (
              <object className="pdf-frame" data={previewUrl} type="application/pdf"
                aria-label="PDF preview">
                <div className="pdf-fallback">
                  <p>This browser can't display PDFs inline.</p>
                  <p>
                    <a className="pdf-open-tab" href={previewUrl} target="_blank" rel="noreferrer">
                      ↗ Open the PDF in a tab
                    </a>
                  </p>
                </div>
              </object>
            )}
          </div>
        </div>
      )}

      <div className="card">
        <header><h2>Conversion report</h2></header>
        <Markdown text={report.report_markdown} />
      </div>
    </>
  )
}
