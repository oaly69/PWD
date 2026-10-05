<template>
  <div class="pform">
    <div v-if="!editing" class="presets">
      <span class="muted">快速填充</span>
      <button v-for="p in PROVIDER_PRESETS" :key="p.name" type="button" class="preset" :class="{ active: form.name === p.name }" @click="applyPreset(p)">{{ p.name }}</button>
    </div>

    <div class="grid2">
      <div>
        <div class="field-label">名称</div>
        <n-input v-model:value="form.name" placeholder="例如：OpenAI" />
      </div>
      <div>
        <div class="field-label">类型</div>
        <n-radio-group v-model:value="form.kind" class="kind-seg">
          <n-radio-button value="openai">OpenAI 兼容</n-radio-button>
          <n-radio-button value="comfyui">ComfyUI</n-radio-button>
        </n-radio-group>
      </div>
    </div>

    <div class="field">
      <div class="field-label">接口地址</div>
      <n-input v-model:value="form.base_url" :placeholder="form.kind === 'comfyui' ? 'http://192.168.1.10:8188' : 'https://api.openai.com/v1'" />
      <div class="hint">{{ form.kind === 'openai' ? '一般以 /v1 结尾。' : 'ComfyUI 需以 --listen 启动。' }}容器内访问宿主机服务请使用 http://host.docker.internal:端口</div>
    </div>

    <div class="field">
      <div class="field-label">API Key <span v-if="form.kind === 'comfyui'" class="muted">（可选）</span></div>
      <n-input v-model:value="form.api_key" type="password" show-password-on="click" :placeholder="editing ? '留空表示不修改' : 'sk-...'" :input-props="{ autocomplete: 'new-password' }" />
    </div>

    <template v-if="form.kind === 'openai'">
      <div class="models-head">
        <div class="field-label" style="margin: 0">模型</div>
        <span class="spacer" />
        <n-button size="small" secondary :loading="testing" :disabled="!form.base_url" @click="fetchModels">
          <template #icon><RefreshCw :size="14" /></template>获取模型列表
        </n-button>
        <n-button v-if="classified" size="small" secondary @click="autoFill"><template #icon><Wand2 :size="14" /></template>自动分类填入</n-button>
      </div>
      <div v-if="result" class="result" :class="result.ok ? 'ok' : 'err'">{{ result.message }}</div>
      <div class="model-grid">
        <div v-for="cap in CAPS" :key="cap.key">
          <div class="cap-label"><component :is="cap.icon" :size="14" /> {{ cap.label }}<span v-if="form[cap.key].length" class="muted">（{{ form[cap.key].length }}）</span></div>
          <n-select
            v-model:value="form[cap.key]"
            multiple
            filterable
            tag
            :options="remoteOptions"
            :placeholder="cap.placeholder"
          />
        </div>
      </div>

      <n-collapse class="adv">
        <n-collapse-item title="高级设置" name="adv">
          <div class="grid2">
            <div>
              <div class="field-label">图生图方式</div>
              <n-select v-model:value="extra.image_edit_mode" :options="EDIT_MODES" />
            </div>
            <div>
              <div class="field-label">视频接口风格</div>
              <n-select v-model:value="extra.video_api" :options="VIDEO_APIS" />
            </div>
          </div>
          <div class="field">
            <div class="field-label">自定义请求头 <span class="muted">JSON</span></div>
            <n-input v-model:value="headersText" type="textarea" class="mono" :autosize="{ minRows: 2, maxRows: 5 }" placeholder='{"HTTP-Referer": "https://example.com"}' />
            <div v-if="headersError" class="hint err">{{ headersError }}</div>
          </div>
        </n-collapse-item>
      </n-collapse>
    </template>

    <template v-else>
      <div class="models-head">
        <div class="field-label" style="margin: 0">工作流</div>
        <span class="spacer" />
        <n-button size="small" secondary :loading="testing" :disabled="!form.base_url" @click="fetchModels">测试连接</n-button>
        <n-dropdown trigger="click" :options="EXAMPLES" @select="addExample">
          <n-button size="small" secondary><template #icon><Plus :size="14" /></template>示例工作流</n-button>
        </n-dropdown>
        <n-button size="small" secondary @click="importInput?.click()"><template #icon><Upload :size="14" /></template>导入 JSON</n-button>
        <input ref="importInput" type="file" accept=".json,application/json" hidden @change="importFile" />
      </div>
      <div v-if="result" class="result" :class="result.ok ? 'ok' : 'err'">{{ result.message }}</div>
      <div class="hint" style="margin-bottom: 10px">
        在 ComfyUI 中使用「导出 (API)」得到工作流 JSON。可用占位符：<code v-pre>{{prompt}} {{negative_prompt}} {{seed}} {{width}} {{height}} {{steps}} {{batch_size}} {{image}} {{mask}} {{scale}}</code>。image 为参考图 / 待编辑图的文件名，配合 LoadImage 节点使用（局部重绘时重绘区域为透明，LoadImage 的 MASK 输出即为蒙版）；mask 为白色=重绘区域的蒙版图；scale 为放大倍数。
      </div>
      <div v-for="(w, i) in workflows" :key="w.uid" class="wf">
        <div class="wf-head">
          <n-input v-model:value="w.name" size="small" placeholder="工作流名称（即模型名）" style="flex: 1" />
          <n-radio-group v-model:value="w.kind" size="small">
            <n-radio-button value="image">图像</n-radio-button>
            <n-radio-button value="video">视频</n-radio-button>
          </n-radio-group>
          <n-button size="small" quaternary type="error" @click="workflows.splice(i, 1)"><template #icon><Trash2 :size="14" /></template></n-button>
        </div>
        <n-input v-model:value="w.text" type="textarea" class="mono" :autosize="{ minRows: 4, maxRows: 12 }" placeholder="粘贴 API 格式的工作流 JSON" />
        <div v-if="wfError(w)" class="hint err">{{ wfError(w) }}</div>
      </div>
      <EmptyState v-if="!workflows.length" compact :icon="Layers" title="还没有工作流" desc="点击「示例工作流」快速开始，或导入你自己的 ComfyUI API 工作流" />
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { NButton, NCollapse, NCollapseItem, NDropdown, NInput, NRadioButton, NRadioGroup, NSelect } from 'naive-ui'
import { AudioLines, Film, Image as ImageIcon, Layers, MessageSquare, Plus, RefreshCw, Trash2, Upload, Wand2 } from 'lucide-vue-next'
import EmptyState from './EmptyState.vue'
import { api, toast } from '../api'
import { PROVIDER_PRESETS } from '../constants'

const props = defineProps({
  form: { type: Object, required: true },
  editing: { type: Boolean, default: false },
  // 测试函数：(payload) => Promise<{ ok, message, models?, classified? }>
  tester: { type: Function, required: true },
})

const CAPS = [
  { key: 'chat_models', label: '对话模型', icon: MessageSquare, placeholder: '如 gpt-4o、deepseek-chat' },
  { key: 'image_models', label: '图像模型', icon: ImageIcon, placeholder: '如 gpt-image-1、Kwai-Kolors/Kolors' },
  { key: 'video_models', label: '视频模型', icon: Film, placeholder: '如 sora-2、Wan-AI/Wan2.2-T2V-A14B' },
  { key: 'tts_models', label: '语音模型', icon: AudioLines, placeholder: '如 tts-1、gpt-4o-mini-tts' },
]
const EDIT_MODES = [
  { label: '/images/edits 接口（OpenAI gpt-image-1 等）', value: 'edits' },
  { label: '请求体 image 字段（硅基流动等）', value: 'field' },
]
const VIDEO_APIS = [
  { label: 'OpenAI Sora 风格（/videos）', value: 'openai' },
  { label: '硅基流动（/video/submit）', value: 'siliconflow' },
]

const form = props.form
for (const c of CAPS) form[c.key] = form[c.key] || []
form.extra = form.extra || {}
const extra = form.extra
extra.image_edit_mode = extra.image_edit_mode || 'edits'
extra.video_api = extra.video_api || 'openai'

const testing = ref(false)
const result = ref(null)
const remote = ref([])
const classified = ref(null)
const importInput = ref(null)
let uid = 0

const remoteOptions = computed(() => remote.value.map((m) => ({ label: m, value: m })))

// 自定义请求头
const headersText = ref(extra.headers && Object.keys(extra.headers).length ? JSON.stringify(extra.headers, null, 2) : '')
const headersError = ref('')
watch(headersText, (v) => {
  if (!v.trim()) {
    headersError.value = ''
    delete extra.headers
    return
  }
  try {
    const parsed = JSON.parse(v)
    if (typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('必须是对象')
    extra.headers = parsed
    headersError.value = ''
  } catch (e) {
    headersError.value = `JSON 格式错误：${e.message}`
  }
})

// ComfyUI 工作流
const workflows = ref(Object.entries(extra.workflows || {}).map(([name, wf]) => ({
  uid: ++uid, name, kind: extra.workflow_kinds?.[name] || 'image', text: JSON.stringify(wf, null, 2),
})))

function parseWf(w) {
  try {
    const v = JSON.parse(w.text)
    return typeof v === 'object' && !Array.isArray(v) ? v : null
  } catch {
    return null
  }
}
const wfError = (w) => (!w.text.trim() ? '' : parseWf(w) ? '' : 'JSON 格式错误')

watch(workflows, (list) => {
  const wfs = {}
  const kinds = {}
  for (const w of list) {
    const parsed = parseWf(w)
    if (w.name.trim() && parsed) {
      wfs[w.name.trim()] = parsed
      kinds[w.name.trim()] = w.kind
    }
  }
  extra.workflows = wfs
  extra.workflow_kinds = kinds
}, { deep: true, immediate: true })

const EXAMPLES = [
  { label: 'SDXL 文生图', key: 'SDXL 文生图' },
  { label: 'SDXL 局部重绘 / 扩图', key: 'SDXL 局部重绘' },
  { label: '4x 高清放大', key: '4x 高清放大' },
]

async function addExample(name = 'SDXL 文生图') {
  const data = await api.get('/api/providers/comfyui/example').catch(() => null)
  const wf = data?.workflows?.[name]
  if (!wf) return
  const taken = new Set(workflows.value.map((w) => w.name))
  let title = name
  for (let i = 2; taken.has(title); i++) title = `${name} ${i}`
  workflows.value.push({ uid: ++uid, name: title, kind: 'image', text: JSON.stringify(wf, null, 2) })
}

async function importFile(e) {
  const file = e.target.files[0]
  e.target.value = ''
  if (!file) return
  const text = await file.text()
  try {
    JSON.parse(text)
  } catch {
    return toast('文件不是合法的 JSON', 'error')
  }
  workflows.value.push({ uid: ++uid, name: file.name.replace(/\.json$/i, ''), kind: 'image', text })
}

function applyPreset(p) {
  Object.assign(form, { name: p.name, kind: p.kind, base_url: p.base_url })
  Object.assign(extra, { image_edit_mode: 'edits', video_api: 'openai', ...p.extra })
  if (p.kind === 'comfyui' && !workflows.value.length) addExample()
}

async function fetchModels() {
  testing.value = true
  result.value = null
  try {
    const payload = { ...form, api_key: form.api_key || (props.editing ? null : '') }
    const r = await props.tester(payload)
    result.value = r
    remote.value = r.models || []
    classified.value = r.classified || null
  } finally {
    testing.value = false
  }
}

function autoFill() {
  const c = classified.value
  if (!c) return
  const merge = (a, b) => [...new Set([...(a || []), ...(b || [])])]
  form.chat_models = merge(form.chat_models, c.chat)
  form.image_models = merge(form.image_models, c.image)
  form.video_models = merge(form.video_models, c.video)
  form.tts_models = merge(form.tts_models, c.tts)
  toast('已按模型名称自动分类，请检查后保存', 'success')
}

defineExpose({
  validate() {
    if (headersError.value) return headersError.value
    if (form.kind === 'comfyui' && workflows.value.some((w) => wfError(w))) return '存在格式错误的工作流 JSON'
    return ''
  },
})
</script>

<style scoped>
.presets { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 18px; font-size: 13px; }
.presets .muted { margin-right: 4px; }
.preset { padding: 4px 12px; border-radius: 14px; border: 1px solid var(--border); background: var(--panel); color: var(--text-2); cursor: pointer; font-size: 12.5px; }
.preset:hover, .preset.active { border-color: var(--primary); color: var(--primary); }
.grid2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-bottom: 14px; }
.grid2 > *, .model-grid > * { min-width: 0; }
.kind-seg { display: flex; }
.kind-seg :deep(.n-radio-button) { flex: 1; text-align: center; }
.field { margin-bottom: 14px; }
.hint { font-size: 12px; color: var(--muted); margin-top: 5px; line-height: 1.6; }
.hint.err { color: var(--danger); }
.models-head { display: flex; align-items: center; gap: 6px; margin: 18px 0 10px; flex-wrap: wrap; }
.result { font-size: 13px; padding: 8px 12px; border-radius: 8px; margin-bottom: 12px; }
.result.ok { background: color-mix(in srgb, var(--success) 12%, transparent); color: var(--success); }
.result.err { background: color-mix(in srgb, var(--danger) 10%, transparent); color: var(--danger); word-break: break-word; }
.model-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 14px; }
/* 模型名很长时标签内省略，避免撑开选择框 */
.model-grid :deep(.n-base-selection-tag-wrapper) { max-width: 100%; }
.model-grid :deep(.n-tag) { max-width: 100%; }
.model-grid :deep(.n-tag__content) { overflow: hidden; text-overflow: ellipsis; }
/* 标签自动换行，过多时在框内滚动 */
.model-grid :deep(.n-base-selection-tags) { max-height: 132px; overflow-y: auto; }
.cap-label { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--text-2); margin-bottom: 5px; font-weight: 500; }
.adv { margin-top: 18px; }
.wf { border: 1px solid var(--border); border-radius: 10px; padding: 10px; margin-bottom: 10px; }
.wf-head { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.mono :deep(textarea) { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; }
code { font-size: 11.5px; background: var(--panel-2); padding: 1px 4px; border-radius: 4px; }
@media (max-width: 640px) { .grid2, .model-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
