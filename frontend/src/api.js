import { store } from './store'
import router from './router'

// 由 App.vue 注入 naive-ui 的 message / dialog 实例
export const ui = { message: null, dialog: null, notification: null }

export function toast(content, type = 'info', duration = 3000) {
  if (ui.message) ui.message[type === 'error' ? 'error' : type](content, { duration, keepAliveOnHover: true })
  else console[type === 'error' ? 'error' : 'log'](content)
}

export function confirmDialog({ title = '确认操作', content, positiveText = '确定', type = 'warning' }) {
  return new Promise((resolve) => {
    if (!ui.dialog) return resolve(window.confirm(content))
    ui.dialog[type]({
      title,
      content,
      positiveText,
      negativeText: '取消',
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
      onMaskClick: () => resolve(false),
    })
  })
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
  let resp
  try {
    resp = await fetch(url, opts)
  } catch (e) {
    if (e.name === 'AbortError') throw e
    if (!silent) toast('网络连接失败，请检查服务是否在运行', 'error')
    throw e
  }
  if (raw && resp.ok) return resp
  let data = null
  try {
    data = await resp.json()
  } catch {
    /* 非 JSON 响应 */
  }
  if (!resp.ok) {
    const err = new ApiError(resp.status, errorMessage(data, resp.status))
    if (resp.status === 409 && !url.startsWith('/api/install')) {
      store.site.installed = false
      router.replace('/install')
    } else if (resp.status === 401 && !url.startsWith('/api/auth/')) {
      store.user = null
      router.replace({ path: '/login', query: { next: router.currentRoute.value.fullPath } })
    } else if (!silent) {
      toast(err.message, 'error', 5000)
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

export async function uploadFile(file) {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/api/assets/upload', fd)
}

export async function loadSite() {
  store.site = await api.get('/api/site')
  document.title = store.site.site_name
  return store.site
}
