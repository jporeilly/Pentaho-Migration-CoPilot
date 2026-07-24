// Reports flow, step 3: download the .prpt bundle + the conversion report.
// The bundle travels base64 in the conversion response; a Blob turns it into
// a real file download client-side.

import { useState } from 'react'
import Markdown from '../components/Markdown.jsx'
import EffortPanel from '../components/EffortPanel.jsx'

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

export default function ReportsDownloadPage({ report, onReconvert, loading }) {
  const [jndi, setJndi] = useState(report.summary.jndi)
  const mdName = report.filename.replace(/\.prpt$/, '.conversion.md')

  return (
    <>
      <EffortPanel effort={report.summary.effort} />
      <div className="card">
        <header><h2>Download</h2></header>
        <div className="actions">
          <button className="primary" onClick={() => downloadBase64(report.prpt_base64, report.filename)}>
            ⬇ {report.filename}
          </button>
          <button className="ghost" onClick={() => downloadText(report.report_markdown, mdName)}>
            ⬇ Conversion report (.md)
          </button>
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
