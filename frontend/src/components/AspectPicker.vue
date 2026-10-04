<template>
  <div class="aspects">
    <button
      v-for="a in ASPECTS"
      :key="a.label"
      type="button"
      class="aspect"
      :class="{ active: modelValue === a.size }"
      :title="a.size"
      @click="emit('update:modelValue', a.size)"
    >
      <span class="shape" :style="shape(a)" />
      <span>{{ a.label }}</span>
    </button>
  </div>
</template>

<script setup>
import { ASPECTS } from '../constants'

defineProps({ modelValue: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue'])

function shape(a) {
  const max = 18
  const r = a.w / a.h
  const w = r >= 1 ? max : Math.round(max * r)
  const hgt = r >= 1 ? Math.round(max / r) : max
  return { width: `${w}px`, height: `${hgt}px` }
}
</script>

<style scoped>
.aspects { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
.aspect {
  display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 8px 0 6px;
  border: 1px solid var(--border); border-radius: 8px; background: var(--panel); color: var(--text-2);
  cursor: pointer; font-size: 12px; transition: all .15s;
}
.aspect:hover { border-color: var(--primary); color: var(--text); }
.aspect.active { border-color: var(--primary); background: color-mix(in srgb, var(--primary) 10%, transparent); color: var(--primary); font-weight: 600; }
.shape { display: block; border: 1.5px solid currentColor; border-radius: 3px; height: 18px; }
.aspect > .shape { margin: 2px 0; }
</style>
