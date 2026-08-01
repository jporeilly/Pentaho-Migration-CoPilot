// Minimal markdown rendering — headings, bullets, bold, inline code, links,
// fenced code blocks, and pipe tables. Only used for our own generated
// content, so it doesn't need to be a full parser.
function inline(text, keyBase) {
  const parts = []
  const re = /(\*\*(.+?)\*\*|`(.+?)`|\[(.+?)\]\((.+?)\)|\*([^*]+?)\*)/g
  let last = 0
  let m
  let i = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    if (m[2]) parts.push(<strong key={`${keyBase}-${i}`}>{m[2]}</strong>)
    else if (m[3]) parts.push(<code key={`${keyBase}-${i}`}>{m[3]}</code>)
    else if (m[4]) parts.push(<a key={`${keyBase}-${i}`} href={m[5]} target="_blank" rel="noreferrer">{m[4]}</a>)
    else if (m[6]) parts.push(<em key={`${keyBase}-${i}`}>{m[6]}</em>)
    last = m.index + m[0].length
    i++
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

const cells = (row) => row.replace(/^\||\|$/g, '').split('|').map((c) => c.trim())

export default function Markdown({ text }) {
  const blocks = []
  const lines = text.split('\n')
  let n = 0
  while (n < lines.length) {
    const line = lines[n]
    if (line.startsWith('<details>')) {
      // the conversion report's collapsible sections:
      // <details><summary>title</summary> ... </details>
      const t = line.match(/<summary>(.*?)<\/summary>/)
      const inner = []
      n++
      while (n < lines.length && !lines[n].startsWith('</details>')) inner.push(lines[n++])
      n++ // closing tag
      blocks.push(
        <details key={`d${n}`}>
          <summary>{inline(t ? t[1] : 'details', `ds${n}`)}</summary>
          <Markdown text={inner.join('\n')} />
        </details>
      )
      continue
    }
    if (line.startsWith('```')) {
      const code = []
      n++
      while (n < lines.length && !lines[n].startsWith('```')) code.push(lines[n++])
      n++ // closing fence
      blocks.push(<pre key={`c${n}`}>{code.join('\n')}</pre>)
      continue
    }
    if (line.startsWith('|') && lines[n + 1]?.match(/^\|[\s:|-]+\|?$/)) {
      const head = cells(line)
      n += 2
      const rows = []
      while (n < lines.length && lines[n].startsWith('|')) rows.push(cells(lines[n++]))
      blocks.push(
        <div className="table-scroll" key={`t${n}`}>
          <table>
            <thead><tr>{head.map((h, i) => <th key={i}>{inline(h, `th${n}-${i}`)}</th>)}</tr></thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>{r.map((c, ci) => <td key={ci}>{inline(c, `td${n}-${ri}-${ci}`)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }
    if (line.startsWith('### ')) blocks.push(<h4 key={n}>{inline(line.slice(4), n)}</h4>)
    else if (line.startsWith('## ')) blocks.push(<h3 key={n}>{inline(line.slice(3), n)}</h3>)
    else if (line.startsWith('# ')) blocks.push(<h2 key={n}>{inline(line.slice(2), n)}</h2>)
    else if (line.startsWith('- ')) blocks.push(<li key={n}>{inline(line.slice(2), n)}</li>)
    else if (line.startsWith('---')) blocks.push(<hr key={n} />)
    else if (line.trim()) blocks.push(<p key={n}>{inline(line, n)}</p>)
    n++
  }
  return <div className="md">{blocks}</div>
}
