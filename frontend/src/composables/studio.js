import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { loadProviders, loadSettings, modelOptions, splitModelKey, store } from '../store'

const storageKey = (kind) => `pwd.model.${kind}`

/** 创作工作台的通用逻辑：记住所选模型、处理 ?ref= / ?asset= / ?prompt= 参数。 */
export function useStudio(kind, { onAsset, onRef, onPrompt } = {}) {
  const route = useRoute()
  const router = useRouter()
  const modelKey = ref('')
  const submitting = ref(false)

  function validKey(key) {
    if (!key) return false
    const [pid, model] = splitModelKey(key)
    return modelOptions(kind).some((g) => g.children.some((c) => c.value === `${pid}::${model}`))
  }

  watch(modelKey, (v) => {
    try { if (v) localStorage.setItem(storageKey(kind), v) } catch { /* 忽略 */ }
  })

  const isComfy = () => {
    const [pid] = splitModelKey(modelKey.value)
    return store.providers.find((p) => p.id === pid)?.kind === 'comfyui'
  }
  const currentProvider = () => {
    const [pid] = splitModelKey(modelKey.value)
    return store.providers.find((p) => p.id === pid)
  }

  async function handleQuery() {
    const q = route.query
    if (q.ref) onRef?.(await api.get(`/api/assets/${q.ref}`))
    if (q.asset) onAsset?.(await api.get(`/api/assets/${q.asset}`))
    if (q.prompt) onPrompt?.(String(q.prompt), q.negative ? String(q.negative) : '')
    if (q.ref || q.asset || q.prompt) router.replace({ path: route.path })
  }

  async function submit(body) {
    const [provider_id, model] = splitModelKey(modelKey.value)
    submitting.value = true
    try {
      return await api.post(`/api/generate/${kind}`, { ...body, provider_id, model })
    } finally {
      submitting.value = false
    }
  }

  onMounted(async () => {
    await loadProviders()
    const settings = await loadSettings().catch(() => ({}))
    let saved = null
    try { saved = localStorage.getItem(storageKey(kind)) } catch { /* 忽略 */ }
    const def = settings[`default_${kind}_provider_id`] ? `${settings[`default_${kind}_provider_id`]}::${settings[`default_${kind}_model`]}` : ''
    modelKey.value = [saved, def].find(validKey) || modelOptions(kind)[0]?.children[0]?.value || ''
    await handleQuery()
  })

  watch(() => route.query, (q) => {
    if (q.ref || q.asset || q.prompt) handleQuery()
  })

  return { modelKey, submitting, submit, isComfy, currentProvider }
}
