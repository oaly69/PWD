<template>
  <StudioShell title="语音合成" :icon="AudioLines">
    <div class="block">
      <div class="field-label">模型</div>
      <ModelSelect v-model="modelKey" kind="tts" />
    </div>

    <div class="block">
      <div class="field-label">文本 <span class="muted hint">{{ form.prompt.length }} 字</span></div>
      <n-input v-model:value="form.prompt" type="textarea" :autosize="{ minRows: 8, maxRows: 18 }" placeholder="输入要朗读的文字…" @keydown.ctrl.enter="generate" @keydown.meta.enter="generate" />
    </div>

    <div class="block">
      <div class="field-label">音色 <span class="muted hint">可直接输入服务支持的任意音色名</span></div>
      <n-select v-model:value="form.voice" :options="VOICES" filterable tag placeholder="选择或输入音色" />
    </div>

    <div class="block">
      <div class="field-label">语速 <span class="muted hint">{{ form.speed.toFixed(2) }}x</span></div>
      <n-slider v-model:value="form.speed" :min="0.5" :max="2" :step="0.05" :marks="{ 0.5: '0.5', 1: '1.0', 1.5: '1.5', 2: '2.0' }" />
    </div>

    <n-collapse class="block">
      <n-collapse-item title="高级参数" name="adv">
        <div class="field-label">输出格式</div>
        <n-radio-group v-model:value="form.format" size="small">
          <n-radio-button v-for="f in ['mp3', 'wav', 'opus', 'flac']" :key="f" :value="f">{{ f }}</n-radio-button>
        </n-radio-group>
        <div class="field-label" style="margin-top: 12px">语气指令 <span class="muted hint">gpt-4o-mini-tts 等模型支持</span></div>
        <n-input v-model:value="form.instructions" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="例如：用温柔、舒缓的语气朗读" />
      </n-collapse-item>
    </n-collapse>

    <template #footer>
      <n-button type="primary" size="large" block :loading="submitting" :disabled="!modelKey || !form.prompt.trim()" @click="generate">
        <template #icon><AudioLines :size="18" /></template>合成语音
      </n-button>
    </template>

    <template #results>
      <TaskFeed ref="feed" kind="tts" @reuse="reuse" />
    </template>
  </StudioShell>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { NButton, NCollapse, NCollapseItem, NInput, NRadioButton, NRadioGroup, NSelect, NSlider } from 'naive-ui'
import { AudioLines } from 'lucide-vue-next'
import ModelSelect from '../components/ModelSelect.vue'
import StudioShell from '../components/StudioShell.vue'
import TaskFeed from '../components/TaskFeed.vue'
import { toast } from '../api'
import { VOICES } from '../constants'
import { useStudio } from '../composables/studio'

const form = reactive({ prompt: '', voice: 'alloy', speed: 1, format: 'mp3', instructions: '' })
const feed = ref(null)

function applyParams(prompt, params, providerId, model) {
  form.prompt = prompt || ''
  form.voice = params.voice || form.voice
  form.speed = params.speed || 1
  form.format = params.format || 'mp3'
  form.instructions = params.instructions || ''
  if (providerId && model) modelKey.value = `${providerId}::${model}`
}

const { modelKey, submitting, submit } = useStudio('tts', {
  onAsset: (a) => applyParams(a.prompt, a.params || {}, a.provider_id, a.model),
  onPrompt: (p) => { form.prompt = p },
})

function reuse(t) {
  applyParams(t.prompt, t.params || {}, t.provider_id, t.model)
}

async function generate() {
  if (!modelKey.value || !form.prompt.trim() || submitting.value) return
  const task = await submit({
    prompt: form.prompt.trim(),
    voice: form.voice,
    speed: form.speed === 1 ? null : form.speed,
    format: form.format,
    instructions: form.instructions || null,
  })
  feed.value?.add(task)
  toast('已提交合成', 'success')
}
</script>

<style scoped>
.hint { font-weight: 400; font-size: 12px; }
</style>
