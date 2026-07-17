export default function PageNav({ step, maxStep, onStep, nextLabel }) {
  return (
    <div className="page-nav">
      {step > 0 ? (
        <button className="ghost" onClick={() => onStep(step - 1)}>← Back</button>
      ) : <span />}
      {step < 4 && step < maxStep && (
        <button className="primary" onClick={() => onStep(step + 1)}>
          {nextLabel ?? 'Next'} →
        </button>
      )}
    </div>
  )
}
