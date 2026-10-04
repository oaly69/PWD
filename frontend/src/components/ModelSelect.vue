<template>
  <n-select
    :value="modelValue || null"
    :options="options"
    :size="size"
    filterable
    :placeholder="placeholder"
    :consistent-menu-width="false"
    @update:value="(v) => emit('update:modelValue', v || '')"
  >
    <template #empty>
      <div class="empty">
        暂无可用{{ LABEL[kind] }}模型
        <router-link to="/providers">去配置模型服务 →</router-link>
      </div>
    </template>
  </n-select>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { NSelect } from 'naive-ui'
import { loadProviders, modelOptions, store } from '../store'

const props = defineProps({
  modelValue: { type: String, default: '' },
  kind: { type: String, default: 'chat' },
  size: { type: String, default: 'medium' },
  placeholder: { type: String, default: '选择模型' },
})
const emit = defineEmits(['update:modelValue'])
const LABEL = { chat: '对话', image: '图像', video: '视频', tts: '语音' }

const options = computed(() => {
  void store.providers
  return modelOptions(props.kind)
})

onMounted(() => loadProviders())
</script>

<style scoped>
.empty { padding: 8px 4px; font-size: 13px; color: var(--muted); display: flex; flex-direction: column; gap: 6px; align-items: center; }
</style>
