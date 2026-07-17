const STEPS = [
  { label: 'Upload', hint: 'PowerCenter export' },
  { label: 'Parse', hint: 'deterministic' },
  { label: 'Map', hint: 'rules + AI' },
  { label: 'Generate', hint: 'PDI .ktr' },
  { label: 'Validate', hint: 'review & report' },
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
