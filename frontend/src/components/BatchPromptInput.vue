<template>
  <div class="batch">
    <div class="prompt-box" :class="{ focused }">
      <n-input
        :value="modelValue"
        type="textarea"
        :placeholder="placeholder"
        :autosize="{ minRows: 6, maxRows: 16 }"
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
          <TemplateBrowser :category="kind === 'video' ? 'video' : 'image'" @select="addTemplate" />
        </n-popover>
        <n-button quaternary size="tiny" @click="fileInput?.click()"><template #icon><FileUp :size="14" /></template>导入</n-button>
        <input ref="fileInput" type="file" hidden accept=".txt,.csv,text/plain,text/csv" @change="onFile" />
        <n-button quaternary size="tiny" :disabled="!modelValue.trim()" @click="dedupe"><template #icon><ListX :size="14" /></template>去重</n-button>
        <span class="spacer" />
        <n-button v-if="modelValue" quaternary circle size="tiny" @click="emit('update:modelValue', '')"><template #icon><X :size="14" /></template></n-button>
      </div>
    </div>

    <div class="opts">
      <n-radio-group :value="split" size="small" @update:value="(v) => emit('update:split', v)">
        <n-radio-button value="line">每行一条</n-radio-button>
        <n-radio-button value="blank">空行分隔</n-radio-button>
      </n-radio-group>
      <span class="spacer" />
      <span class="count" :class="{ over }">共 {{ over ? `超过 ${MAX_BATCH}` : prompts.length }} 条</span>
    </div>
    <div class="muted tip">
      {{ split === 'line' ? '每行一条提示词' : '用空行分隔，单条可以写多行' }}；
      写 <code>{猫|狗|兔子}</code> 会自动展开为多条；支持导入 txt（每行一条）或 csv（取「prompt / 提示词」列）。单次最多 {{ MAX_BATCH }} 条。
    </div>

    <n-collapse v-if="prompts.length" class="preview">
      <n-collapse-item :title="`预览 ${Math.min(prompts.length, MAX_BATCH)} 条`" name="p">
        <ol class="list">
          <li v-for="(p, i) in prompts.slice(0, MAX_BATCH)" :key="i" :title="p">{{ p }}</li>
        </ol>
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { NButton, NCollapse, NCollapseItem, NInput, NPopover, NRadioButton, NRadioGroup } from 'naive-ui'
import { BookText, FileUp, ListX, X } from 'lucide-vue-next'
import { toast } from '../api'
import { MAX_BATCH, parseBatch, readPromptFile } from '../utils/batch'
import TemplateBrowser from './TemplateBrowser.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  split: { type: String, default: 'line' },
  kind: { type: String, default: 'image' },
  placeholder: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'update:split', 'submit'])

const focused = ref(false)
const pickerOpen = ref(false)
const fileInput = ref(null)

const prompts = computed(() => parseBatch(props.modelValue, props.split))
const over = computed(() => prompts.value.length > MAX_BATCH)

function append(lines) {
  const sep = props.split === 'blank' ? '\n\n' : '\n'
  const cur = props.modelValue.replace(/\s+$/, '')
  emit('update:modelValue', (cur ? cur + sep : '') + lines.join(sep))
}

function addTemplate(t) {
  pickerOpen.value = false
  // 「每行一条」模式下模板中的换行会被拆开，合并为一行
  append([props.split === 'line' ? t.content.replace(/\s*\n\s*/g, ' ') : t.content])
}

async function onFile(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  const lines = await readPromptFile(file)
  if (!lines.length) return toast('文件中没有读到提示词', 'warning')
  append(lines)
  toast(`已导入 ${lines.length} 条提示词`, 'success')
}

function dedupe() {
  const sep = props.split === 'blank' ? /\n\s*\n/ : /\n/
  const parts = props.modelValue.split(sep).map((s) => s.trim()).filter(Boolean)
  const uniq = [...new Set(parts)]
  emit('update:modelValue', uniq.join(props.split === 'blank' ? '\n\n' : '\n'))
  if (uniq.length < parts.length) toast(`已移除 ${parts.length - uniq.length} 条重复`, 'success')
}

function onKeydown(e) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    emit('submit')
  }
}

defineExpose({ prompts })
</script>

<style scoped>
.prompt-box { border: 1px solid var(--border); border-radius: 10px; background: var(--panel); transition: border-color .15s, box-shadow .15s; }
.prompt-box.focused { border-color: var(--primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 15%, transparent); }
.prompt-box :deep(.n-input) { background: transparent; }
.toolbar { display: flex; align-items: center; gap: 2px; padding: 4px 6px; border-top: 1px dashed var(--border); }
.opts { display: flex; align-items: center; margin-top: 8px; }
.count { font-size: 12.5px; font-weight: 600; color: var(--primary); }
.count.over { color: var(--danger); }
.tip { font-size: 12px; margin-top: 6px; line-height: 1.6; }
.tip code { font-size: 11.5px; padding: 0 4px; border-radius: 4px; background: var(--panel-2); }
.preview { margin-top: 8px; }
.list { margin: 0; padding-left: 22px; max-height: 220px; overflow: auto; font-size: 12.5px; color: var(--text-2); }
.list li { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.8; }
</style>
