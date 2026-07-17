const LEVELS = {
  info:    { icon: 'ℹ', cls: 'info' },
  warning: { icon: '⚠', cls: 'warning' },
  serious: { icon: '⛔', cls: 'serious' },
}

export default function SourceCard({ source }) {
  return (
    <section className="card source-card">
      <header>
        <h2>
          Source analysis
          <span>
            {source.tool} {source.product_version ?? 'unknown version'}
            {source.repository_version && ` · repository ${source.repository_version}`}
          </span>
        </h2>
      </header>

      <dl className="source-facts">
        <div className="pair"><dt>Repository</dt><dd>{source.repository_name ?? '—'}</dd></div>
        <div className="pair"><dt>Database</dt><dd>{source.database_type ?? '—'}</dd></div>
        <div className="pair"><dt>Codepage</dt><dd>{source.codepage ?? '—'}</dd></div>
        <div className="pair"><dt>Exported</dt><dd>{source.creation_date ?? '—'}</dd></div>
        <div className="pair"><dt>Folder(s)</dt><dd>{source.folders.join(', ') || '—'}</dd></div>
        <div className="pair">
          <dt>Contents</dt>
          <dd>
            {source.mappings} mappings · {source.workflows} workflows ·{' '}
            {source.sessions} sessions · {source.mapplets} mapplets
          </dd>
        </div>
      </dl>

      {source.warnings.length > 0 && (
        <ul className="source-warnings">
          {source.warnings.map((w, i) => {
            const level = LEVELS[w.level] ?? LEVELS.info
            return (
              <li key={i} className={level.cls}>
                <span className="w-icon">{level.icon}</span>
                <span className="w-level">{w.level}</span>
                <span className="w-text">{w.text}</span>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
