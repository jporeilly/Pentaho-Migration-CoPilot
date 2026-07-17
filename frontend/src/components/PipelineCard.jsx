import StatTiles from './StatTiles.jsx'
import FlowDiagram from './FlowDiagram.jsx'
import StepsTable from './StepsTable.jsx'

export default function PipelineCard({ result }) {
  const { pipeline, report, ktr } = result

  function download() {
    const blob = new Blob([ktr], { type: 'application/xml' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${pipeline.name}.ktr`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <section className="card">
      <header>
        <h2>
          {pipeline.name}
          <span>{pipeline.source_tool}</span>
        </h2>
        <button className="primary" onClick={download}>Download .ktr</button>
      </header>

      <StatTiles report={report} />
      <FlowDiagram pipeline={pipeline} />
      <StepsTable steps={pipeline.steps} />

      <details className="ktr">
        <summary>Preview generated .ktr XML</summary>
        <pre>{ktr}</pre>
      </details>
    </section>
  )
}
