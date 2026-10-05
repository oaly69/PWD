// 批量提示词：拆分、通配符展开与文件导入
export const MAX_BATCH = 50

// {猫|狗|兔子} 展开为多条；{{变量}} 是模板变量，不参与展开
const WILDCARD = /(?<!\{)\{([^{}]*\|[^{}]*)\}(?!\})/

/** 把一条提示词中的 {a|b|c} 按笛卡尔积展开，最多 limit 条。 */
export function expandWildcards(text, limit = MAX_BATCH + 1) {
  const m = text.match(WILDCARD)
  if (!m) return [text]
  const head = text.slice(0, m.index)
  const tail = text.slice(m.index + m[0].length)
  const out = []
  for (const opt of m[1].split('|')) {
    for (const rest of expandWildcards(tail, limit - out.length)) {
      out.push(head + opt.trim() + rest)
      if (out.length >= limit) return out
    }
  }
  return out
}

/** 按行（或空行）拆分并展开通配符，去掉空白条目。split: 'line' | 'blank' */
export function parseBatch(text, split = 'line') {
  const parts = split === 'blank' ? (text || '').split(/\n\s*\n/) : (text || '').split('\n')
  const out = []
  for (const p of parts) {
    const t = p.trim()
    if (!t) continue
    for (const x of expandWildcards(t)) {
      out.push(x)
      if (out.length > MAX_BATCH) return out
    }
  }
  return out
}

function csvRows(text) {
  const rows = []
  let row = []
  let cell = ''
  let quoted = false
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++ } else if (ch === '"') quoted = false
      else cell += ch
    } else if (ch === '"') quoted = true
    else if (ch === ',') { row.push(cell); cell = '' } else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++
      row.push(cell); rows.push(row); row = []; cell = ''
    } else cell += ch
  }
  row.push(cell)
  rows.push(row)
  return rows.filter((r) => r.some((c) => c.trim()))
}

/** 从 txt / csv 文件读取提示词：txt 每行一条；csv 取「prompt / 提示词」列，没有则取第一列。 */
export async function readPromptFile(file) {
  const text = (await file.text()).replace(/^﻿/, '')
  if (!/\.csv$/i.test(file.name)) return text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
  const rows = csvRows(text)
  if (!rows.length) return []
  const col = rows[0].findIndex((h) => /^(prompt|提示词)$/i.test(h.trim()))
  const body = col >= 0 ? rows.slice(1) : rows
  // 多行单元格合并为一行，保证「每行一条」
  return body.map((r) => (r[Math.max(col, 0)] || '').replace(/\s*\n\s*/g, ' ').trim()).filter(Boolean)
}
