<template>
  <div class="page gallery" @dragover.prevent="dragging = true" @dragleave.self="dragging = false" @drop.prevent="onDrop">
    <div class="page-head">
      <div>
        <h1>作品库</h1>
        <div class="sub">共 {{ total }} 个作品 · 生成结果会自动保存到这里</div>
      </div>
      <span class="spacer" />
      <n-button :type="selecting ? 'primary' : 'default'" secondary @click="toggleSelect">
        <template #icon><SquareCheck :size="16" /></template>{{ selecting ? '退出多选' : '多选' }}
      </n-button>
      <n-button type="primary" :loading="uploading" @click="fileInput?.click()"><template #icon><Upload :size="16" /></template>上传素材</n-button>
      <input ref="fileInput" type="file" accept="image/*,video/*,audio/*" multiple hidden @change="(e) => { upload(e.target.files); e.target.value = '' }" />
    </div>

    <div class="filters">
      <n-tabs v-model:value="kind" type="segment" size="small" class="kind-tabs" @update:value="reload">
        <n-tab name="">全部</n-tab>
        <n-tab name="image">图片</n-tab>
        <n-tab name="video">视频</n-tab>
        <n-tab name="audio">音频</n-tab>
      </n-tabs>
      <n-select v-model:value="source" :options="SOURCES" size="small" class="f-select" @update:value="reload" />
      <n-select v-model:value="model" :options="modelOpts" size="small" clearable filterable placeholder="全部模型" class="f-select wide" @update:value="reload" />
      <n-button size="small" :type="favorite ? 'warning' : 'default'" secondary @click="favorite = !favorite; reload()">
        <template #icon><Star :size="14" :fill="favorite ? 'currentColor' : 'none'" /></template>收藏
      </n-button>
      <span class="spacer" />
      <n-input v-model:value="q" size="small" clearable placeholder="搜索提示词" class="search" @update:value="onSearch">
        <template #prefix><Search :size="14" /></template>
      </n-input>
    </div>

    <transition name="slide">
      <div v-if="selecting" class="batch-bar">
        <span>已选 <b>{{ selected.size }}</b> 项</span>
        <n-button size="small" quaternary @click="selectAll">全选已加载</n-button>
        <n-button size="small" quaternary :disabled="!selected.size" @click="selected = new Set()">清空</n-button>
        <span class="spacer" />
        <n-button size="small" secondary :disabled="!selected.size" @click="batch('favorite')"><template #icon><Star :size="14" /></template>收藏</n-button>
        <n-button size="small" secondary :disabled="!selected.size" @click="downloadZip"><template #icon><Download :size="14" /></template>打包下载</n-button>
        <n-button size="small" type="error" secondary :disabled="!selected.size" @click="batch('delete')"><template #icon><Trash2 :size="14" /></template>删除</n-button>
      </div>
    </transition>

    <div ref="wall" class="wall" :style="{ '--cols': columns.length }">
      <div v-for="(col, ci) in columns" :key="ci" class="col">
        <div
          v-for="a in col"
          :key="a.id"
          class="tile"
          :class="[a.kind, { selected: selected.has(a.id) }]"
          @click="onTile(a)"
        >
          <div class="media" :style="{ aspectRatio: ratio(a) }">
            <img v-if="a.kind === 'image'" :src="a.thumb_url || a.url" loading="lazy" :alt="a.prompt" />
            <video v-else-if="a.kind === 'video'" :src="a.url + '#t=0.1'" muted preload="metadata" @mouseenter="(e) => e.target.play().catch(() => {})" @mouseleave="(e) => { e.target.pause() }" />
            <div v-else class="audio-tile"><Music :size="28" :stroke-width="1.5" /><span class="ellipsis">{{ a.prompt || '音频' }}</span></div>
            <span v-if="a.kind === 'video'" class="badge"><Play :size="11" fill="currentColor" /> 视频</span>
          </div>
          <div class="overlay">
            <div class="ov-prompt">{{ a.prompt }}</div>
          </div>
          <button class="fav" :class="{ on: a.favorite }" @click.stop="toggleFav(a)"><Star :size="15" :fill="a.favorite ? 'currentColor' : 'none'" /></button>
          <span v-if="selecting" class="check"><Check :size="14" /></span>
        </div>
      </div>
    </div>

    <div v-if="loading" class="wall loading-wall" :style="{ '--cols': columns.length }">
      <div v-for="i in columns.length" :key="i" class="col"><div class="tile shimmer" style="aspect-ratio: 1" /><div class="tile shimmer" style="aspect-ratio: 3/4" /></div>
    </div>
    <EmptyState v-if="!loading && !items.length" :icon="GalleryHorizontalEnd" :title="hasFilter ? '没有符合条件的作品' : '作品库还是空的'" :desc="hasFilter ? '试试调整筛选条件' : '去生成第一张图片，或者把素材拖进来'">
      <n-button v-if="!hasFilter" type="primary" @click="$router.push('/image')">开始创作</n-button>
    </EmptyState>
    <div ref="sentinel" class="sentinel" />

    <div v-if="dragging" class="drop-mask"><Upload :size="40" /><div>松开即可上传到作品库</div></div>
    <MediaViewer v-model:index="viewerIndex" :items="items" @deleted="onDeleted" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { NButton, NInput, NSelect, NTab, NTabs } from 'naive-ui'
import { Check, Download, GalleryHorizontalEnd, Music, Play, Search, SquareCheck, Star, Trash2, Upload } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import MediaViewer from '../components/MediaViewer.vue'
import { api, confirmDialog, toast, uploadFile } from '../api'
import { downloadUrl } from '../utils/format'

const SOURCES = [
  { label: '全部来源', value: '' },
  { label: 'AI 生成', value: 'generated' },
  { label: '上传素材', value: 'upload' },
]
const PAGE = 48

const items = ref([])
const total = ref(0)
const loading = ref(false)
const kind = ref('')
const source = ref('')
const model = ref(null)
const favorite = ref(false)
const q = ref('')
const modelOpts = ref([])
const selecting = ref(false)
const selected = ref(new Set())
const viewerIndex = ref(-1)
const uploading = ref(false)
const dragging = ref(false)
const wall = ref(null)
const sentinel = ref(null)
const fileInput = ref(null)
const width = ref(1000)
let observer = null
let resizeObs = null
let searchTimer = null

const hasFilter = computed(() => kind.value || source.value || model.value || favorite.value || q.value)

const ratio = (a) => {
  if (a.kind === 'image' && a.width && a.height) return `${a.width} / ${a.height}`
  if (a.kind === 'video') return '16 / 9'
  if (a.kind === 'audio') return '2 / 1'
  return '1 / 1'
}

// 瀑布流：按顺序放入当前最短的列
const columns = computed(() => {
  const n = Math.max(2, Math.min(6, Math.floor(width.value / 230)))
  const cols = Array.from({ length: n }, () => [])
  const heights = new Array(n).fill(0)
  for (const a of items.value) {
    const [w, h] = ratio(a).split(' / ').map(Number)
    const i = heights.indexOf(Math.min(...heights))
    cols[i].push(a)
    heights[i] += h / w + 0.05
  }
  return cols
})

function params() {
  const p = new URLSearchParams({ offset: items.value.length, limit: PAGE })
  if (kind.value) p.set('kind', kind.value)
  if (source.value) p.set('source', source.value)
  if (model.value) p.set('model', model.value)
  if (favorite.value) p.set('favorite', 'true')
  if (q.value.trim()) p.set('q', q.value.trim())
  return p
}

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    const data = await api.get(`/api/assets?${params()}`)
    items.value.push(...data.items)
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function reload() {
  items.value = []
  selected.value = new Set()
  load()
}

function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(reload, 300)
}

function onTile(a) {
  if (selecting.value) {
    const s = new Set(selected.value)
    s.has(a.id) ? s.delete(a.id) : s.add(a.id)
    selected.value = s
  } else {
    viewerIndex.value = items.value.findIndex((x) => x.id === a.id)
  }
}

function toggleSelect() {
  selecting.value = !selecting.value
  selected.value = new Set()
}

function selectAll() {
  selected.value = new Set(items.value.map((a) => a.id))
}

async function toggleFav(a) {
  const r = await api.patch(`/api/assets/${a.id}`, { favorite: !a.favorite })
  a.favorite = r.favorite
}

async function batch(action) {
  const ids = [...selected.value]
  if (action === 'delete' && !(await confirmDialog({ title: '批量删除', content: `确定永久删除选中的 ${ids.length} 个作品？`, positiveText: '删除' }))) return
  await api.post('/api/assets/batch', { ids, action })
  if (action === 'delete') {
    items.value = items.value.filter((a) => !selected.value.has(a.id))
    total.value -= ids.length
    selected.value = new Set()
    toast(`已删除 ${ids.length} 个作品`, 'success')
  } else {
    items.value.forEach((a) => { if (selected.value.has(a.id)) a.favorite = true })
    toast('已收藏', 'success')
  }
}

function downloadZip() {
  downloadUrl(`/api/assets-zip?ids=${[...selected.value].join(',')}`)
}

function onDeleted(a) {
  items.value = items.value.filter((x) => x.id !== a.id)
  total.value--
}

async function upload(files) {
  const list = [...files]
  if (!list.length) return
  uploading.value = true
  let ok = 0
  try {
    for (const f of list) {
      try {
        await uploadFile(f)
        ok++
      } catch {
        /* 已提示 */
      }
    }
  } finally {
    uploading.value = false
  }
  if (ok) toast(`已上传 ${ok} 个文件`, 'success')
  reload()
}

function onDrop(e) {
  dragging.value = false
  upload(e.dataTransfer.files)
}

onMounted(async () => {
  modelOpts.value = (await api.get('/api/assets/models')).map((m) => ({ label: m, value: m }))
  resizeObs = new ResizeObserver(([entry]) => { width.value = entry.contentRect.width })
  if (wall.value) resizeObs.observe(wall.value)
  observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting && !loading.value && items.value.length < total.value) load()
  }, { rootMargin: '600px' })
  observer.observe(sentinel.value)
  load()
})
onUnmounted(() => {
  observer?.disconnect()
  resizeObs?.disconnect()
})
</script>

<style scoped>
.gallery { max-width: 1560px; position: relative; min-height: 100%; }
.filters { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 16px; }
.kind-tabs { width: 280px; }
.f-select { width: 120px; }
.f-select.wide { width: 200px; }
.search { width: 220px; }
.batch-bar { display: flex; align-items: center; gap: 8px; padding: 10px 14px; margin-bottom: 14px; border-radius: 12px; background: color-mix(in srgb, var(--primary) 8%, var(--panel)); border: 1px solid color-mix(in srgb, var(--primary) 30%, transparent); position: sticky; top: 0; z-index: 5; }
.wall { display: grid; grid-template-columns: repeat(var(--cols), 1fr); gap: 12px; align-items: start; }
.col { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.tile { position: relative; border-radius: 12px; overflow: hidden; cursor: pointer; background: var(--panel-2); border: 2px solid transparent; transition: border-color .15s, transform .15s; }
.tile:hover { transform: translateY(-2px); }
.tile.selected { border-color: var(--primary); }
.media { position: relative; width: 100%; }
.media img, .media video { width: 100%; height: 100%; object-fit: cover; display: block; }
.audio-tile { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: var(--muted); padding: 12px; font-size: 12px; background: linear-gradient(135deg, color-mix(in srgb, var(--primary) 12%, var(--panel-2)), var(--panel-2)); }
.audio-tile span { max-width: 100%; }
.badge { position: absolute; left: 8px; top: 8px; display: flex; align-items: center; gap: 3px; font-size: 11px; color: #fff; background: rgba(0, 0, 0, .5); padding: 2px 7px; border-radius: 10px; }
.overlay { position: absolute; inset: auto 0 0 0; padding: 28px 10px 10px; background: linear-gradient(transparent, rgba(0, 0, 0, .7)); opacity: 0; transition: opacity .2s; pointer-events: none; }
.tile:hover .overlay { opacity: 1; }
.ov-prompt { color: #fff; font-size: 12px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.fav { position: absolute; top: 8px; right: 8px; width: 30px; height: 30px; border-radius: 8px; border: none; background: rgba(0, 0, 0, .45); color: #fff; display: grid; place-items: center; cursor: pointer; opacity: 0; transition: opacity .15s; backdrop-filter: blur(4px); }
.fav.on { opacity: 1; color: #ffd166; }
.tile:hover .fav { opacity: 1; }
.check { position: absolute; top: 8px; left: 8px; width: 22px; height: 22px; border-radius: 50%; border: 2px solid #fff; background: rgba(0, 0, 0, .3); color: transparent; display: grid; place-items: center; }
.tile.selected .check { background: var(--primary); border-color: var(--primary); color: #fff; }
.loading-wall { margin-top: 12px; }
.loading-wall .tile { border: none; }
.sentinel { height: 1px; }
.drop-mask { position: fixed; inset: 0; z-index: 1000; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--primary); font-size: 16px; font-weight: 600; background: color-mix(in srgb, var(--bg) 85%, transparent); border: 3px dashed var(--primary); pointer-events: none; }
.slide-enter-active, .slide-leave-active { transition: all .2s; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(-6px); }
@media (hover: none) { .fav { opacity: 1; } }
@media (max-width: 760px) {
  .kind-tabs, .search, .f-select.wide { width: 100%; }
  .wall, .col { gap: 8px; }
}
</style>
