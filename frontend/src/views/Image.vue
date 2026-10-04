<template>
  <div class="image-page">
    <form class="panel card" @submit.prevent="generate">
      <label class="field">
        <span>模型</span>
        <select v-model="modelKey">
          <option value="">选择图像模型…</option>
          <optgroup v-for="p in imageProviders" :key="p.id" :label="p.name">
            <option v-for="m in p.image_models" :key="m" :value="`${p.id}::${m}`">{{ m }}</option>
          </optgroup>
        </select>
        <div v-if="!imageProviders.length" class="hint">暂无可用图像模型，请先在 <router-link to="/providers">模型服务</router-link> 中配置。</div>
      </label>

      <label class="field">
        <span class="row">
          <span class="grow">提示词</span>
          <select v-if="templates.length" class="tpl" @change="useTemplate($event)">
            <option value="">提示词库…</option>
            <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.title }}</option>
          </select>
        </span>
        <textarea v-model="form.prompt" rows="5" required placeholder="描述你想要的画面，例如：一只坐在窗边的橘猫，午后阳光，胶片质感" @keydown.ctrl.enter="generate" @keydown.meta.enter="generate" />
      </label>
      <label class="field">
        <span>反向提示词</span>
        <textarea v-model="form.negative_prompt" rows="2" placeholder="不希望出现的内容（部分模型支持）" />
      </label>

      <div class="field">
        <span class="label">尺寸</span>
        <div class="sizes">
          <button v-for="s in SIZES" :key="s.value" type="button" class="small" :class="{ primary: form.size === s.value }" @click="form.size = s.value">{{ s.label }}</button>
        </div>
        <input v-model="form.size" class="size-input" placeholder="宽x高，如 1024x1024" />
      </div>

      <div class="grid-2">
        <label class="field">
          <span>数量</span>
          <input v-model.number="form.n" type="number" min="1" max="8" />
        </label>
        <label class="field">
          <span>种子</span>
          <input v-model="form.seed" type="number" placeholder="随机" />
        </label>
      </div>

      <details class="field">
        <summary>高级参数</summary>
        <label class="field" v-if="isComfy" style="margin-top: 10px">
          <span>步数</span>
          <input v-model.number="form.steps" type="number" min="1" max="200" />
        </label>
        <label class="field" style="margin-top: 10px">
          <span>额外请求参数（JSON，将合并到请求体）</span>
          <textarea v-model="extraText" rows="3" placeholder='{"quality": "hd", "style": "vivid"}' class="mono" />
        </label>
      </details>

      <div class="row">
        <button type="button" class="ghost small" :disabled="!form.prompt" @click="saveTemplate">存为模板</button>
        <span class="spacer" />
        <button class="primary" :disabled="!modelKey || !form.prompt.trim() || submitting">{{ submitting ? '提交中…' : '生成 (Ctrl+Enter)' }}</button>
      </div>
    </form>

    <section class="results">
      <div class="page-head">
        <h2 style="margin: 0">生成记录</h2>
        <span class="spacer" />
        <router-link to="/gallery">查看作品库 →</router-link>
      </div>
      <div v-if="!tasks.length" class="empty card">还没有生成记录</div>
      <div v-for="t in tasks" :key="t.id" class="card task">
        <div class="row">
          <span class="tag" :class="statusClass(t.status)">{{ STATUS[t.status] }}</span>
          <span class="muted small-text">{{ t.model }} · {{ t.params.size }} · {{ formatTime(t.created_at) }}</span>
          <span class="spacer" />
          <button class="ghost small" @click="reuse(t)">复用参数</button>
          <button v-if="!['pending', 'running'].includes(t.status)" class="ghost small" @click="removeTask(t)">✕</button>
        </div>
        <div class="prompt">{{ t.prompt }}</div>
        <div v-if="t.status === 'failed'" class="error">{{ t.error }}</div>
        <div v-if="['pending', 'running'].includes(t.status)" class="loading">
          <div v-for="i in t.params.n || 1" :key="i" class="ph" />
        </div>
        <div v-else-if="t.assets.length" class="imgs">
          <a v-for="a in t.assets" :key="a.id" :href="a.url" target="_blank"><img :src="a.url" loading="lazy" /></a>
        </div>
      </div>
      <div v-if="hasMore" style="text-align: center"><button @click="loadMore">加载更多</button></div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, formatTime, toast } from '../api'

const SIZES = [
  { label: '1:1', value: '1024x1024' },
  { label: '3:4', value: '768x1024' },
  { label: '4:3', value: '1024x768' },
  { label: '9:16', value: '720x1280' },
  { label: '16:9', value: '1280x720' },
  { label: '竖 2:3', value: '1024x1536' },
  { label: '横 3:2', value: '1536x1024' },
]
const STATUS = { pending: '排队中', running: '生成中', succeeded: '完成', failed: '失败' }
const statusClass = (s) => ({ succeeded: 'ok', failed: 'err', running: 'run', pending: 'run' })[s]

const route = useRoute()
const providers = ref([])
const templates = ref([])
const tasks = ref([])
const hasMore = ref(false)
const submitting = ref(false)
const modelKey = ref('')
const extraText = ref('')
const form = reactive({ prompt: '', negative_prompt: '', size: '1024x1024', n: 1, seed: '', steps: 25 })
let timer = null

const imageProviders = computed(() => providers.value.filter((p) => p.enabled && p.image_models.length))
const isComfy = computed(() => {
  const pid = Number(modelKey.value.split('::')[0])
  return providers.value.find((p) => p.id === pid)?.kind === 'comfyui'
})

function useTemplate(e) {
  const t = templates.value.find((x) => String(x.id) === e.target.value)
  if (t) {
    form.prompt = t.content
    if (t.negative) form.negative_prompt = t.negative
  }
  e.target.value = ''
}

async function saveTemplate() {
  const title = prompt('模板名称', form.prompt.slice(0, 20))
  if (!title) return
  const t = await api.post('/api/prompts', { title, category: 'image', content: form.prompt, negative: form.negative_prompt })
  templates.value.unshift(t)
  toast('已保存到提示词库', 'success')
}

async function generate() {
  if (!modelKey.value || !form.prompt.trim() || submitting.value) return
  let extra
  if (extraText.value.trim()) {
    try {
      extra = JSON.parse(extraText.value)
    } catch {
      return toast('额外请求参数不是合法的 JSON', 'error')
    }
  }
  const [pid, ...rest] = modelKey.value.split('::')
  submitting.value = true
  try {
    const t = await api.post('/api/images/generate', {
      provider_id: Number(pid),
      model: rest.join('::'),
      prompt: form.prompt,
      negative_prompt: form.negative_prompt,
      size: form.size,
      n: form.n || 1,
      seed: form.seed === '' || form.seed === null ? null : Number(form.seed),
      steps: isComfy.value ? form.steps : null,
      extra_body: extra || null,
    })
    tasks.value.unshift(t)
    try { localStorage.setItem('pwd.image.model', modelKey.value) } catch { /* 忽略 */ }
  } finally {
    submitting.value = false
  }
}

function reuse(t) {
  form.prompt = t.prompt
  form.negative_prompt = t.params.negative_prompt || ''
  form.size = t.params.size || '1024x1024'
  form.n = t.params.n || 1
  form.seed = t.params.seed ?? ''
  if (t.params.steps) form.steps = t.params.steps
  extraText.value = t.params.extra_body ? JSON.stringify(t.params.extra_body) : ''
  const key = `${t.provider_id}::${t.model}`
  if (imageProviders.value.some((p) => p.id === t.provider_id && p.image_models.includes(t.model))) modelKey.value = key
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function removeTask(t) {
  await api.del(`/api/tasks/${t.id}`)
  tasks.value = tasks.value.filter((x) => x.id !== t.id)
}

async function loadMore() {
  const more = await api.get(`/api/tasks?kind=image&limit=20&offset=${tasks.value.length}`)
  tasks.value.push(...more)
  hasMore.value = more.length === 20
}

async function poll() {
  const running = tasks.value.filter((t) => ['pending', 'running'].includes(t.status))
  for (const t of running) {
    try {
      const fresh = await api.get(`/api/tasks/${t.id}`, { silent: true })
      Object.assign(t, fresh)
      if (fresh.status === 'failed') toast(`生成失败：${fresh.error}`, 'error', 6000)
    } catch {
      /* 忽略轮询错误 */
    }
  }
}

onMounted(async () => {
  const [ps, tpls, settings] = await Promise.all([
    api.get('/api/providers'),
    api.get('/api/prompts?category=image'),
    api.get('/api/settings'),
  ])
  providers.value = ps
  templates.value = tpls
  let saved = null
  try { saved = localStorage.getItem('pwd.image.model') } catch { /* 忽略 */ }
  const candidates = [saved, settings.default_image_provider_id && `${settings.default_image_provider_id}::${settings.default_image_model}`]
  for (const key of candidates) {
    if (!key) continue
    const [pid, ...rest] = key.split('::')
    if (imageProviders.value.some((p) => p.id === Number(pid) && p.image_models.includes(rest.join('::')))) {
      modelKey.value = key
      break
    }
  }
  if (!modelKey.value && imageProviders.value.length) {
    const p = imageProviders.value[0]
    modelKey.value = `${p.id}::${p.image_models[0]}`
  }
  if (route.query.prompt) form.prompt = String(route.query.prompt)
  if (route.query.negative) form.negative_prompt = String(route.query.negative)
  await loadMore()
  timer = setInterval(poll, 2000)
})

onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.image-page { display: flex; gap: 20px; padding: 24px; align-items: flex-start; }
.panel { width: 380px; flex-shrink: 0; position: sticky; top: 0; }
.results { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.label { display: block; margin-bottom: 6px; font-weight: 500; }
.sizes { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.tpl { width: auto; padding: 2px 6px; font-size: 12px; font-weight: normal; }
.mono { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; }
summary { cursor: pointer; color: var(--muted); }
.task { padding: 14px; }
.small-text { font-size: 12px; }
.prompt { margin: 8px 0; white-space: pre-wrap; word-break: break-word; }
.error { color: var(--danger); font-size: 13px; word-break: break-word; }
.imgs, .loading { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; }
.imgs img { width: 100%; border-radius: 8px; display: block; background: var(--panel-2); }
.ph { aspect-ratio: 1; border-radius: 8px; background: linear-gradient(90deg, var(--panel-2), var(--border), var(--panel-2)); background-size: 200% 100%; animation: shimmer 1.4s infinite; }
@keyframes shimmer { to { background-position: -200% 0; } }
@media (max-width: 900px) {
  .image-page { flex-direction: column; padding: 16px; }
  .panel { width: 100%; position: static; }
}
</style>
