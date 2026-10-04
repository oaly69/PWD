import { reactive } from 'vue'
import { api } from './api'

export const store = reactive({
  site: { site_name: 'PWD 创作台', installed: true, version: '' },
  user: null,
  providers: [],
  providersLoaded: false,
  settings: null,
  activeTasks: [],
})

export async function loadProviders(force = false) {
  if (store.providersLoaded && !force) return store.providers
  store.providers = await api.get('/api/providers')
  store.providersLoaded = true
  return store.providers
}

export async function loadSettings(force = false) {
  if (store.settings && !force) return store.settings
  store.settings = await api.get('/api/settings')
  return store.settings
}

/** 指定能力（chat/image/video/tts）的可用模型分组，供 n-select 使用。 */
export function modelOptions(kind) {
  const field = `${kind}_models`
  return store.providers
    .filter((p) => p.enabled && (p[field] || []).length)
    .map((p) => ({
      type: 'group',
      label: p.name,
      key: `g${p.id}`,
      children: p[field].map((m) => ({ label: m, value: `${p.id}::${m}`, provider: p })),
    }))
}

export function splitModelKey(key) {
  if (!key) return [null, '']
  const i = key.indexOf('::')
  return [Number(key.slice(0, i)), key.slice(i + 2)]
}

export function providerName(id) {
  return store.providers.find((p) => p.id === id)?.name || ''
}
