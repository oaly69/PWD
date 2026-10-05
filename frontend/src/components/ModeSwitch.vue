<template>
  <div class="mode-switch" role="tablist">
    <button type="button" role="tab" :class="{ active: !modelValue }" @click="emit('update:modelValue', false)">单条</button>
    <button type="button" role="tab" :class="{ active: modelValue }" @click="emit('update:modelValue', true)">批量</button>
  </div>
</template>

<script setup>
defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue'])
</script>

<style scoped>
.mode-switch { display: inline-flex; padding: 2px; border-radius: 8px; background: var(--panel-2); border: 1px solid var(--border); }
.mode-switch button { border: none; background: transparent; color: var(--text-2); font-size: 12px; padding: 2px 10px; border-radius: 6px; cursor: pointer; font-weight: 500; }
.mode-switch button.active { background: var(--panel); color: var(--primary); box-shadow: 0 1px 2px rgba(0, 0, 0, .08); font-weight: 600; }
</style>
