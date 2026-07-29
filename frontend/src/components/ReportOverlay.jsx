import { useRef } from 'react'

// A full-screen viewer for a self-contained HTML report.
//
// Why not just window.open? New browser tabs (window.open AND target=_blank)
// never surface inside embedded webviews — Claude's in-app preview pane, and
// some kiosk/IDE browsers — so the report silently downloaded instead of
// showing. Rendering the HTML in an <iframe srcDoc> works in every real
// browser AND in those panes. Print goes straight to the browser's
// Save-as-PDF, which is how the consultant turns it into a PDF anyway.
export default function ReportOverlay({ html, title = 'Report', filename, onClose }) {
  const frame = useRef(null)

  function print() {
    const win = frame.current && frame.current.contentWindow
    if (win) { win.focus(); win.print() }
  }

  function download() {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
    a.download = filename || 'report.html'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="report-overlay" onClick={onClose}>
      <div className="report-overlay-inner" onClick={(e) => e.stopPropagation()}>
        <div className="report-overlay-bar">
          <span className="report-overlay-title">{title}</span>
          <span className="report-overlay-actions">
            <button className="ghost" onClick={print}>🖨 Print / Save PDF</button>
            {filename && <button className="ghost" onClick={download}>⬇ .html</button>}
            <button className="ghost" onClick={onClose}>✕ Close</button>
          </span>
        </div>
        <iframe ref={frame} title={title} srcDoc={html} className="report-overlay-frame" />
      </div>
    </div>
  )
}
