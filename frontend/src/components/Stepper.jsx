const STEPS = [
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

export default function Stepper({ step, maxStep, onStep }) {
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
