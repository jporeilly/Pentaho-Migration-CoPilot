// Source-tool identity badge. Lettermark only — vendors' actual logos are
// trademarked; this is our own neutral mark, colored per tool.
const TOOLS = {
  powercenter: { short: 'INFA', label: 'Informatica PowerCenter', color: '#eb6834' },
  ssis: { short: 'SSIS', label: 'SQL Server Integration Services', color: '#3987e5' },
  talend: { short: 'TLND', label: 'Talend', color: '#1baf7a' },
  datastage: { short: 'DS', label: 'IBM DataStage', color: '#9085e9' },
}

export default function SourceBadge({ tool }) {
  const t = TOOLS[tool] ?? { short: 'ETL', label: tool, color: 'var(--text-muted)' }
  return (
    <span className="source-badge" title={t.label}>
      <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
        <rect x="2" y="2" width="14" height="14" rx="4" transform="rotate(45 9 9)" fill={t.color} />
      </svg>
      {t.short}
    </span>
  )
}
