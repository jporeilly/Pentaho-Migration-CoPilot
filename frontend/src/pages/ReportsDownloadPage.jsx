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
  const mdName = report.filename.replace(/\.prpt$/, '.conversion.md')

  async function openPdfPreview() {
    setPreviewBusy(true)
    setPreviewError(null)
    try {
      const form = new FormData()
      form.append('dump', file)
      const res = await fetch(`/reports/preview?jndi=${encodeURIComponent(jndi)}`, {
        method: 'POST',
        body: form,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || res.statusText)
      }
      const url = URL.createObjectURL(await res.blob())
      window.open(url, '_blank')
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) {
      setPreviewError(err.message)
    } finally {
      setPreviewBusy(false)
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
          steps. <b>👁 PDF preview</b> renders the bundle through the real
          Pentaho Reporting engine with an <b>empty dataset</b> — page setup,
          bands and labels appear exactly as PRD will show them; detail rows are
          empty because no database is attached. Changing the <b>JNDI name</b>
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
              {previewBusy ? 'Rendering…' : '👁 PDF preview'}
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
        {previewError && <div className="error">PDF preview failed: {previewError}</div>}
        <p className="muted">
          Open the .prpt in Pentaho Report Designer, work through the conversion report
          below, then publish to the Pentaho Server.
        </p>
      </div>

      <div className="card">
        <header><h2>Conversion report</h2></header>
        <Markdown text={report.report_markdown} />
      </div>
    </>
  )
}
