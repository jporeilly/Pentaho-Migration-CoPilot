import StatTiles from '../components/StatTiles.jsx'
import StepsTable from '../components/StepsTable.jsx'

export default function MapPage({ result }) {
  const { pipeline, report } = result
  return (
    <section className="card">
      <header>
        <h2>Mapping decisions <span>{pipeline.name}</span></h2>
      </header>
      <StatTiles report={report} />
      <StepsTable steps={pipeline.steps} />
    </section>
  )
}
