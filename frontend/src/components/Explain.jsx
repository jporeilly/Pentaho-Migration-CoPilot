// Expandable "what am I looking at?" explanation for a section. Collapsed by
// default so experts aren't slowed down; one click for everyone else.

import { useState } from 'react'

export default function Explain({ label = 'What am I looking at?', children }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="explain">
      <button className="explain-toggle" onClick={() => setOpen(!open)}>
        {open ? '▾' : '▸'} {label}
      </button>
      {open && <div className="explain-body">{children}</div>}
    </div>
  )
}
