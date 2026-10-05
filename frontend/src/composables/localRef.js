import { ref, watch } from 'vue'

/** 记在 localStorage 中的 ref（读写失败时退化为普通 ref）。 */
export function useLocalRef(key, initial) {
  let value = initial
  try {
    const raw = localStorage.getItem(key)
    if (raw !== null) value = JSON.parse(raw)
  } catch { /* 忽略 */ }
  const r = ref(value)
  watch(r, (v) => {
    try { localStorage.setItem(key, JSON.stringify(v)) } catch { /* 忽略 */ }
  })
  return r
}
