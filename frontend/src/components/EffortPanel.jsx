// Effort & cost estimate: remaining work with Copilot vs manual rebuild.
// Hours come from the server (transparent heuristics, listed in assumptions);
// money is hours x rate, chosen here and remembered locally.

import { useState } from 'react'

const money = (h, rate) =>
  (h * rate).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

export default function EffortPanel({ effort }) {
  const [rate, setRate] = useState(() => Number(localStorage.getItem('consultantRate')) || 150)
  const [showWhy, setShowWhy] = useState(false)
  if (!effort) return null

  function updateRate(value) {
    const n = Math.max(Number(value) || 0, 0)
    setRate(n)
    localStorage.setItem('consultantRate', String(n))
  }

  return (
    <div className="effort-panel">
      <div className="effort-head">
        <b>Estimated effort &amp; cost</b>
        <label className="rate-field" title="Blended consultant rate. Typical: $125–$175/h ($1,000–$1,400 per 8h day).">
          rate $
          <input type="number" min="0" step="5" value={rate} onChange={(e) => updateRate(e.target.value)} />
          /h (${(rate * 8).toLocaleString()}/day)
        </label>
      </div>
      <div className="effort-cols">
        <div className="effort-col">
          <div className="effort-hours">{effort.copilot_hours}h</div>
          <div className="effort-label">with Copilot</div>
          <div className="effort-cost">{money(effort.copilot_hours, rate)}</div>
        </div>
        <div className="effort-col">
          <div className="effort-hours">{effort.manual_hours}h</div>
          <div className="effort-label">manual rebuild</div>
          <div className="effort-cost">{money(effort.manual_hours, rate)}</div>
        </div>
        <div className="effort-col saved">
          <div className="effort-hours">−{effort.saved_hours}h</div>
          <div className="effort-label">saved ({effort.saved_pct}%)</div>
          <div className="effort-cost">{money(effort.saved_hours, rate)}</div>
        </div>
      </div>
      <button className="effort-why" onClick={() => setShowWhy(!showWhy)}>
        {showWhy ? 'Hide assumptions' : 'How is this calculated?'}
      </button>
      {showWhy && (
        <ul className="effort-assumptions">
          {effort.assumptions.map((a, i) => <li key={i}>{a}</li>)}
          <li>Static estimate for planning conversations — refine against your own delivery history.</li>
        </ul>
      )}
    </div>
  )
}
