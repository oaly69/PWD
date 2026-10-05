<template>
  <div>
    <div class="row head">
      <n-select v-model:value="action" :options="actionOptions" clearable placeholder="全部操作" size="small" style="width: 180px" @update:value="reload" />
      <n-input v-model:value="q" size="small" clearable placeholder="搜索用户 / 对象 / IP" style="width: 220px" @update:value="onSearch">
        <template #prefix><Search :size="14" /></template>
      </n-input>
      <span class="spacer" />
      <span class="muted small">共 {{ total }} 条</span>
    </div>
    <n-data-table :columns="columns" :data="items" :loading="loading" :bordered="false" size="small" :scroll-x="820" class="table" />
    <div v-if="items.length < total" class="more"><n-button size="small" secondary :loading="loading" @click="load">加载更多</n-button></div>
  </div>
</template>

<script setup>
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NDataTable, NInput, NSelect, NTag } from 'naive-ui'
import { Search } from 'lucide-vue-next'
import { api } from '../../api'
import { formatTime } from '../../utils/format'

const items = ref([])
const total = ref(0)
const labels = ref({})
const action = ref(null)
const q = ref('')
const loading = ref(false)
let timer = null

const actionOptions = computed(() => Object.entries(labels.value).map(([value, label]) => ({ value, label })))
const TYPE = (a) => (a.endsWith('failed') || a.endsWith('delete') ? 'error' : a.startsWith('auth.') ? 'info' : 'warning')

const columns = [
  { title: '时间', key: 'created_at', width: 160, render: (r) => formatTime(r.created_at) },
  { title: '用户', key: 'username', width: 120, ellipsis: { tooltip: true } },
  { title: '操作', key: 'label', width: 130, render: (r) => h(NTag, { size: 'small', bordered: false, type: TYPE(r.action) }, () => r.label) },
  { title: '对象', key: 'target', width: 140, ellipsis: { tooltip: true } },
  { title: '详情', key: 'detail', ellipsis: { tooltip: true } },
  { title: 'IP', key: 'ip', width: 130 },
]

async function load() {
  loading.value = true
  try {
    const p = new URLSearchParams({ offset: items.value.length, limit: 50 })
    if (action.value) p.set('action', action.value)
    if (q.value.trim()) p.set('q', q.value.trim())
    const r = await api.get(`/api/audit?${p}`)
    items.value.push(...r.items)
    total.value = r.total
    labels.value = r.actions
  } finally {
    loading.value = false
  }
}

function reload() {
  items.value = []
  load()
}

function onSearch() {
  clearTimeout(timer)
  timer = setTimeout(reload, 300)
}

onMounted(load)
defineExpose({ load: reload })
</script>

<style scoped>
.head { margin-bottom: 12px; gap: 8px; flex-wrap: wrap; }
.small { font-size: 12px; }
.table { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }
.more { text-align: center; margin-top: 12px; }
</style>
