import { useEffect, useState } from 'react'
import Markdown from './Markdown.jsx'

// Generic document popup: fetches a markdown endpoint and renders it.
export default function DocModal({ title, url, onClose }) {
  const [text, setText] = useState(null)

  useEffect(() => {
    fetch(url)
      .then((r) => r.text())
      .then(setText)
      .catch(() => setText(`Could not load ${title}.`))
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [url, title, onClose])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <h3>{title}</h3>
          <button className="ghost" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="modal-body">
          {text === null ? <p className="loading">Loading…</p> : <Markdown text={text} />}
        </div>
      </div>
    </div>
  )
}
