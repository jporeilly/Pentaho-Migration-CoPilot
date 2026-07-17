import DropZone from '../components/DropZone.jsx'
import SourceCard from '../components/SourceCard.jsx'

const STAGES = [
  { n: 1, name: 'Parse', kind: 'deterministic', text: 'Real XML parsers extract steps, fields, expressions, and hops into a normalized model. No AI, no hallucination risk.' },
  { n: 2, name: 'Map', kind: 'rules + AI', text: 'A rules library maps the clean majority 1:1 to PDI steps; the LLM only translates expressions and ambiguous idioms.' },
  { n: 3, name: 'Generate', kind: 'deterministic', text: 'Emits editable .ktr transformations that open in Spoon — never a black box. Unconverted pieces become explicit TODOs.' },
  { n: 4, name: 'Validate', kind: 'review & report', text: 'Every step gets a confidence level: auto, review, or manual. You always see an honest map of what remains.' },
]

const PHASES = [
  { name: 'Phase 0 — Internal tool', text: 'Informatica PowerCenter, top transformation types; used by Pentaho’s own services team. You are here.', current: true },
  { name: 'Phase 1 — Assisted product', text: 'Exposed to customers with confidence scoring and mandatory human review.' },
  { name: 'Phase 2 — Multi-source', text: 'Add SSIS, then Talend / DataStage; broaden transformation coverage.' },
]

export default function UploadPage({ onFile, onSample, error, loading, source }) {
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

      <DropZone onFile={onFile} onSample={onSample} />
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
