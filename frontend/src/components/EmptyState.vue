<template>
  <div class="empty-state" :class="{ compact }">
    <div class="icon"><component :is="icon" :size="compact ? 28 : 40" :stroke-width="1.5" /></div>
    <div class="title">{{ title }}</div>
    <div v-if="desc" class="desc">{{ desc }}</div>
    <div v-if="$slots.default" class="actions"><slot /></div>
  </div>
</template>

<script setup>
import { Sparkles } from 'lucide-vue-next'

defineProps({
  icon: { type: [Object, Function], default: () => Sparkles },
  title: { type: String, required: true },
  desc: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})
</script>

<style scoped>
.empty-state { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 56px 20px; color: var(--muted); }
.empty-state.compact { padding: 28px 16px; }
.icon { width: 76px; height: 76px; border-radius: 22px; display: grid; place-items: center; background: color-mix(in srgb, var(--primary) 10%, transparent); color: var(--primary); margin-bottom: 16px; }
.compact .icon { width: 52px; height: 52px; border-radius: 16px; margin-bottom: 10px; }
.title { font-size: 16px; font-weight: 600; color: var(--text); }
.desc { margin-top: 6px; font-size: 13px; max-width: 420px; line-height: 1.6; }
.actions { margin-top: 18px; display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
</style>
