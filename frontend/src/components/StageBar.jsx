// The staged progress bar every background agent shows: named stages as
// chips, the active one pulsing, finished ones ticked. One component -
// the release gate, the ETL review agent, translation and the project
// sweeps must all read the same way. Counted work (done/total) rides on
// the active chip; `detail` names the item being worked (e.g. the file a
// sweep is on).
export default function StageBar({ stage, stages, done, total, detail }) {
  if (!stages || !stages.length) return null
  const idx = stages.indexOf(stage)
  return (
    <div className="gate-progress">
      {stages.filter((s) => s !== 'done').map((s) => {
        const mine = stages.indexOf(s)
        const counter = mine === idx && total ? ` ${done ?? 0}/${total}` : ''
        return (
          <div
            key={s}
            className={'gate-step' + (mine < idx ? ' done' : mine === idx ? ' active' : '')}
          >
            {mine < idx ? '✓ ' : ''}{s}{counter}
          </div>
        )
      })}
      {detail ? <span className="gate-step-detail">{detail}</span> : null}
    </div>
  )
}
