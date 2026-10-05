<template>
  <StudioShell title="图像生成" :icon="ImageIcon">
    <div class="block">
      <div class="field-label">
        模型
        <span class="spacer" />
        <n-button text size="tiny" :type="compare ? 'primary' : 'default'" @click="compare = !compare"><template #icon><Columns3 :size="13" /></template>多模型对比</n-button>
      </div>
      <ModelSelect v-model="modelKey" kind="image" />
      <template v-if="compare">
        <ModelSelect v-model="compareKeys" kind="image" multiple placeholder="再选 1～3 个模型，用同一提示词同时生成" class="compare-select" />
        <div class="muted hint">每个模型各生成一个任务，结果在右侧并列出现，便于比较效果</div>
      </template>
    </div>

    <div class="block">
      <div class="field-label">提示词</div>
      <PromptInput v-model="form.prompt" kind="image" placeholder="描述你想要的画面，越具体越好。例如：一只坐在窗边的橘猫，午后阳光透过纱帘，胶片质感" @template="onTemplate" @submit="generate" />
    </div>

    <div class="block">
      <div class="field-label">风格 <span class="muted hint">{{ style ? '· ' + style.name : '可选' }}</span></div>
      <div class="styles">
        <button v-for="s in STYLE_PRESETS" :key="s.name" type="button" class="style-chip" :class="{ active: style?.name === s.name }" :title="s.prompt" @click="style = style?.name === s.name ? null : s">{{ s.name }}</button>
      </div>
    </div>

    <div class="block">
      <div class="field-label">
        参考图 <span class="muted hint">图生图 / 图像编辑{{ maxRefs > 1 ? `，最多 ${maxRefs} 张` : '' }}</span>
      </div>
      <ReferenceImages v-model="refs" :max="maxRefs" />
    </div>

    <div class="block">
      <div class="field-label">画面比例</div>
      <AspectPicker v-model="form.size" />
      <n-input v-model:value="form.size" size="small" placeholder="宽x高，例如 1024x1024" class="size-input">
        <template #prefix><span class="muted">尺寸</span></template>
      </n-input>
    </div>

    <div class="block">
      <div class="field-label">生成数量</div>
      <n-radio-group v-model:value="form.n" size="small" class="count">
        <n-radio-button v-for="i in [1, 2, 3, 4]" :key="i" :value="i">{{ i }} 张</n-radio-button>
      </n-radio-group>
    </div>

    <n-collapse class="block" :default-expanded-names="form.negative_prompt ? ['neg'] : []">
      <n-collapse-item title="反向提示词" name="neg">
        <n-input v-model:value="form.negative_prompt" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="不希望出现的内容，例如：模糊, 低质量, 多余手指（部分模型支持）" />
      </n-collapse-item>
      <n-collapse-item title="高级参数" name="adv">
        <div class="field-label">种子</div>
        <n-input-group>
          <n-input-number v-model:value="form.seed" :min="0" :max="2147483647" placeholder="随机" clearable style="flex: 1" />
          <n-button @click="form.seed = Math.floor(Math.random() * 2147483647)"><template #icon><Dices :size="16" /></template></n-button>
        </n-input-group>
        <template v-if="isComfy()">
          <div class="field-label" style="margin-top: 12px">采样步数</div>
          <n-slider v-model:value="form.steps" :min="1" :max="80" />
        </template>
        <div class="field-label" style="margin-top: 12px">额外请求参数 <span class="muted hint">JSON，合并到请求体</span></div>
        <n-input v-model:value="extraText" type="textarea" class="mono" :autosize="{ minRows: 2, maxRows: 8 }" placeholder='{"quality": "high", "background": "transparent"}' />
      </n-collapse-item>
    </n-collapse>

    <template #footer>
      <n-button type="primary" size="large" block :loading="submitting" :disabled="!modelKey || !form.prompt.trim()" @click="generate">
        <template #icon><Sparkles :size="18" /></template>
        生成 {{ form.n > 1 ? `${form.n} 张` : '' }}{{ extraKeys.length ? ` · ${extraKeys.length + 1} 个模型` : '' }}
        <span class="kbd">Ctrl ↵</span>
      </n-button>
    </template>

    <template #results>
      <TaskFeed ref="feed" kind="image" @reuse="reuse" @use-ref="useRef" />
    </template>
  </StudioShell>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { NButton, NCollapse, NCollapseItem, NInput, NInputGroup, NInputNumber, NRadioButton, NRadioGroup, NSlider } from 'naive-ui'
import { Columns3, Dices, Image as ImageIcon, Sparkles } from 'lucide-vue-next'
import AspectPicker from '../components/AspectPicker.vue'
import ModelSelect from '../components/ModelSelect.vue'
import PromptInput from '../components/PromptInput.vue'
import ReferenceImages from '../components/ReferenceImages.vue'
import StudioShell from '../components/StudioShell.vue'
import TaskFeed from '../components/TaskFeed.vue'
import { api, toast } from '../api'
import { STYLE_PRESETS } from '../constants'
import { splitModelKey } from '../store'
import { useStudio } from '../composables/studio'

const form = reactive({ prompt: '', negative_prompt: '', size: '1024x1024', n: 1, seed: null, steps: 25 })
const style = ref(null)
const refs = ref([])
const extraText = ref('')
const feed = ref(null)
const compare = ref(false)
const compareKeys = ref([])
const extraKeys = computed(() => (compare.value ? compareKeys.value.filter((k) => k !== modelKey.value).slice(0, 3) : []))

function applyParams(prompt, params, providerId, model) {
  form.prompt = prompt || ''
  form.negative_prompt = params.negative_prompt || ''
  form.size = params.size || form.size
  form.n = params.n || 1
  form.seed = params.seed ?? null
  if (params.steps) form.steps = params.steps
  style.value = STYLE_PRESETS.find((s) => s.name === params.style) || null
  extraText.value = params.extra_body ? JSON.stringify(params.extra_body, null, 2) : ''
  if (providerId && model) modelKey.value = `${providerId}::${model}`
  if (params.reference_asset_ids?.length) {
    Promise.all(params.reference_asset_ids.map((id) => api.get(`/api/assets/${id}`, { silent: true }).catch(() => null)))
      .then((list) => { refs.value = list.filter(Boolean) })
  } else refs.value = []
}

const { modelKey, submitting, submit, isComfy, currentProvider } = useStudio('image', {
  onRef: (a) => { refs.value = [a]; toast('已添加为参考图', 'success') },
  onAsset: (a) => applyParams(a.prompt, a.params || {}, a.provider_id, a.model),
  onPrompt: (p, neg) => { form.prompt = p; if (neg) form.negative_prompt = neg },
})

const maxRefs = computed(() => {
  const p = currentProvider()
  return p?.kind === 'openai' && (p.extra?.image_edit_mode || 'edits') === 'edits' ? 4 : 1
})

function onTemplate(t) {
  if (t.negative) form.negative_prompt = t.negative
}

function reuse(t) {
  applyParams(t.prompt, t.params || {}, t.provider_id, t.model)
  toast('已填入该任务的参数', 'success')
}

function useRef(a) {
  refs.value = [a, ...refs.value.filter((x) => x.id !== a.id)].slice(0, maxRefs.value)
  toast('已添加为参考图', 'success')
}

async function generate() {
  if (!modelKey.value || !form.prompt.trim() || submitting.value) return
  let extra_body = null
  if (extraText.value.trim()) {
    try {
      extra_body = JSON.parse(extraText.value)
    } catch {
      return toast('额外请求参数不是合法的 JSON', 'error')
    }
  }
  const body = {
    prompt: form.prompt.trim(),
    negative_prompt: form.negative_prompt,
    size: form.size,
    n: form.n,
    seed: form.seed,
    steps: isComfy() ? form.steps : null,
    style: style.value?.name || null,
    style_prompt: style.value?.prompt || null,
    style_negative: style.value?.negative || null,
    reference_asset_ids: refs.value.map((r) => r.id),
    extra_body,
  }
  const task = await submit(body)
  feed.value?.add(task)
  // 对比模式：其余模型使用相同参数各提交一个任务（ComfyUI 专属参数对其他服务无影响）
  for (const key of extraKeys.value) {
    const [provider_id, model] = splitModelKey(key)
    const t = await api.post('/api/generate/image', { ...body, provider_id, model }).catch(() => null)
    if (t) feed.value?.add(t)
  }
}
</script>

<style scoped>
.hint { font-weight: 400; font-size: 12px; }
.styles { display: flex; flex-wrap: wrap; gap: 6px; }
.style-chip { padding: 5px 12px; border-radius: 16px; border: 1px solid var(--border); background: var(--panel); color: var(--text-2); font-size: 12.5px; cursor: pointer; transition: all .15s; }
.style-chip:hover { border-color: var(--primary); color: var(--text); }
.style-chip.active { background: var(--primary); border-color: var(--primary); color: #fff; }
.size-input { margin-top: 8px; }
.block > .field-label { display: flex; align-items: center; }
.compare-select { margin-top: 8px; }
.count { display: flex; }
.count :deep(.n-radio-button) { flex: 1; text-align: center; }
.kbd { margin-left: 8px; font-size: 11px; opacity: .7; padding: 1px 6px; border-radius: 4px; background: rgba(255, 255, 255, .18); }
</style>
