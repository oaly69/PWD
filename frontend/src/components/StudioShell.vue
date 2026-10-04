<template>
  <div class="studio">
    <aside class="panel">
      <div class="panel-scroll">
        <div class="panel-title">
          <component :is="icon" :size="18" />
          <span>{{ title }}</span>
        </div>
        <slot />
      </div>
      <div class="panel-foot">
        <slot name="footer" />
      </div>
    </aside>
    <section class="results">
      <slot name="results" />
    </section>
  </div>
</template>

<script setup>
defineProps({ title: String, icon: [Object, Function] })
</script>

<style scoped>
.studio { display: flex; height: 100%; min-height: 0; }
.panel { width: 400px; flex-shrink: 0; display: flex; flex-direction: column; border-right: 1px solid var(--border); background: var(--panel); }
.panel-scroll { flex: 1; overflow: auto; padding: 18px 20px 8px; }
.panel-title { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 16px; margin-bottom: 16px; }
.panel-foot { padding: 12px 20px 16px; border-top: 1px solid var(--border); }
.results { flex: 1; min-width: 0; overflow: auto; padding: 20px 24px 32px; }
.panel :deep(.block) { margin-bottom: 18px; }
@media (max-width: 960px) {
  .studio { flex-direction: column; overflow: auto; height: auto; }
  .panel { width: 100%; border-right: none; border-bottom: 1px solid var(--border); }
  .panel-scroll { overflow: visible; }
  .results { overflow: visible; padding: 16px; }
}
</style>
