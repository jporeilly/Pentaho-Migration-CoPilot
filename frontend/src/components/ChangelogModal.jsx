import { useEffect, useState } from 'react'

// Minimal markdown rendering — headings, bullets, bold, inline code, links.
// CHANGELOG.md is our own file, so this doesn't need to be a full parser.
function inline(text, keyBase) {
  const parts = []
  const re = /(\*\*(.+?)\*\*|`(.+?)`|\[(.+?)\]\((.+?)\))/g
  let last = 0
  let m
  let i = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    if (m[2]) parts.push(<strong key={`${keyBase}-${i}`}>{m[2]}</strong>)
    else if (m[3]) parts.push(<code key={`${keyBase}-${i}`}>{m[3]}</code>)
    else if (m[4]) parts.push(<a key={`${keyBase}-${i}`} href={m[5]} target="_blank" rel="noreferrer">{m[4]}</a>)
    last = m.index + m[0].length
    i++
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

function Markdown({ text }) {
  const blocks = []
  text.split('\n').forEach((line, n) => {
    if (line.startsWith('### ')) blocks.push(<h4 key={n}>{inline(line.slice(4), n)}</h4>)
    else if (line.startsWith('## ')) blocks.push(<h3 key={n}>{inline(line.slice(3), n)}</h3>)
    else if (line.startsWith('# ')) blocks.push(<h2 key={n}>{inline(line.slice(2), n)}</h2>)
    else if (line.startsWith('- ')) blocks.push(<li key={n}>{inline(line.slice(2), n)}</li>)
    else if (line.trim()) blocks.push(<p key={n}>{inline(line, n)}</p>)
  })
  return <div className="md">{blocks}</div>
}

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
