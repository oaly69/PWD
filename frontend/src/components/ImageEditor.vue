<template>
  <Teleport to="body">
    <transition name="fade">
      <div v-if="asset" class="editor">
        <header class="ed-head">
          <n-tabs v-model:value="op" type="segment" size="small" class="ed-tabs">
            <n-tab v-for="o in OPS" :key="o.key" :name="o.key">{{ o.label }}</n-tab>
          </n-tabs>
          <span class="spacer" />
          <n-button quaternary circle @click="close"><template #icon><X :size="18" /></template></n-button>
        </header>

        <div class="ed-body">
          <!-- 画布区 -->
          <div ref="stageEl" class="ed-stage">
            <div v-if="op === 'inpaint'" class="canvas-box" :style="boxStyle">
              <img :src="asset.url" draggable="false" @load="onImgLoad" />
              <canvas
                ref="maskCanvas"
                :width="natural.w"
                :height="natural.h"
                class="mask"
                @pointerdown="startStroke"
                @pointermove="moveStroke"
                @pointerup="endStroke"
                @pointerleave="endStroke(); cursor.show = false"
                @pointerenter="cursor.show = true"
              />
              <div v-show="cursor.show" class="brush-cursor" :style="cursorStyle" />
            </div>

            <div v-else-if="op === 'outpaint'" class="outpaint-frame" :style="frameStyle">
              <img :src="asset.url" draggable="false" :style="innerStyle" @load="onImgLoad" />
              <div class="frame-size">{{ outSize.w }} × {{ outSize.h }}</div>
            </div>

            <div v-else class="plain-box">
              <img :src="asset.url" draggable="false" @load="onImgLoad" />
              <div v-if="op === 'upscale'" class="frame-size">{{ natural.w }} × {{ natural.h }} → {{ Math.round(natural.w * scale) }} × {{ Math.round(natural.h * scale) }}</div>
            </div>
          </div>

          <!-- 参数区 -->
          <aside class="ed-panel">
            <div class="scroll">
              <p class="muted desc">{{ OPS.find((o) => o.key === op).desc }}</p>

              <template v-if="op === 'inpaint'">
                <div class="field-label">画笔 <span class="muted">{{ brush }} px</span></div>
                <n-slider v-model:value="brush" :min="4" :max="300" />
                <div class="tool-row">
                  <n-radio-group v-model:value="tool" size="small">
                    <n-radio-button value="brush"><Brush :size="13" /> 涂抹</n-radio-button>
                    <n-radio-button value="eraser"><Eraser :size="13" /> 擦除</n-radio-button>
                  </n-radio-group>
                  <n-button size="small" quaternary :disabled="!history.length" @click="undo"><template #icon><Undo2 :size="14" /></template></n-button>
                  <n-button size="small" quaternary @click="invertMask">反选</n-button>
                  <n-button size="small" quaternary @click="clearMask">清空</n-button>
                </div>
              </template>

              <template v-if="op === 'outpaint'">
                <div class="field-label">快速设置</div>
                <div class="presets">
                  <n-button v-for="p in OUT_PRESETS" :key="p.label" size="small" secondary @click="applyPreset(p)">{{ p.label }}</n-button>
                </div>
                <div class="field-label">向各方向扩展（像素）</div>
                <div class="expand-grid">
                  <label v-for="d in DIRS" :key="d.key">
                    <span>{{ d.label }}</span>
                    <n-input-number v-model:value="expand[d.key]" size="small" :min="0" :max="4096" :step="64" />
                  </label>
                </div>
              </template>

              <template v-if="op === 'upscale'">
                <div class="field-label">放大倍数</div>
                <n-radio-group v-model:value="scale" size="small">
                  <n-radio-button v-for="s in [1.5, 2, 3, 4]" :key="s" :value="s">{{ s }}×</n-radio-button>
                </n-radio-group>
              </template>

              <div class="field-label">{{ op === 'upscale' ? '放大方式' : '模型' }}</div>
              <n-select v-model:value="modelKey" :options="modelOpts" filterable :consistent-menu-width="false" placeholder="选择模型" />
              <div class="hint">{{ modelHint }}</div>

              <template v-if="op === 'inpaint' || op === 'outpaint' || (op === 'rembg' && !isComfy)">
                <div class="field-label">{{ op === 'inpaint' ? '在涂抹区域生成什么' : op === 'outpaint' ? '画面描述' : '指令（可选）' }}</div>
                <n-input
                  v-model:value="prompt"
                  type="textarea"
                  :autosize="{ minRows: 3, maxRows: 8 }"
                  :placeholder="op === 'inpaint' ? '例如：一只戴着墨镜的橘猫' : op === 'outpaint' ? '默认使用原图的提示词' : '默认：去除背景，只保留主体'"
                />
              </template>
              <template v-if="(op === 'inpaint' || op === 'outpaint') && isComfy">
                <div class="field-label">反向提示词</div>
                <n-input v-model:value="negative" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="不希望出现的内容" />
              </template>
              <template v-if="op === 'inpaint' || op === 'outpaint'">
                <div class="field-label">生成数量</div>
                <n-radio-group v-model:value="n" size="small">
                  <n-radio-button v-for="i in [1, 2, 4]" :key="i" :value="i">{{ i }}</n-radio-button>
                </n-radio-group>
              </template>
            </div>
            <div class="ed-actions">
              <n-button block type="primary" size="large" :loading="submitting" @click="submit">
                <template #icon><Sparkles :size="16" /></template>开始{{ OPS.find((o) => o.key === op).label }}
              </n-button>
              <div class="muted hint center">结果会作为新作品保存，可在任务中心查看进度</div>
            </div>
          </aside>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { NButton, NInput, NInputNumber, NRadioButton, NRadioGroup, NSelect, NSlider, NTab, NTabs } from 'naive-ui'
import { Brush, Eraser, Sparkles, Undo2, X } from 'lucide-vue-next'
import { api, toast } from '../api'
import { loadProviders, loadSettings, modelOptions, splitModelKey, store } from '../store'

const props = defineProps({
  asset: { type: Object, default: null },
  initialOp: { type: String, default: 'inpaint' },
})
const emit = defineEmits(['update:asset', 'submitted'])

const OPS = [
  { key: 'inpaint', label: '局部重绘', desc: '用画笔涂抹需要修改的区域，描述想要的内容，只重绘涂抹部分。' },
  { key: 'outpaint', label: '扩图', desc: '向四周扩展画布，由模型补全画面，适合改变构图或画幅比例。' },
  { key: 'upscale', label: '高清放大', desc: '提高分辨率。本地放大速度快、不消耗额度；ComfyUI 放大模型细节更好。' },
  { key: 'rembg', label: '去除背景', desc: '去除背景只保留主体。需要支持图像编辑的模型（如 gpt-image-1）或 ComfyUI 抠图工作流。' },
]
const DIRS = [
  { key: 'top', label: '上' }, { key: 'bottom', label: '下' }, { key: 'left', label: '左' }, { key: 'right', label: '右' },
]
const OUT_PRESETS = [
  { label: '四周 25%', fn: (w, h) => ({ left: w / 4, right: w / 4, top: h / 4, bottom: h / 4 }) },
  { label: '左右 50%', fn: (w) => ({ left: w / 4, right: w / 4, top: 0, bottom: 0 }) },
  { label: '上下 50%', fn: (w, h) => ({ left: 0, right: 0, top: h / 4, bottom: h / 4 }) },
  { label: '转为 16:9', fn: (w, h) => ratio(w, h, 16 / 9) },
  { label: '转为 9:16', fn: (w, h) => ratio(w, h, 9 / 16) },
  { label: '转为 1:1', fn: (w, h) => ratio(w, h, 1) },
]
const LOCAL = '__local__'
const MODEL_STORE = 'pwd.model.edit.'

const op = ref(props.initialOp)
const natural = reactive({ w: 0, h: 0 })
const stageEl = ref(null)
const stage = reactive({ w: 800, h: 600 })
const maskCanvas = ref(null)
const brush = ref(48)
const tool = ref('brush')
const history = ref([])
const cursor = reactive({ x: 0, y: 0, show: false })
const expand = reactive({ left: 0, right: 0, top: 0, bottom: 0 })
const scale = ref(2)
const prompt = ref('')
const negative = ref('')
const n = ref(1)
const modelKey = ref(null)
const submitting = ref(false)
let drawing = false
let last = null

function ratio(w, h, r) {
  if (w / h < r) {
    const add = Math.round(h * r - w) / 2
    return { left: add, right: add, top: 0, bottom: 0 }
  }
  const add = Math.round(w / r - h) / 2
  return { left: 0, right: 0, top: add, bottom: add }
}

const imageProviders = computed(() => {
  void store.providers
  return modelOptions('image')
})
const modelOpts = computed(() => {
  const groups = imageProviders.value
  if (op.value === 'upscale') return [{ label: '本地放大（Lanczos，免费、快速）', value: LOCAL }, ...groups]
  return groups
})
const currentProvider = computed(() => {
  if (!modelKey.value || modelKey.value === LOCAL) return null
  const [pid] = splitModelKey(modelKey.value)
  return store.providers.find((p) => p.id === pid)
})
const isComfy = computed(() => currentProvider.value?.kind === 'comfyui')
const modelHint = computed(() => {
  if (modelKey.value === LOCAL) return '使用 Lanczos 插值 + 轻度锐化，不消耗模型额度'
  if (isComfy.value) {
    if (op.value === 'upscale') return 'ComfyUI 工作流需包含 {{image}}，目标尺寸由 {{width}} {{height}} 传入'
    if (op.value === 'rembg') return 'ComfyUI 工作流需包含 {{image}}，例如接入 RMBG / BiRefNet 节点'
    return 'ComfyUI 工作流需包含 {{image}}（重绘区域为透明，LoadImage 的 MASK 输出即蒙版）或 {{mask}}'
  }
  if (currentProvider.value) return '将调用 /images/edits 接口（模型服务中可切换为请求体传图方式）'
  return ''
})

const outSize = computed(() => ({
  w: natural.w + (expand.left || 0) + (expand.right || 0),
  h: natural.h + (expand.top || 0) + (expand.bottom || 0),
}))

// 图片在舞台中的显示尺寸
function fit(w, h) {
  if (!w || !h) return { w: 0, h: 0 }
  // 小图适当放大显示，便于涂抹
  const s = Math.min(stage.w / w, stage.h / h, 2)
  return { w: Math.round(w * s), h: Math.round(h * s) }
}
const boxStyle = computed(() => {
  const d = fit(natural.w, natural.h)
  return { width: `${d.w}px`, height: `${d.h}px` }
})
const frameStyle = computed(() => {
  const d = fit(outSize.value.w, outSize.value.h)
  return { width: `${d.w}px`, height: `${d.h}px` }
})
const innerStyle = computed(() => {
  const o = outSize.value
  return {
    left: `${((expand.left || 0) / o.w) * 100}%`,
    top: `${((expand.top || 0) / o.h) * 100}%`,
    width: `${(natural.w / o.w) * 100}%`,
    height: `${(natural.h / o.h) * 100}%`,
  }
})
const displayScale = computed(() => (natural.w ? fit(natural.w, natural.h).w / natural.w : 1))
const cursorStyle = computed(() => {
  const size = brush.value * displayScale.value
  return { width: `${size}px`, height: `${size}px`, left: `${cursor.x - size / 2}px`, top: `${cursor.y - size / 2}px` }
})

function onImgLoad(e) {
  const img = e.target
  if (img.naturalWidth === natural.w && img.naturalHeight === natural.h) return
  natural.w = img.naturalWidth
  natural.h = img.naturalHeight
  brush.value = Math.max(8, Math.round(Math.min(natural.w, natural.h) / 16))
  history.value = []
}

function measure() {
  const el = stageEl.value
  if (!el) return
  stage.w = Math.max(200, el.clientWidth - 48)
  stage.h = Math.max(200, el.clientHeight - 48)
}

// ---------------------------------------------------------------- 蒙版绘制

function ctx() {
  return maskCanvas.value?.getContext('2d')
}

function point(e) {
  const rect = maskCanvas.value.getBoundingClientRect()
  cursor.x = e.clientX - rect.left
  cursor.y = e.clientY - rect.top
  return { x: (cursor.x / rect.width) * natural.w, y: (cursor.y / rect.height) * natural.h }
}

function snapshot() {
  const c = ctx()
  if (!c) return
  history.value.push(c.getImageData(0, 0, natural.w, natural.h))
  if (history.value.length > 20) history.value.shift()
}

function drawLine(from, to) {
  const c = ctx()
  c.globalCompositeOperation = tool.value === 'eraser' ? 'destination-out' : 'source-over'
  c.strokeStyle = 'rgba(255, 64, 129, 1)'
  c.fillStyle = c.strokeStyle
  c.lineWidth = brush.value
  c.lineCap = 'round'
  c.lineJoin = 'round'
  c.beginPath()
  c.moveTo(from.x, from.y)
  c.lineTo(to.x, to.y)
  c.stroke()
}

function startStroke(e) {
  if (!maskCanvas.value) return
  e.target.setPointerCapture?.(e.pointerId)
  snapshot()
  drawing = true
  last = point(e)
  drawLine(last, last)
}

function moveStroke(e) {
  const p = point(e)
  if (!drawing) return
  drawLine(last, p)
  last = p
}

function endStroke() {
  drawing = false
  last = null
}

function undo() {
  const data = history.value.pop()
  if (data) ctx().putImageData(data, 0, 0)
}

function clearMask() {
  snapshot()
  ctx().clearRect(0, 0, natural.w, natural.h)
}

function invertMask() {
  snapshot()
  const c = ctx()
  const img = c.getImageData(0, 0, natural.w, natural.h)
  for (let i = 0; i < img.data.length; i += 4) {
    const on = img.data[i + 3] > 0
    img.data[i] = 255; img.data[i + 1] = 64; img.data[i + 2] = 129
    img.data[i + 3] = on ? 0 : 255
  }
  c.putImageData(img, 0, 0)
}

/** 导出白色 = 重绘区域、黑色 = 保留区域的蒙版 PNG。返回 null 表示没有涂抹。 */
function exportMask() {
  const src = ctx().getImageData(0, 0, natural.w, natural.h)
  const out = document.createElement('canvas')
  out.width = natural.w
  out.height = natural.h
  const oc = out.getContext('2d')
  const img = oc.createImageData(natural.w, natural.h)
  let painted = false
  for (let i = 0; i < src.data.length; i += 4) {
    const v = src.data[i + 3] > 20 ? 255 : 0
    if (v) painted = true
    img.data[i] = v; img.data[i + 1] = v; img.data[i + 2] = v; img.data[i + 3] = 255
  }
  if (!painted) return null
  oc.putImageData(img, 0, 0)
  return out.toDataURL('image/png')
}

function applyPreset(p) {
  const v = p.fn(natural.w, natural.h)
  for (const k of Object.keys(expand)) expand[k] = Math.round((v[k] || 0) / 8) * 8
}

// ---------------------------------------------------------------- 提交

function close() {
  emit('update:asset', null)
}

async function submit() {
  const body = { op: op.value, source_asset_id: props.asset.id }
  if (modelKey.value && modelKey.value !== LOCAL) {
    const [provider_id, model] = splitModelKey(modelKey.value)
    Object.assign(body, { provider_id, model })
  } else if (op.value !== 'upscale' || !modelKey.value) {
    return toast('请选择模型', 'warning')
  }
  if (op.value === 'inpaint') {
    if (!prompt.value.trim()) return toast('请描述要在涂抹区域生成的内容', 'warning')
    const mask = exportMask()
    if (!mask) return toast('请先涂抹需要重绘的区域', 'warning')
    body.mask = mask
  }
  if (op.value === 'outpaint') {
    if (outSize.value.w === natural.w && outSize.value.h === natural.h) return toast('请设置扩展的方向和大小', 'warning')
    body.expand = { ...expand }
  }
  if (op.value === 'upscale') body.scale = scale.value
  if (prompt.value.trim() && op.value !== 'upscale') body.prompt = prompt.value.trim()
  if (negative.value.trim()) body.negative_prompt = negative.value.trim()
  if (op.value === 'inpaint' || op.value === 'outpaint') body.n = n.value
  submitting.value = true
  try {
    const task = await api.post('/api/images/edit', body)
    try { localStorage.setItem(MODEL_STORE + op.value, modelKey.value) } catch { /* 忽略 */ }
    toast('已提交，完成后会出现在作品库中', 'success')
    emit('submitted', task)
    close()
  } finally {
    submitting.value = false
  }
}

function pickModel() {
  let saved = null
  try { saved = localStorage.getItem(MODEL_STORE + op.value) } catch { /* 忽略 */ }
  const all = modelOpts.value.flatMap((g) => (g.children ? g.children.map((c) => c.value) : [g.value]))
  const st = store.settings || {}
  const def = st.default_image_provider_id ? `${st.default_image_provider_id}::${st.default_image_model}` : null
  modelKey.value = [saved, op.value === 'upscale' ? LOCAL : def].find((k) => k && all.includes(k)) || all[0] || null
}

function onKey(e) {
  if (!props.asset || ['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return
  if (e.key === 'Escape') { e.stopImmediatePropagation(); close() }
  else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); undo() }
  else if (e.key === '[') brush.value = Math.max(4, brush.value - 8)
  else if (e.key === ']') brush.value = Math.min(300, brush.value + 8)
}

watch(() => props.asset, async (a) => {
  if (!a) return
  op.value = props.initialOp
  prompt.value = ''
  negative.value = ''
  Object.assign(expand, { left: 0, right: 0, top: 0, bottom: 0 })
  natural.w = a.width || 0
  natural.h = a.height || 0
  history.value = []
  await loadProviders()
  await loadSettings().catch(() => null)
  pickModel()
  await nextTick()
  measure()
})
watch(op, async () => {
  pickModel()
  await nextTick()
  measure()
})

onMounted(() => {
  window.addEventListener('keydown', onKey, true)
  window.addEventListener('resize', measure)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKey, true)
  window.removeEventListener('resize', measure)
})
</script>

<style scoped>
.editor { position: fixed; inset: 0; z-index: 2100; background: var(--bg); display: flex; flex-direction: column; }
.ed-head { height: 56px; flex-shrink: 0; display: flex; align-items: center; gap: 10px; padding: 0 16px; border-bottom: 1px solid var(--border); background: var(--panel); }
.ed-tabs { width: min(460px, 70vw); }
.ed-body { flex: 1; min-height: 0; display: flex; }
.ed-stage { flex: 1; min-width: 0; display: flex; align-items: center; justify-content: center; padding: 24px; overflow: hidden;
  background: repeating-conic-gradient(var(--panel-2) 0% 25%, var(--bg) 0% 50%) 50% / 24px 24px; }
.canvas-box { position: relative; touch-action: none; box-shadow: var(--shadow); }
.canvas-box img, .canvas-box canvas { position: absolute; inset: 0; width: 100%; height: 100%; user-select: none; }
.canvas-box canvas { opacity: .55; cursor: none; }
.brush-cursor { position: absolute; border-radius: 50%; border: 1.5px solid #fff; box-shadow: 0 0 0 1px rgba(0, 0, 0, .5); pointer-events: none; }
.outpaint-frame { position: relative; border: 2px dashed var(--primary); background: color-mix(in srgb, var(--primary) 10%, transparent); box-sizing: content-box; }
.outpaint-frame img { position: absolute; object-fit: fill; box-shadow: 0 0 0 1px var(--border); }
.plain-box { position: relative; max-width: 100%; max-height: 100%; display: flex; }
.plain-box img { max-width: 100%; max-height: calc(100vh - 160px); object-fit: contain; box-shadow: var(--shadow); }
.frame-size { position: absolute; bottom: -28px; left: 50%; transform: translateX(-50%); font-size: 12px; color: var(--muted); white-space: nowrap; }
.ed-panel { width: 340px; flex-shrink: 0; display: flex; flex-direction: column; border-left: 1px solid var(--border); background: var(--panel); }
.scroll { flex: 1; overflow: auto; padding: 4px 18px 16px; }
.desc { font-size: 13px; line-height: 1.6; margin: 12px 0 4px; }
.field-label { margin-top: 14px; }
.tool-row { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; margin-top: 8px; }
.presets { display: flex; flex-wrap: wrap; gap: 6px; }
.expand-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 10px; }
.expand-grid label { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.hint { font-size: 12px; color: var(--muted); margin-top: 4px; line-height: 1.5; }
.center { text-align: center; }
.ed-actions { padding: 14px 18px 18px; border-top: 1px solid var(--border); }
.fade-enter-active, .fade-leave-active { transition: opacity .15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
@media (max-width: 860px) {
  .ed-body { flex-direction: column; }
  .ed-stage { flex: none; height: 50vh; padding: 12px; }
  .ed-panel { width: 100%; flex: 1; min-height: 0; border-left: none; border-top: 1px solid var(--border); }
  .plain-box img { max-height: calc(50vh - 40px); }
}
</style>
