import { useEffect, useState } from 'react'
import Markdown from './Markdown.jsx'

export default function ChangelogModal({ onClose }) {
  const [text, setText] = useState(null)

  useEffect(() => {
    fetch('/changelog')
      .then((r) => r.text())
      .then(setText)
      .catch(() => setText('Could not load the changelog.'))
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Changelog"
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <h3>Changelog</h3>
          <button className="ghost" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="modal-body">
          {text === null ? <p className="loading">Loading…</p> : <Markdown text={text} />}
        </div>
      </div>
    </div>
  )
}
