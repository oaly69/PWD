import { Marked } from 'marked'
import { markedHighlight } from 'marked-highlight'
import hljs from 'highlight.js/lib/common'
import DOMPurify from 'dompurify'

const marked = new Marked(
  markedHighlight({
    emptyLangClass: 'hljs',
    langPrefix: 'hljs language-',
    highlight(code, lang) {
      const language = hljs.getLanguage(lang) ? lang : 'plaintext'
      return hljs.highlight(code, { language }).value
    },
  }),
  {
    gfm: true,
    breaks: true,
    renderer: {
      code({ text, lang }) {
        // text 已被 markedHighlight 处理为高亮 HTML
        const label = (lang || 'text').split(/\s/)[0]
        return `<div class="code-block"><div class="code-head"><span>${label}</span><button class="code-copy" type="button">复制</button></div><pre><code class="hljs language-${label}">${text}</code></pre></div>`
      },
    },
  },
)

/** 拆分推理模型在正文中输出的 <think>…</think> 段落。 */
export function splitThink(text) {
  if (!text || !text.startsWith('<think>')) return { think: '', body: text || '' }
  const end = text.indexOf('</think>')
  if (end < 0) return { think: text.slice(7), body: '' }
  return { think: text.slice(7, end).trim(), body: text.slice(end + 8).trimStart() }
}

export function renderMarkdown(text) {
  return DOMPurify.sanitize(marked.parse(text || ''), { ADD_ATTR: ['target'] })
}

/** 事件委托：处理代码块复制按钮。 */
export function handleCodeCopy(e, onCopied) {
  const btn = e.target.closest?.('.code-copy')
  if (!btn) return
  const code = btn.closest('.code-block')?.querySelector('code')?.innerText || ''
  navigator.clipboard?.writeText(code).then(() => {
    btn.textContent = '已复制'
    setTimeout(() => { btn.textContent = '复制' }, 1500)
    onCopied?.()
  })
}
