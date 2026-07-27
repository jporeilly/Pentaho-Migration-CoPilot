const ETL_STEPS = [
  { label: 'Upload', hint: 'source export',
    tip: 'Drop a PowerCenter .xml or Talend .item export. The source analysis identifies the tool and version and flags migration risks before anything is converted.' },
  { label: 'Parse', hint: 'deterministic',
    tip: 'Real XML parsing — no AI. Extracts steps, fields, expressions, and hops into a normalized model you can inspect as a flow diagram.' },
  { label: 'Map', hint: 'rules + AI',
    tip: 'The rules library maps known transformations 1:1; the LLM only translates expressions. Every decision carries a confidence level, compared side-by-side with the source.' },
  { label: 'Generate', hint: 'PDI .ktr',
    tip: 'Deterministic templating emits an editable PDI transformation that opens in Spoon. Anything unconverted is an explicit TODO, never hidden.' },
  { label: 'Validate', hint: 'review & report',
    tip: 'Migration confidence score, human review checklist, sandbox test kit, and downloadable reports. Nothing auto-deploys.' },
]

export const REPORT_STEPS = [
  { label: 'Upload', hint: '.rpt or dump',
    tip: 'Drop the Crystal .rpt itself (extracted server-side with the free SAP .NET runtime) or an RptToXml .xml dump.' },
  { label: 'Inspect', hint: 'deterministic',
    tip: 'Real XML parsing — no AI. Report structure, bands, data source SQL, parameters, and summaries.' },
  { label: 'Formulas', hint: 'rules + AI',
    tip: 'Crystal formulas translated deterministically to OpenFormula; the LLM assists only with what rules cannot prove, always flagged for review. The original text is preserved — never guessed.' },
  { label: 'Download', hint: 'PRD .prpt',
    tip: 'A native Pentaho Report Designer bundle that opens in PRD, plus a conversion report listing every item that still needs a human.' },
]

export default function Stepper({ step, maxStep, onStep, steps }) {
  const STEPS = steps ?? ETL_STEPS
  return (
    <ol className="stepper">
      {STEPS.map((s, i) => {
        const state = i < step ? 'done' : i === step ? 'active' : i <= maxStep ? 'ready' : 'locked'
        return (
          <li key={s.label} className={state}>
            <button
              disabled={i > maxStep}
              onClick={() => onStep(i)}
              aria-current={i === step ? 'step' : undefined}
              title={s.tip}
            >
              <span className="dot">{i < step ? '✓' : i + 1}</span>
              <span className="step-text">
                <span className="step-label">{s.label}</span>
                <span className="step-hint">{s.hint}</span>
              </span>
            </button>
            {i < STEPS.length - 1 && <span className="bar" aria-hidden="true" />}
          </li>
        )
      })}
    </ol>
  )
}
