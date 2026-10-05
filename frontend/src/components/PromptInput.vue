<template>
  <div class="prompt-input" :class="{ focused }">
    <n-input
      :value="modelValue"
      type="textarea"
      :placeholder="placeholder"
      :autosize="{ minRows, maxRows }"
      :bordered="false"
      @update:value="(v) => emit('update:modelValue', v)"
      @focus="focused = true"
      @blur="focused = false"
      @keydown="onKeydown"
    />
    <div class="toolbar">
      <n-popover v-model:show="pickerOpen" trigger="click" placement="bottom-start" :width="380" style="padding: 12px">
        <template #trigger>
          <n-button quaternary size="tiny"><template #icon><BookText :size="14" /></template>模板</n-button>
        </template>
        <TemplateBrowser :category="kind === 'video' ? 'video' : 'image'" @select="useTemplate" />
      </n-popover>
      <n-tooltip>
        <template #trigger>
          <n-button quaternary size="tiny" :loading="enhancing" :disabled="!modelValue.trim()" @click="enhance">
            <template #icon><WandSparkles :size="14" /></template>AI 优化
          </n-button>
        </template>
        使用对话模型扩写、润色提示词（可在系统设置中指定模型）
      </n-tooltip>
      <n-button v-if="undoValue !== null" quaternary size="tiny" @click="undo">
        <template #icon><Undo2 :size="14" /></template>撤销
      </n-button>
      <span class="spacer" />
      <span class="count">{{ modelValue.length }}</span>
      <n-button v-if="modelValue" quaternary circle size="tiny" @click="emit('update:modelValue', '')"><template #icon><X :size="14" /></template></n-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { NButton, NInput, NPopover, NTooltip } from 'naive-ui'
import { BookText, Undo2, WandSparkles, X } from 'lucide-vue-next'
import { api, toast } from '../api'
import TemplateBrowser from './TemplateBrowser.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  kind: { type: String, default: 'image' },
  placeholder: { type: String, default: '' },
  minRows: { type: Number, default: 4 },
  maxRows: { type: Number, default: 12 },
})
const emit = defineEmits(['update:modelValue', 'template', 'submit'])

const focused = ref(false)
const enhancing = ref(false)
const undoValue = ref(null)
const pickerOpen = ref(false)

function useTemplate(t) {
  pickerOpen.value = false
  undoValue.value = props.modelValue
  emit('update:modelValue', t.content)
  emit('template', t)
}

async function enhance() {
  enhancing.value = true
  try {
    const r = await api.post('/api/prompts/enhance', { prompt: props.modelValue, kind: props.kind === 'video' ? 'video' : 'image' })
    undoValue.value = props.modelValue
    emit('update:modelValue', r.prompt)
    toast('提示词已优化', 'success')
  } finally {
    enhancing.value = false
  }
}

function undo() {
  emit('update:modelValue', undoValue.value)
  undoValue.value = null
}

function onKeydown(e) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    emit('submit')
  }
}

</script>

<style scoped>
.prompt-input { border: 1px solid var(--border); border-radius: 10px; background: var(--panel); transition: border-color .15s, box-shadow .15s; }
.prompt-input.focused { border-color: var(--primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 15%, transparent); }
.prompt-input :deep(.n-input) { background: transparent; }
.toolbar { display: flex; align-items: center; gap: 2px; padding: 4px 6px; border-top: 1px dashed var(--border); }
.count { font-size: 11px; color: var(--muted); margin-right: 4px; }
</style>
