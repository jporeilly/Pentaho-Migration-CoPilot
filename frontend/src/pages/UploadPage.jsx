import { useState } from 'react'
import DropZone from '../components/DropZone.jsx'
import SourceCard from '../components/SourceCard.jsx'

const FAMILIES = {
  etl: {
    label: 'ETL → PDI',
    hint: 'PowerCenter · Talend exports',
    stages: [
      { n: 1, name: 'Parse', kind: 'deterministic', text: 'Real XML parsers turn a PowerCenter or Talend export into a normalized step/hop model — no AI, zero failures across the real corpora.' },
      { n: 2, name: 'Map', kind: 'rules + AI', text: 'A rules library maps the clean majority of transformations 1:1 to PDI steps; the LLM only translates expressions it cannot prove, always flagged for review.' },
      { n: 3, name: 'Generate', kind: 'deterministic', text: 'Emits editable .ktr transformations (and .kjb jobs) that open in Spoon. Anything unconverted becomes an explicit TODO in the step description.' },
      { n: 4, name: 'Validate', kind: 'review & report', text: 'Confidence score, impact analysis, sandbox test kit, measured output-parity diff, effort & cost vs a manual rebuild, and a branded PDF report.' },
    ],
  },
  reports: {
    label: 'Crystal → PRD',
    hint: 'SAP Crystal RptToXml dumps',
    stages: [
      { n: 1, name: 'Inspect', kind: 'deterministic', text: 'Parses the RptToXml dump into a banded report model — layout wireframe, data-source SQL, parameters, summaries, and the professional formatting carried from the Crystal source.' },
      { n: 2, name: 'Formulas', kind: 'rules + AI', text: 'Crystal formulas translated to OpenFormula deterministically; the LLM assists the hard ones (variables, running totals), always flagged for review. Never guessed.' },
      { n: 3, name: 'Convert', kind: 'deterministic', text: 'Emits a native .prpt bundle — bands, styles, embedded logo, report functions — verified by loading it through the real Pentaho Reporting engine.' },
      { n: 4, name: 'Download', kind: 'review & report', text: 'The .prpt plus a conversion report listing every review item and TODO, an empty-data PDF preview, and the effort & cost estimate.' },
    ],
  },
}

const PHASES = [
  { name: 'Phase 0 — Internal tool', text: 'Informatica PowerCenter end-to-end, used by Pentaho’s own services team. Complete.' },
  { name: 'Phase 1 — Assisted product', text: 'Exposed to customers with confidence scoring and mandatory human review.' },
  { name: 'Phase 2 — Multi-source', text: 'Talend and SAP Crystal Reports shipped (real-corpus validated); SSIS and DataStage next. You are here.', current: true },
]

export default function UploadPage({ onFile, onSample, onCrystalSample, error, loading, source, onShowPractices }) {
  const [family, setFamily] = useState('etl')
  const fam = FAMILIES[family]

  return (
    <>
      <p className="opportunity">
        Legacy data platforms lock customers in with the sunk cost of thousands of
        hand-built artifacts — ETL mappings and operational reports alike. Migration
        Copilot turns that migration into an assisted effort measured in weeks:
        deterministic parsing where accuracy is non-negotiable, AI only where semantic
        judgment is genuinely required.{' '}
        <a href="/brief" target="_blank" rel="noreferrer">Read the technical brief →</a>
      </p>
      <p className="practices-cta">
        <button className="ghost" onClick={onShowPractices}>📘 Migration best practices</button>
      </p>

      <DropZone onFile={onFile} onSample={onSample} onCrystalSample={onCrystalSample} />
      {error && <div className="error">Conversion failed: {error}</div>}
      {loading && <p className="loading">Converting…</p>}
      {source && <SourceCard source={source} />}

      <div className="family-tabs">
        {Object.entries(FAMILIES).map(([key, f]) => (
          <button
            key={key}
            className={`family-tab${family === key ? ' active' : ''}`}
            onClick={() => setFamily(key)}
          >
            <span className="family-label">{f.label}</span>
            <span className="family-hint">{f.hint}</span>
          </button>
        ))}
      </div>

      <div className="stage-cards">
        {fam.stages.map((s) => (
          <div className="stage-card" key={s.n}>
            <div className="stage-head">
              <span className="stage-n">{s.n}</span>
              <span className="stage-name">{s.name}</span>
              <span className={`stage-kind ${s.kind.startsWith('deterministic') ? 'det' : 'ai'}`}>{s.kind}</span>
            </div>
            <p>{s.text}</p>
          </div>
        ))}
      </div>

      <div className="phase-strip">
        {PHASES.map((p) => (
          <div className={`phase${p.current ? ' current' : ''}`} key={p.name}>
            <b>{p.name}</b>
            <span>{p.text}</span>
          </div>
        ))}
      </div>
    </>
  )
}
