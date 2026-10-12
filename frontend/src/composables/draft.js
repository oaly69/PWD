import { isRef, onScopeDispose, toRaw, watch } from 'vue'
import { store } from '../store'

// 页面草稿：输入的提示词、参数等自动保存到浏览器，切换页面或刷新后恢复（按用户区分）
const keyOf = (name, session) => `pwd.${session ? 'view' : 'draft'}.${store.user?.id || 0}.${name}`

function storageOf(session) {
  try {
    return session ? window.sessionStorage : window.localStorage
  } catch {
    return null
  }
}

function snapshot(state) {
  const out = {}
  for (const [k, v] of Object.entries(state)) out[k] = toRaw(isRef(v) ? v.value : v)
  return out
}

/**
 * 把一组 ref / reactive 绑定到浏览器存储。
 * state: { 名称: ref 或 reactive 对象 }；session 为 true 时只在当前标签页内保留（适合筛选条件）。
 */
export function useDraft(name, state, { session = false, delay = 300 } = {}) {
  const storage = storageOf(session)
  const key = keyOf(name, session)
  try {
    const saved = JSON.parse(storage?.getItem(key) || 'null')
    if (saved && typeof saved === 'object') {
      for (const [k, target] of Object.entries(state)) {
        if (!(k in saved) || saved[k] === undefined) continue
        if (isRef(target)) target.value = saved[k]
        else if (target && typeof target === 'object' && saved[k] && typeof saved[k] === 'object') Object.assign(target, saved[k])
      }
    }
  } catch { /* 草稿损坏时忽略 */ }

  let timer = null
  const save = () => {
    clearTimeout(timer)
    timer = null
    try { storage?.setItem(key, JSON.stringify(snapshot(state))) } catch { /* 存储已满或不可用 */ }
  }
  // 监听响应式对象本身（toRaw 后的对象不会被追踪）
  watch(() => Object.values(state).map((v) => (isRef(v) ? v.value : v)), () => {
    clearTimeout(timer)
    timer = setTimeout(save, delay)
  }, { deep: true })
  // 离开页面、关闭或刷新前立即写入
  const flush = () => { if (timer) save() }
  window.addEventListener('pagehide', flush)
  onScopeDispose(() => {
    flush()
    window.removeEventListener('pagehide', flush)
  })
  return { save, clear: () => { try { storage?.removeItem(key) } catch { /* 忽略 */ } } }
}
