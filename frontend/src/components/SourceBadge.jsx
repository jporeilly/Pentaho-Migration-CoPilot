import { useState } from 'react'

// Source-tool identity badge. If a real logo exists at
// frontend/public/logos/<tool>.png (drop in the official asset — internal
// tool), it is shown; otherwise a neutral lettermark fallback renders.
export const TOOLS = {
  powercenter: { short: 'INFA', label: 'Informatica PowerCenter', color: '#eb6834' },
  talend: { short: 'TLND', label: 'Talend', color: '#1baf7a' },
  datastage: { short: 'DS', label: 'IBM DataStage', color: '#9085e9' },
  crystal: { short: 'CR', label: 'SAP Crystal Reports', color: '#f0ab00' },
  xaction: { short: 'XA', label: 'Pentaho BI Platform (.xaction + .report)', color: '#005f9e' },
}

export const toolLabel = (tool) => TOOLS[tool]?.label ?? tool

export default function SourceBadge({ tool }) {
  const [logoMissing, setLogoMissing] = useState(false)
  const t = TOOLS[tool] ?? { short: 'ETL', label: tool, color: 'var(--text-muted)' }

  return (
    <span className="source-badge" title={t.label}>
      {!logoMissing ? (
        <img
          src={`/logos/${tool}.png`}
          alt={t.label}
          height="20"
          onError={() => setLogoMissing(true)}
        />
      ) : (
        <>
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
            <rect x="2" y="2" width="14" height="14" rx="4" transform="rotate(45 9 9)" fill={t.color} />
          </svg>
          {t.short}
        </>
      )}
    </span>
  )
}
