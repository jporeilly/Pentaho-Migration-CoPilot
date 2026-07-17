export default function GeneratePage({ result }) {
  const { pipeline, ktr } = result

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
        <h2>Generated transformation <span>{pipeline.name}.ktr</span></h2>
        <button className="primary" onClick={download}>Download .ktr</button>
      </header>
      <p className="hint-line">
        Opens in Spoon as an editable transformation. Steps marked <em>review</em> or{' '}
        <em>manual</em> carry their notes and TODO expressions in the step description —
        nothing unconverted is hidden.
      </p>
      <pre className="ktr-pre">{ktr}</pre>
    </section>
  )
}
