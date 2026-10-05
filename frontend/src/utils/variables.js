// 提示词变量：模板中写 {{变量名}} 或 {{变量名|默认值}}，使用模板时弹出表单填写
const RE = /\{\{\s*([^{}|]+?)\s*(?:\|([^{}]*))?\}\}/g

/** 解析模板中的变量，按出现顺序去重。 */
export function parseVariables(text) {
  const seen = new Map()
  for (const m of (text || '').matchAll(RE)) {
    const name = m[1].trim()
    if (!seen.has(name)) seen.set(name, { name, default: (m[2] || '').trim() })
  }
  return [...seen.values()]
}

/** 用填写的值替换变量；未填写的使用默认值，没有默认值则保留变量名。 */
export function fillVariables(text, values) {
  return (text || '').replace(RE, (_, name, def) => {
    const v = (values[name.trim()] || '').trim()
    return v || (def || '').trim() || name.trim()
  })
}
