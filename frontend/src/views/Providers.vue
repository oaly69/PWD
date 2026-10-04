<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>模型服务</h1>
        <div class="sub">接入任意 OpenAI 兼容接口（OpenAI、DeepSeek、硅基流动、阿里百炼、火山方舟、OpenRouter、Ollama、One API / New API…）或 ComfyUI</div>
      </div>
      <span class="spacer" />
      <n-button type="primary" @click="openForm()"><template #icon><Plus :size="16" /></template>添加服务</n-button>
    </div>

    <div class="grid">
      <div v-for="p in store.providers" :key="p.id" class="card" :class="{ off: !p.enabled }">
        <div class="top">
          <div class="logo" :style="{ background: color(p.name) }">{{ p.name.slice(0, 1).toUpperCase() }}</div>
          <div class="name-box">
            <div class="name ellipsis">{{ p.name }}</div>
            <div class="url ellipsis" :title="p.base_url">{{ p.base_url }}</div>
          </div>
          <n-switch :value="p.enabled" size="small" @update:value="toggle(p)" />
        </div>
        <div class="tags">
          <n-tag size="small" :bordered="false">{{ p.kind === 'comfyui' ? 'ComfyUI' : 'OpenAI 兼容' }}</n-tag>
          <n-tag v-if="p.kind === 'openai'" size="small" :bordered="false" :type="p.has_key ? 'success' : 'warning'">{{ p.has_key ? `Key ${p.api_key_masked}` : '未设置 Key' }}</n-tag>
        </div>
        <div class="caps">
          <div v-for="c in CAPS" :key="c.key" class="cap" :class="{ none: !p[c.key]?.length }">
            <component :is="c.icon" :size="14" />
            <span>{{ c.label }}</span>
            <b>{{ p[c.key]?.length || 0 }}</b>
          </div>
        </div>
        <div v-if="results[p.id]" class="result" :class="results[p.id].ok ? 'ok' : 'err'">{{ results[p.id].message }}</div>
        <div class="actions">
          <n-button size="small" secondary :loading="testing[p.id]" @click="test(p)"><template #icon><Zap :size="14" /></template>测试</n-button>
          <n-button size="small" secondary @click="openForm(p)"><template #icon><Pencil :size="14" /></template>编辑</n-button>
          <span class="spacer" />
          <n-button size="small" quaternary type="error" @click="remove(p)"><template #icon><Trash2 :size="14" /></template></n-button>
        </div>
      </div>
    </div>
    <EmptyState v-if="store.providersLoaded && !store.providers.length" :icon="Plug" title="还没有模型服务" desc="添加一个 OpenAI 兼容接口或 ComfyUI 后，即可开始对话、生图、生视频和语音合成。">
      <n-button type="primary" @click="openForm()">添加服务</n-button>
    </EmptyState>

    <n-modal v-model:show="showForm" preset="card" :title="form?.id ? '编辑模型服务' : '添加模型服务'" style="width: min(780px, 96vw)" :segmented="{ content: true, footer: 'soft' }" :mask-closable="false">
      <ProviderForm v-if="form" :key="formKey" ref="pform" :form="form" :editing="!!form.id" :tester="tester" />
      <template #footer>
        <div class="row">
          <n-checkbox v-if="form" v-model:checked="form.enabled">启用</n-checkbox>
          <span class="spacer" />
          <n-button @click="showForm = false">取消</n-button>
          <n-button type="primary" :loading="saving" :disabled="!form?.base_url" @click="save">保存</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { NButton, NCheckbox, NModal, NSwitch, NTag } from 'naive-ui'
import { AudioLines, Film, Image as ImageIcon, MessageSquare, Pencil, Plug, Plus, Trash2, Zap } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import ProviderForm from '../components/ProviderForm.vue'
import { api, confirmDialog, toast } from '../api'
import { loadProviders, store } from '../store'

const CAPS = [
  { key: 'chat_models', label: '对话', icon: MessageSquare },
  { key: 'image_models', label: '图像', icon: ImageIcon },
  { key: 'video_models', label: '视频', icon: Film },
  { key: 'tts_models', label: '语音', icon: AudioLines },
]
const COLORS = ['#6d5dfc', '#2f6fed', '#0f9f8f', '#e0457b', '#d97706', '#7c3aed', '#0891b2', '#65a30d']

const showForm = ref(false)
const form = ref(null)
const formKey = ref(0)
const pform = ref(null)
const saving = ref(false)
const results = reactive({})
const testing = reactive({})

const color = (name) => COLORS[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % COLORS.length]

function openForm(p) {
  formKey.value++
  form.value = reactive(p
    ? { ...JSON.parse(JSON.stringify(p)), api_key: '' }
    : { name: '', kind: 'openai', base_url: '', api_key: '', enabled: true, chat_models: [], image_models: [], video_models: [], tts_models: [], extra: {} })
  showForm.value = true
}

const tester = (payload) => api.post('/api/providers/test-draft', payload)

async function save() {
  const err = pform.value?.validate()
  if (err) return toast(err, 'error')
  const { id, ...body } = form.value
  if (id && !body.api_key) body.api_key = null
  saving.value = true
  try {
    if (id) await api.put(`/api/providers/${id}`, body)
    else await api.post('/api/providers', body)
    showForm.value = false
    toast('已保存', 'success')
    await loadProviders(true)
  } finally {
    saving.value = false
  }
}

async function test(p) {
  testing[p.id] = true
  try {
    results[p.id] = await api.post(`/api/providers/${p.id}/test`)
  } finally {
    testing[p.id] = false
  }
}

async function toggle(p) {
  await api.put(`/api/providers/${p.id}`, { ...p, api_key: null, enabled: !p.enabled })
  await loadProviders(true)
}

async function remove(p) {
  if (!(await confirmDialog({ title: '删除模型服务', content: `确定删除「${p.name}」？使用它的对话需要重新选择模型。`, positiveText: '删除' }))) return
  await api.del(`/api/providers/${p.id}`)
  await loadProviders(true)
}

onMounted(() => loadProviders(true))
</script>

<style scoped>
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 14px; }
.card { padding: 16px; border-radius: 14px; background: var(--panel); border: 1px solid var(--border); display: flex; flex-direction: column; gap: 12px; transition: box-shadow .15s; }
.card:hover { box-shadow: var(--shadow); }
.card.off { opacity: .6; }
.top { display: flex; align-items: center; gap: 12px; }
.logo { width: 42px; height: 42px; border-radius: 12px; color: #fff; font-weight: 700; font-size: 18px; display: grid; place-items: center; flex-shrink: 0; }
.name-box { flex: 1; min-width: 0; }
.name { font-weight: 600; font-size: 15px; }
.url { font-size: 12px; color: var(--muted); }
.tags { display: flex; gap: 6px; flex-wrap: wrap; }
.caps { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
.cap { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 8px 0; border-radius: 10px; background: var(--panel-2); font-size: 12px; color: var(--text-2); }
.cap b { font-size: 15px; color: var(--text); }
.cap.none { opacity: .45; }
.result { font-size: 12.5px; padding: 6px 10px; border-radius: 8px; word-break: break-word; }
.result.ok { background: color-mix(in srgb, var(--success) 12%, transparent); color: var(--success); }
.result.err { background: color-mix(in srgb, var(--danger) 10%, transparent); color: var(--danger); }
.actions { display: flex; gap: 6px; align-items: center; }
</style>
