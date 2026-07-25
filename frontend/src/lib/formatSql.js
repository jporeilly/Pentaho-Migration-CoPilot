// Display-only SQL pretty-printer: one select-list column per line, major
// clauses on their own lines. Never used for the SQL that lands in the
// bundle — purely for readable rendering in the UI.

const CLAUSES = /\s+(FROM|WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|UNION(?:\s+ALL)?|LEFT\s+(?:OUTER\s+)?JOIN|RIGHT\s+(?:OUTER\s+)?JOIN|INNER\s+JOIN|JOIN|AND|ON)\s+/gi

export default function formatSql(sql) {
  if (!sql) return sql
  // flatten existing whitespace so we control the layout
  let s = sql.replace(/\s+/g, ' ').trim()

  // split the select list on top-level commas
  const selMatch = s.match(/^SELECT\s+(DISTINCT\s+)?/i)
  if (selMatch) {
    const head = selMatch[0].trim()
    const rest = s.slice(selMatch[0].length)
    const fromIdx = topLevelIndex(rest, /\bFROM\b/i)
    if (fromIdx > 0) {
      const cols = splitTopLevel(rest.slice(0, fromIdx))
      s = head + '\n  ' + cols.join(',\n  ') + '\n' + rest.slice(fromIdx)
    }
  }
  // major clauses on their own lines (JOIN/AND indented, ON stays inline)
  s = s.replace(CLAUSES, (m, kw) => {
    const upper = kw.toUpperCase().replace(/\s+/g, ' ')
    if (upper === 'ON') return ' ON '
    if (upper === 'AND') return '\n  AND '
    if (upper.endsWith('JOIN')) return '\n' + upper + ' '
    return '\n' + upper + ' '
  })
  return s
}

function topLevelIndex(text, re) {
  let depth = 0
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i]
    if (c === '(') depth += 1
    else if (c === ')') depth -= 1
    else if (depth === 0) {
      const m = text.slice(i).match(re)
      if (m && m.index === 0) return i
    }
  }
  return -1
}

function splitTopLevel(text) {
  const parts = []
  let depth = 0
  let current = ''
  for (const c of text) {
    if (c === '(') depth += 1
    if (c === ')') depth -= 1
    if (c === ',' && depth === 0) {
      parts.push(current.trim())
      current = ''
    } else {
      current += c
    }
  }
  if (current.trim()) parts.push(current.trim())
  return parts
}
