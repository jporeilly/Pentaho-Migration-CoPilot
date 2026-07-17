import { useState } from 'react'

export default function DropZone({ onFile, onSample }) {
  const [over, setOver] = useState(false)

  return (
    <div className="uploader">
      <label
        className={`drop${over ? ' over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          if (e.dataTransfer.files.length) onFile(e.dataTransfer.files[0])
        }}
      >
        <input
          type="file"
          accept=".xml,.item"
          onChange={(e) => e.target.files.length && onFile(e.target.files[0])}
        />
        Drop a PowerCenter .xml or Talend .item export here, or <strong>browse</strong>
      </label>
      <button className="ghost" onClick={onSample}>Try the sample</button>
    </div>
  )
}
