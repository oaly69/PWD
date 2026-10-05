<template>
  <div>
    <div class="row head">
      <n-radio-group v-model:value="days" size="small" @update:value="load">
        <n-radio-button :value="7">近 7 天</n-radio-button>
        <n-radio-button :value="30">近 30 天</n-radio-button>
        <n-radio-button :value="90">近 90 天</n-radio-button>
      </n-radio-group>
      <span class="spacer" />
      <span class="muted small">Token 数优先使用服务返回的真实用量，服务未返回时按字数估算</span>
    </div>

    <div class="stats">
      <div v-for="k in KINDS" :key="k.key" class="stat">
        <div class="stat-label"><component :is="k.icon" :size="14" />{{ k.label }}</div>
        <div class="stat-value">{{ totals[k.key].toLocaleString() }}<span class="unit">{{ k.unit }}</span></div>
      </div>
      <div class="stat">
        <div class="stat-label"><Coins :size="14" />Token</div>
        <div class="stat-value">{{ formatNum(totals.tokens) }}</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-title">每日用量</div>
      <div class="chart">
        <div v-for="d in series" :key="d.date" class="bar-col" :title="barTitle(d)">
          <div class="bar">
            <div v-for="k in KINDS" :key="k.key" class="seg" :style="{ height: `${(d[k.key] / maxDay) * 100}%`, background: k.color }" />
          </div>
          <div class="bar-label">{{ d.label }}</div>
        </div>
      </div>
      <div class="legend">
        <span v-for="k in KINDS" :key="k.key"><i :style="{ background: k.color }" />{{ k.label }}</span>
      </div>
    </div>

    <div class="two">
      <div class="panel">
        <div class="panel-title">按用户</div>
        <n-data-table size="small" :columns="userCols" :data="report.users" :bordered="false" :max-height="360" />
      </div>
      <div class="panel">
        <div class="panel-title">按模型</div>
        <n-data-table size="small" :columns="modelCols" :data="report.models" :bordered="false" :max-height="360" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { NDataTable, NRadioButton, NRadioGroup } from 'naive-ui'
import { AudioLines, Coins, Film, Image as ImageIcon, MessageSquare } from 'lucide-vue-next'
import { api } from '../../api'

const KINDS = [
  { key: 'chat', label: '对话', unit: ' 条', icon: MessageSquare, color: 'var(--primary)' },
  { key: 'image', label: '图片', unit: ' 张', icon: ImageIcon, color: '#0f9f8f' },
  { key: 'video', label: '视频', unit: ' 个', icon: Film, color: '#e0457b' },
  { key: 'tts', label: '语音', unit: ' 条', icon: AudioLines, color: '#d97706' },
]
const KIND_LABEL = Object.fromEntries(KINDS.map((k) => [k.key, k.label]))
const days = ref(30)
const report = ref({ daily: [], users: [], models: [] })

const formatNum = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e4 ? `${(n / 1e3).toFixed(1)}K` : String(n))

const totals = computed(() => {
  const t = { chat: 0, image: 0, video: 0, tts: 0, tokens: 0 }
  for (const d of report.value.daily) {
    t[d.kind] = (t[d.kind] || 0) + d.units
    t.tokens += d.tokens
  }
  return t
})

const series = computed(() => {
  const map = {}
  for (const d of report.value.daily) {
    map[d.date] = map[d.date] || { chat: 0, image: 0, video: 0, tts: 0 }
    map[d.date][d.kind] = d.units
  }
  const out = []
  const now = new Date()
  for (let i = days.value - 1; i >= 0; i--) {
    const dt = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i)
    const key = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
    out.push({ date: key, label: i % Math.ceil(days.value / 10) === 0 ? `${dt.getMonth() + 1}/${dt.getDate()}` : '', ...(map[key] || { chat: 0, image: 0, video: 0, tts: 0 }) })
  }
  return out
})
const maxDay = computed(() => Math.max(1, ...series.value.map((d) => d.chat + d.image + d.video + d.tts)))
const barTitle = (d) => `${d.date}\n${KINDS.map((k) => `${k.label}：${d[k.key]}`).join('\n')}`

const userCols = [
  { title: '用户', key: 'username', ellipsis: { tooltip: true } },
  ...KINDS.map((k) => ({ title: k.label, key: k.key, width: 64, sorter: (a, b) => a[k.key] - b[k.key] })),
  { title: 'Token', key: 'tokens', width: 80, sorter: (a, b) => a.tokens - b.tokens, render: (r) => formatNum(r.tokens) },
]
const modelCols = [
  { title: '模型', key: 'model', ellipsis: { tooltip: true } },
  { title: '类型', key: 'kind', width: 60, render: (r) => KIND_LABEL[r.kind] || r.kind },
  { title: '次数', key: 'units', width: 64 },
  { title: 'Token', key: 'tokens', width: 80, render: (r) => (r.kind === 'chat' ? formatNum(r.tokens) : '—') },
]

async function load() {
  report.value = await api.get(`/api/usage/report?days=${days.value}`)
}
onMounted(load)
defineExpose({ load })
</script>

<style scoped>
.head { margin-bottom: 14px; gap: 12px; flex-wrap: wrap; }
.small { font-size: 12px; }
.stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.stat { padding: 14px 16px; border-radius: 14px; background: var(--panel); border: 1px solid var(--border); }
.stat-label { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--muted); }
.stat-value { font-size: 24px; font-weight: 700; margin-top: 4px; font-variant-numeric: tabular-nums; }
.unit { font-size: 12px; font-weight: 400; color: var(--muted); }
.panel { padding: 14px 16px; border-radius: 14px; background: var(--panel); border: 1px solid var(--border); margin-bottom: 14px; min-width: 0; }
.panel-title { font-weight: 600; margin-bottom: 10px; }
.chart { display: flex; align-items: flex-end; gap: 3px; height: 180px; }
.bar-col { flex: 1; min-width: 0; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; }
.bar { width: 100%; max-width: 26px; flex: 1; display: flex; flex-direction: column-reverse; border-radius: 4px 4px 0 0; overflow: hidden; background: var(--panel-2); }
.seg { width: 100%; min-height: 0; }
.bar-label { height: 18px; font-size: 10.5px; color: var(--muted); white-space: nowrap; margin-top: 4px; }
.legend { display: flex; gap: 14px; justify-content: center; font-size: 12px; color: var(--text-2); margin-top: 6px; }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 4px; vertical-align: -1px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.two .panel { margin-bottom: 0; }
@media (max-width: 900px) { .stats { grid-template-columns: repeat(2, 1fr); } .two { grid-template-columns: 1fr; } }
</style>
