<template>
  <n-modal :show="show" preset="card" title="从作品库选择" style="width: min(920px, 94vw)" :segmented="{ content: true }" @update:show="emit('update:show', $event)">
    <div class="bar">
      <n-radio-group v-model:value="filter" size="small" @update:value="reload">
        <n-radio-button value="all">全部图片</n-radio-button>
        <n-radio-button value="fav">收藏</n-radio-button>
        <n-radio-button value="upload">上传素材</n-radio-button>
      </n-radio-group>
      <span class="spacer" />
      <span class="muted">已选 {{ selected.length }} / {{ max }}</span>
    </div>
    <div class="grid" @scroll="onScroll">
      <div
        v-for="a in items"
        :key="a.id"
        class="cell"
        :class="{ on: selected.some((s) => s.id === a.id) }"
        @click="toggle(a)"
      >
        <img :src="a.thumb_url || a.url" loading="lazy" />
        <span class="check"><Check :size="14" /></span>
      </div>
      <div v-if="loading" v-for="i in 6" :key="'s' + i" class="cell shimmer" />
    </div>
    <EmptyState v-if="!loading && !items.length" compact :icon="ImageIcon" title="还没有图片" desc="可以直接上传参考图" />
    <template #footer>
      <div class="row">
        <span class="spacer" />
        <n-button @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" :disabled="!selected.length" @click="confirm">确定</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import { NButton, NModal, NRadioButton, NRadioGroup } from 'naive-ui'
import { Check, Image as ImageIcon } from 'lucide-vue-next'
import { api } from '../api'
import EmptyState from './EmptyState.vue'

const props = defineProps({ show: Boolean, max: { type: Number, default: 1 } })
const emit = defineEmits(['update:show', 'select'])

const items = ref([])
const total = ref(0)
const loading = ref(false)
const filter = ref('all')
const selected = ref([])

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    const p = new URLSearchParams({ kind: 'image', offset: items.value.length, limit: 48 })
    if (filter.value === 'fav') p.set('favorite', 'true')
    if (filter.value === 'upload') p.set('source', 'upload')
    const data = await api.get(`/api/assets?${p}`)
    items.value.push(...data.items)
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function reload() {
  items.value = []
  load()
}

function onScroll(e) {
  const el = e.target
  if (el.scrollTop + el.clientHeight > el.scrollHeight - 200 && items.value.length < total.value) load()
}

function toggle(a) {
  const i = selected.value.findIndex((s) => s.id === a.id)
  if (i >= 0) selected.value.splice(i, 1)
  else if (props.max === 1) selected.value = [a]
  else if (selected.value.length < props.max) selected.value.push(a)
}

function confirm() {
  emit('select', [...selected.value])
  emit('update:show', false)
}

watch(() => props.show, (v) => {
  if (v) {
    selected.value = []
    reload()
  }
})
</script>

<style scoped>
.bar { display: flex; align-items: center; margin-bottom: 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; max-height: 60vh; overflow: auto; }
.cell { position: relative; aspect-ratio: 1; border-radius: 8px; overflow: hidden; cursor: pointer; border: 2px solid transparent; background: var(--panel-2); }
.cell img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cell.on { border-color: var(--primary); }
.check { position: absolute; top: 6px; right: 6px; width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: rgba(0, 0, 0, .35); color: transparent; border: 1.5px solid #fff; }
.cell.on .check { background: var(--primary); color: #fff; border-color: var(--primary); }
</style>
