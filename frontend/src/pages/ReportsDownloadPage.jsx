// Reports flow, step 3: download the .prpt bundle + the conversion report.
// The bundle travels base64 in the conversion response; a Blob turns it into
// a real file download client-side.

import { useState } from 'react'
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
  const [prdBusy, setPrdBusy] = useState(false)
  const [prdNote, setPrdNote] = useState(null)
  const mdName = report.filename.replace(/\.prpt$/, '.conversion.md')

  function closePreview() {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(null)
    setPreviewPages(null)
  }

  async function openPdfPreview() {
    setPreviewBusy(true)
    setPreviewError(null)
    try {
      const form = new FormData()
      form.append('dump', file)
      // Pages as images: renders in ANY browser, including embedded panes
      // with no PDF plugin. Falls back to the raw PDF when the server can't
      // rasterize.
      const res = await fetch(`/reports/preview?jndi=${encodeURIComponent(jndi)}&format=pages`, {
        method: 'POST',
        body: form,
      })
      if (res.ok) {
        const body = await res.json()
        setPreviewPages(body.pages)
        setPreviewUrl(null)
        return
      }
      const fallback = await fetch(`/reports/preview?jndi=${encodeURIComponent(jndi)}`, {
        method: 'POST',
        body: form,
      })
      if (!fallback.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || res.statusText)
      }
      const url = URL.createObjectURL(await fallback.blob())
      setPreviewPages(null)
      setPreviewUrl((old) => { if (old) URL.revokeObjectURL(old); return url })
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
          <button className="primary" onClick={() => downloadBase64(report.prpt_base64, report.filename)}>
            ⬇ {report.filename}
          </button>
          <button className="ghost" onClick={() => downloadText(report.report_markdown, mdName)}>
            ⬇ Conversion report (.md)
          </button>
          {file && (
            <button className="ghost" onClick={openPdfPreview} disabled={previewBusy}
              title="Render the .prpt through the real Pentaho Reporting engine with an empty dataset — needs a local Report Designer install">
              {previewBusy ? 'Rendering…' : '🔍 PDF preview'}
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
        {prdNote && <p className="muted">{prdNote}</p>}
        <p className="muted">
          Open the .prpt in Pentaho Report Designer, work through the conversion report
          below, then publish to the Pentaho Server.
        </p>
      </div>

      {(previewPages || previewUrl) && (
        <div className="modal-overlay" onClick={closePreview}>
          <div className="modal pdf-modal" role="dialog" aria-modal="true"
            aria-label="PDF preview" onClick={(e) => e.stopPropagation()}>
            <header>
              <h3>Preview <span className="muted">— rendered by the Pentaho Reporting engine</span></h3>
              <div className="pdf-modal-actions">
                {previewPages && <span className="muted">{previewPages.length} page(s)</span>}
                <button className="ghost" onClick={closePreview} aria-label="Close">✕ Close</button>
              </div>
            </header>
            {previewPages ? (
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
