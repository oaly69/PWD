import { reactive } from 'vue'
import router from './router'

export const state = reactive({
  site: { site_name: 'PWD 创作台', installed: true, version: '' },
  user: null,
  toasts: [],
})

let toastId = 0
export function toast(message, type = 'info', timeout = 3500) {
  const id = ++toastId
  state.toasts.push({ id, message, type })
  setTimeout(() => {
    const i = state.toasts.findIndex((t) => t.id === id)
    if (i >= 0) state.toasts.splice(i, 1)
  }, timeout)
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

function errorMessage(data, status) {
  if (!data) return `请求失败（HTTP ${status}）`
  if (typeof data.detail === 'string') return data.detail
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('；')
  }
  return data.message || `请求失败（HTTP ${status}）`
}

export async function request(method, url, body, { raw = false, silent = false, signal } = {}) {
  const opts = { method, headers: {}, credentials: 'same-origin', signal }
  if (body instanceof FormData) {
    opts.body = body
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const resp = await fetch(url, opts)
  if (raw && resp.ok) return resp
  let data = null
  try {
    data = await resp.json()
  } catch {
    /* 非 JSON 响应 */
  }
  if (!resp.ok) {
    const err = new ApiError(resp.status, errorMessage(data, resp.status))
    if (resp.status === 409 && url !== '/api/install') {
      state.site.installed = false
      router.replace('/install')
    } else if (resp.status === 401 && !url.startsWith('/api/auth/')) {
      state.user = null
      router.replace({ path: '/login', query: { next: router.currentRoute.value.fullPath } })
    } else if (!silent) {
      toast(err.message, 'error')
    }
    throw err
  }
  return data
}

export const api = {
  get: (url, opts) => request('GET', url, undefined, opts),
  post: (url, body, opts) => request('POST', url, body, opts),
  put: (url, body, opts) => request('PUT', url, body, opts),
  patch: (url, body, opts) => request('PATCH', url, body, opts),
  del: (url, opts) => request('DELETE', url, undefined, opts),
}

/** 读取 SSE 流（POST），对每个 data 事件调用 onEvent。 */
export async function streamPost(url, body, onEvent, signal) {
  const resp = await request('POST', url, body, { raw: true, signal })
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data:')) {
          try {
            onEvent(JSON.parse(line.slice(5).trim()))
          } catch {
            /* 忽略无法解析的片段 */
          }
        }
      }
    }
  }
}

export async function loadSite() {
  state.site = await api.get('/api/site')
  document.title = state.site.site_name
  return state.site
}

export function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { hour12: false })
}
