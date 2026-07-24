import DropZone from '../components/DropZone.jsx'
import SourceCard from '../components/SourceCard.jsx'

const STAGES = [
  { n: 1, name: 'Parse', kind: 'deterministic', text: 'Real parsers, no AI: ETL exports become a normalized step/hop model; Crystal RptToXml dumps become a banded report model. Zero failures across all three real corpora.' },
  { n: 2, name: 'Map', kind: 'rules + AI', text: 'Rules libraries map the clean majority 1:1 — PDI steps for ETL, OpenFormula for Crystal formulas. The LLM only translates what rules cannot prove, always flagged for review.' },
  { n: 3, name: 'Generate', kind: 'deterministic', text: 'Editable, native output: .ktr/.kjb that open in Spoon, .prpt bundles verified by loading them through the real Pentaho Reporting engine. Unconverted pieces become explicit TODOs.' },
  { n: 4, name: 'Validate', kind: 'review & report', text: 'Confidence levels on every artifact, effort & cost vs a manual rebuild, output-parity diffs, empty-data PDF previews, and honest review lists of what remains.' },
]

const PHASES = [
  { name: 'Phase 0 — Internal tool', text: 'Informatica PowerCenter end-to-end, used by Pentaho’s own services team. Complete.' },
  { name: 'Phase 1 — Assisted product', text: 'Exposed to customers with confidence scoring and mandatory human review.' },
  { name: 'Phase 2 — Multi-source', text: 'Talend and SAP Crystal Reports shipped (real-corpus validated); SSIS and DataStage next. You are here.', current: true },
]

export default function UploadPage({ onFile, onSample, onCrystalSample, error, loading, source, onShowPractices }) {
  return (
    <>
      <p className="opportunity">
        Legacy ETL platforms lock customers in with the sunk cost of thousands of
        hand-built pipelines — rebuilding 3,000–10,000 mappings by hand is a multi-year,
        seven-figure engagement. Migration Copilot turns that migration into an assisted
        effort measured in weeks: deterministic parsing where accuracy is non-negotiable,
        AI only where semantic judgment is genuinely required.{' '}
        <a href="/brief" target="_blank" rel="noreferrer">Read the technical brief →</a>
      </p>
      <p className="practices-cta">
        <button className="ghost" onClick={onShowPractices}>📘 Migration best practices</button>
      </p>

      <DropZone onFile={onFile} onSample={onSample} onCrystalSample={onCrystalSample} />
      {error && <div className="error">Conversion failed: {error}</div>}
      {loading && <p className="loading">Converting…</p>}
      {source && <SourceCard source={source} />}

      <div className="stage-cards">
        {STAGES.map((s) => (
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
