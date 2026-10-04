<template>
  <div class="page">
    <div class="page-head">
      <h1>模型服务</h1>
      <span class="spacer" />
      <button class="primary" @click="openForm()">＋ 添加服务</button>
    </div>
    <p class="muted" style="margin-top: -8px">
      支持任意 OpenAI 兼容接口（OpenAI、DeepSeek、硅基流动、OpenRouter、Ollama、One API / New API 等）以及 ComfyUI。
    </p>

    <div v-if="!providers.length" class="empty card">还没有模型服务</div>
    <div class="list">
      <div v-for="p in providers" :key="p.id" class="card item" :class="{ disabled: !p.enabled }">
        <div class="row">
          <strong class="grow">{{ p.name }}</strong>
          <span class="tag">{{ p.kind === 'comfyui' ? 'ComfyUI' : 'OpenAI 兼容' }}</span>
          <span v-if="!p.enabled" class="tag err">已停用</span>
        </div>
        <div class="muted url">{{ p.base_url }}</div>
        <div class="muted small-text">Key：{{ p.has_key ? p.api_key_masked : '未设置' }}</div>
        <div v-if="p.chat_models.length" class="models"><span class="label">文本</span><span v-for="m in p.chat_models" :key="m" class="tag">{{ m }}</span></div>
        <div v-if="p.image_models.length" class="models"><span class="label">图像</span><span v-for="m in p.image_models" :key="m" class="tag">{{ m }}</span></div>
        <div v-if="results[p.id]" class="small-text" :style="{ color: results[p.id].ok ? 'var(--success)' : 'var(--danger)' }">{{ results[p.id].message }}</div>
        <div class="row">
          <button class="small" :disabled="testing[p.id]" @click="test(p)">{{ testing[p.id] ? '测试中…' : '测试连接' }}</button>
          <button class="small" @click="toggle(p)">{{ p.enabled ? '停用' : '启用' }}</button>
          <span class="spacer" />
          <button class="small ghost" @click="openForm(p)">编辑</button>
          <button class="small ghost danger" @click="remove(p)">删除</button>
        </div>
      </div>
    </div>

    <div v-if="form" class="modal-mask" @click.self="form = null">
      <form class="card modal" @submit.prevent="save">
        <h2>{{ form.id ? '编辑模型服务' : '添加模型服务' }}</h2>
        <ProviderForm :key="form.id || 'new'" ref="pform" :form="form" :editing="!!form.id" :test="formTest" />
        <div class="row">
          <button v-if="form.id && form.kind === 'openai'" type="button" :disabled="testingForm" @click="fetchModels">{{ testingForm ? '获取中…' : '获取模型列表' }}</button>
          <span class="spacer" />
          <button type="button" @click="form = null">取消</button>
          <button class="primary" :disabled="!form.base_url">保存</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import ProviderForm from '../components/ProviderForm.vue'
import { api, toast } from '../api'

const providers = ref([])
const form = ref(null)
const formTest = ref(null)
const testingForm = ref(false)
const pform = ref(null)
const results = reactive({})
const testing = reactive({})

async function load() {
  providers.value = await api.get('/api/providers')
}

function openForm(p) {
  formTest.value = null
  form.value = p
    ? reactive({ id: p.id, name: p.name, kind: p.kind, base_url: p.base_url, api_key: '', enabled: p.enabled, chat_models: [...p.chat_models], image_models: [...p.image_models], extra: JSON.parse(JSON.stringify(p.extra || {})) })
    : reactive({ name: '', kind: 'openai', base_url: '', api_key: '', enabled: true, chat_models: [], image_models: [], extra: {} })
}

async function save() {
  if (pform.value?.hasError()) return toast('请先修正工作流 JSON', 'error')
  const { id, ...body } = form.value
  if (id && !body.api_key) body.api_key = null // 保持原 Key
  if (id) await api.put(`/api/providers/${id}`, body)
  else await api.post('/api/providers', body)
  form.value = null
  toast('已保存', 'success')
  load()
}

async function fetchModels() {
  testingForm.value = true
  try {
    const r = await api.get(`/api/providers/${form.value.id}/remote-models`)
    formTest.value = { ok: true, message: `发现 ${r.models.length} 个模型`, models: r.models }
  } finally {
    testingForm.value = false
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
  load()
}

async function remove(p) {
  if (!confirm(`删除模型服务「${p.name}」？`)) return
  await api.del(`/api/providers/${p.id}`)
  load()
}

onMounted(load)
</script>

<style scoped>
.list { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }
.item { display: flex; flex-direction: column; gap: 8px; }
.item.disabled { opacity: .65; }
.url { word-break: break-all; font-size: 13px; }
.small-text { font-size: 12px; }
.models { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.models .label { font-size: 12px; color: var(--muted); margin-right: 4px; }
</style>
