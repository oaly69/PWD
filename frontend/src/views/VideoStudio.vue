<template>
  <StudioShell title="视频生成" :icon="Film">
    <div class="block">
      <div class="field-label">模型</div>
      <ModelSelect v-model="modelKey" kind="video" />
      <div v-if="apiHint" class="muted hint-line">{{ apiHint }}</div>
    </div>

    <div class="block">
      <div class="field-label">提示词</div>
      <PromptInput v-model="form.prompt" kind="video" placeholder="描述画面中的主体、动作、镜头运动与氛围。例如：镜头缓慢推近，一只白鹭从晨雾笼罩的湖面起飞，水面泛起涟漪" @submit="generate" />
    </div>

    <div class="block">
      <div class="field-label">首帧参考图 <span class="muted hint">可选，图生视频</span></div>
      <ReferenceImages v-model="refs" :max="1" />
    </div>

    <div class="block">
      <div class="field-label">画面尺寸</div>
      <n-select v-model:value="form.size" :options="VIDEO_SIZES" filterable tag placeholder="选择或输入，如 1280x720" />
    </div>

    <div class="block">
      <div class="field-label">时长 <span class="muted hint">{{ form.seconds }} 秒（以服务实际支持为准）</span></div>
      <n-radio-group v-model:value="form.seconds" size="small" class="seg">
        <n-radio-button v-for="s in [4, 5, 8, 10, 12]" :key="s" :value="s">{{ s }}s</n-radio-button>
      </n-radio-group>
    </div>

    <n-collapse class="block">
      <n-collapse-item title="高级参数" name="adv">
        <div class="field-label">反向提示词</div>
        <n-input v-model:value="form.negative_prompt" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="部分模型支持" />
        <div class="field-label" style="margin-top: 12px">种子</div>
        <n-input-number v-model:value="form.seed" :min="0" placeholder="随机" clearable />
        <div class="field-label" style="margin-top: 12px">额外请求参数 <span class="muted hint">JSON</span></div>
        <n-input v-model:value="extraText" type="textarea" class="mono" :autosize="{ minRows: 2, maxRows: 6 }" placeholder='{"resolution": "720p"}' />
      </n-collapse-item>
    </n-collapse>

    <template #footer>
      <n-button type="primary" size="large" block :loading="submitting" :disabled="!modelKey || !form.prompt.trim()" @click="generate">
        <template #icon><Sparkles :size="18" /></template>生成视频
      </n-button>
      <div class="muted foot-hint">视频生成通常需要 1～10 分钟，可离开页面，完成后会通知你</div>
    </template>

    <template #results>
      <TaskFeed ref="feed" kind="video" @reuse="reuse" />
    </template>
  </StudioShell>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { NButton, NCollapse, NCollapseItem, NInput, NInputNumber, NRadioButton, NRadioGroup, NSelect } from 'naive-ui'
import { Film, Sparkles } from 'lucide-vue-next'
import ModelSelect from '../components/ModelSelect.vue'
import PromptInput from '../components/PromptInput.vue'
import ReferenceImages from '../components/ReferenceImages.vue'
import StudioShell from '../components/StudioShell.vue'
import TaskFeed from '../components/TaskFeed.vue'
import { api, toast } from '../api'
import { VIDEO_SIZES } from '../constants'
import { useStudio } from '../composables/studio'

const form = reactive({ prompt: '', negative_prompt: '', size: '1280x720', seconds: 5, seed: null })
const refs = ref([])
const extraText = ref('')
const feed = ref(null)

function applyParams(prompt, params, providerId, model) {
  form.prompt = prompt || ''
  form.negative_prompt = params.negative_prompt || ''
  form.size = params.size || form.size
  form.seconds = params.seconds || form.seconds
  form.seed = params.seed ?? null
  extraText.value = params.extra_body ? JSON.stringify(params.extra_body, null, 2) : ''
  if (providerId && model) modelKey.value = `${providerId}::${model}`
  const id = params.reference_asset_ids?.[0]
  refs.value = []
  if (id) api.get(`/api/assets/${id}`, { silent: true }).then((a) => { refs.value = [a] }).catch(() => {})
}

const { modelKey, submitting, submit, currentProvider } = useStudio('video', {
  onRef: (a) => { refs.value = [a]; toast('已设为首帧参考图', 'success') },
  onAsset: (a) => applyParams(a.prompt, a.params || {}, a.provider_id, a.model),
  onPrompt: (p) => { form.prompt = p },
})

const apiHint = computed(() => {
  const p = currentProvider()
  if (!p) return ''
  if (p.kind === 'comfyui') return '使用 ComfyUI 视频工作流'
  return p.extra?.video_api === 'siliconflow' ? '接口：硅基流动 /video/submit' : '接口：OpenAI Sora 风格 /videos'
})

function reuse(t) {
  applyParams(t.prompt, t.params || {}, t.provider_id, t.model)
  toast('已填入该任务的参数', 'success')
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
  const task = await submit({
    prompt: form.prompt.trim(),
    negative_prompt: form.negative_prompt,
    size: form.size,
    seconds: form.seconds,
    seed: form.seed,
    reference_asset_ids: refs.value.map((r) => r.id),
    extra_body,
  })
  feed.value?.add(task)
  toast('任务已提交，生成完成后会通知你', 'success')
}
</script>

<style scoped>
.hint { font-weight: 400; font-size: 12px; }
.hint-line { font-size: 12px; margin-top: 6px; }
.seg { display: flex; }
.seg :deep(.n-radio-button) { flex: 1; text-align: center; }
.foot-hint { font-size: 12px; text-align: center; margin-top: 8px; }
</style>
