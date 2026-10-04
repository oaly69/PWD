<template>
  <div>
    <div v-if="!editing" class="presets">
      <span class="muted">快速填充：</span>
      <button v-for="p in PRESETS" :key="p.name" type="button" class="small" @click="applyPreset(p)">{{ p.name }}</button>
    </div>

    <div class="grid-2">
      <label class="field">
        <span>名称</span>
        <input v-model="form.name" placeholder="例如：OpenAI" />
      </label>
      <label class="field">
        <span>类型</span>
        <select v-model="form.kind">
          <option value="openai">OpenAI 兼容接口</option>
          <option value="comfyui">ComfyUI</option>
        </select>
      </label>
    </div>

    <label class="field">
      <span>接口地址</span>
      <input v-model="form.base_url" :placeholder="form.kind === 'comfyui' ? 'http://192.168.1.10:8188' : 'https://api.openai.com/v1'" />
      <div class="hint" v-if="form.kind === 'openai'">一般以 /v1 结尾。容器内访问宿主机服务请使用 http://host.docker.internal:端口</div>
    </label>

    <label class="field">
      <span>API Key <small v-if="form.kind === 'comfyui'" class="muted">（可选）</small></span>
      <input v-model="form.api_key" type="password" autocomplete="new-password" :placeholder="editing ? '留空表示不修改' : 'sk-...'" />
    </label>

    <template v-if="form.kind === 'openai'">
      <label class="field">
        <span>文本模型</span>
        <textarea v-model="chatText" rows="2" placeholder="每行或逗号分隔一个，例如 gpt-4o-mini" />
      </label>
      <label class="field">
        <span>图像模型</span>
        <textarea v-model="imageText" rows="2" placeholder="例如 gpt-image-1、dall-e-3、Kwai-Kolors/Kolors" />
      </label>
    </template>
    <template v-else>
      <label class="field">
        <span>工作流（JSON：{"名称": API 格式工作流}）</span>
        <textarea v-model="workflowText" rows="8" class="mono" spellcheck="false" />
        <div class="hint">
          在 ComfyUI 中通过「导出 (API)」得到工作流 JSON；可用占位符 <code v-pre>{{prompt}} {{negative_prompt}} {{seed}} {{width}} {{height}} {{steps}} {{batch_size}}</code>。
          <a href="#" @click.prevent="loadExample">插入示例工作流</a>
        </div>
        <div v-if="workflowError" class="hint" style="color: var(--danger)">{{ workflowError }}</div>
      </label>
    </template>

    <div v-if="test" class="test-result" :class="test.ok ? 'ok' : 'err'">
      <div>{{ test.message }}</div>
      <div v-if="test.models && test.models.length" class="models">
        <div class="hint">点击模型名称添加：左键加入文本模型，右键加入图像模型</div>
        <span v-for="m in test.models" :key="m" class="tag model" @click="addModel('chat', m)" @contextmenu.prevent="addModel('image', m)">{{ m }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({
  form: { type: Object, required: true },
  editing: { type: Boolean, default: false },
  test: { type: Object, default: null },
})

const PRESETS = [
  { name: 'OpenAI', kind: 'openai', base_url: 'https://api.openai.com/v1', chat_models: ['gpt-4o-mini'], image_models: ['gpt-image-1'] },
  { name: 'DeepSeek', kind: 'openai', base_url: 'https://api.deepseek.com/v1', chat_models: ['deepseek-chat', 'deepseek-reasoner'], image_models: [] },
  { name: '硅基流动', kind: 'openai', base_url: 'https://api.siliconflow.cn/v1', chat_models: ['Qwen/Qwen2.5-7B-Instruct'], image_models: ['Kwai-Kolors/Kolors'] },
  { name: 'OpenRouter', kind: 'openai', base_url: 'https://openrouter.ai/api/v1', chat_models: [], image_models: [] },
  { name: 'Ollama', kind: 'openai', base_url: 'http://host.docker.internal:11434/v1', chat_models: [], image_models: [] },
  { name: 'ComfyUI', kind: 'comfyui', base_url: 'http://host.docker.internal:8188', chat_models: [], image_models: [] },
]

const form = props.form
form.extra = form.extra || {}

const toList = (s) => s.split(/[\n,，]/).map((x) => x.trim()).filter(Boolean)

const chatText = computed({
  get: () => (form.chat_models || []).join('\n'),
  set: (v) => { form.chat_models = toList(v) },
})
const imageText = computed({
  get: () => (form.image_models || []).join('\n'),
  set: (v) => { form.image_models = toList(v) },
})

const workflowText = ref(form.extra.workflows ? JSON.stringify(form.extra.workflows, null, 2) : '')
const workflowError = ref('')
watch(workflowText, (v) => {
  if (!v.trim()) {
    workflowError.value = ''
    form.extra = { ...form.extra, workflows: {} }
    return
  }
  try {
    const parsed = JSON.parse(v)
    if (typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('必须是对象')
    form.extra = { ...form.extra, workflows: parsed }
    workflowError.value = ''
  } catch (e) {
    workflowError.value = `JSON 格式错误：${e.message}`
  }
})

function applyPreset(p) {
  Object.assign(form, { name: p.name, kind: p.kind, base_url: p.base_url, chat_models: [...p.chat_models], image_models: [...p.image_models] })
  if (p.kind === 'comfyui' && !workflowText.value) loadExample()
}

async function loadExample() {
  const data = await api.get('/api/providers/comfyui/example')
  workflowText.value = JSON.stringify(data.workflows, null, 2)
}

function addModel(kind, m) {
  const key = kind === 'chat' ? 'chat_models' : 'image_models'
  if (!form[key].includes(m)) form[key] = [...form[key], m]
}

defineExpose({ hasError: () => !!workflowError.value })
</script>

<style scoped>
.presets { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 14px; }
.mono { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; }
.test-result { padding: 10px 12px; border-radius: 8px; margin-bottom: 14px; font-size: 13px; }
.test-result.ok { background: rgba(47, 163, 107, .12); }
.test-result.err { background: rgba(229, 72, 77, .12); color: var(--danger); }
.models { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; max-height: 160px; overflow: auto; }
.models .hint { width: 100%; }
.tag.model { cursor: pointer; }
.tag.model:hover { background: var(--primary-soft); color: var(--primary); }
</style>
