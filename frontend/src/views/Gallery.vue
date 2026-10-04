<template>
  <div class="page">
    <div class="page-head">
      <h1>作品库</h1>
      <span class="spacer" />
      <label class="btn">
        上传素材
        <input type="file" accept="image/*,video/*,audio/*" multiple hidden @change="upload" />
      </label>
    </div>

    <div class="row wrap filters">
      <button v-for="f in FILTERS" :key="f.key" class="small" :class="{ primary: filter === f.key }" @click="setFilter(f.key)">{{ f.label }}</button>
      <span class="spacer" />
      <input v-model="q" class="search" placeholder="搜索提示词 / 模型" @keyup.enter="reload" />
    </div>

    <div v-if="!items.length && !loading" class="empty card">暂无作品</div>
    <div class="grid">
      <div v-for="(a, i) in items" :key="a.id" class="item" @click="preview = i">
        <img v-if="a.kind === 'image'" :src="a.url" loading="lazy" :alt="a.prompt" />
        <video v-else-if="a.kind === 'video'" :src="a.url" muted preload="metadata" />
        <div v-else class="file">🎵<br />{{ a.prompt }}</div>
        <button class="fav" :class="{ on: a.favorite }" @click.stop="toggleFav(a)">{{ a.favorite ? '★' : '☆' }}</button>
      </div>
    </div>
    <div v-if="items.length < total" style="text-align: center; margin-top: 16px">
      <button :disabled="loading" @click="load">加载更多（{{ items.length }}/{{ total }}）</button>
    </div>

    <div v-if="current" class="modal-mask" @click.self="preview = -1">
      <div class="card viewer">
        <div class="media">
          <img v-if="current.kind === 'image'" :src="current.url" />
          <video v-else-if="current.kind === 'video'" :src="current.url" controls autoplay />
          <audio v-else :src="current.url" controls />
        </div>
        <div class="info">
          <div class="row">
            <span class="tag">{{ current.source === 'upload' ? '上传' : '生成' }}</span>
            <span class="muted small-text">{{ formatTime(current.created_at) }}</span>
            <span class="spacer" />
            <button class="ghost small" @click="preview = -1">✕</button>
          </div>
          <div v-if="current.model" class="muted small-text" style="margin-top: 8px">模型：{{ current.model }}</div>
          <div class="prompt">{{ current.prompt || '（无提示词）' }}</div>
          <div class="row wrap">
            <button class="small" @click="toggleFav(current)">{{ current.favorite ? '★ 取消收藏' : '☆ 收藏' }}</button>
            <a class="btn small" :href="current.url" :download="'pwd-' + current.id">下载</a>
            <button v-if="current.prompt && current.source === 'generated'" class="small" @click="regenerate(current)">再次生成</button>
            <button class="small danger" @click="remove(current)">删除</button>
          </div>
          <div class="row nav">
            <button class="small" :disabled="preview <= 0" @click="preview--">← 上一张</button>
            <span class="spacer" />
            <button class="small" :disabled="preview >= items.length - 1" @click="preview++">下一张 →</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, formatTime, toast } from '../api'

const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'fav', label: '收藏' },
  { key: 'image', label: '图片' },
  { key: 'video', label: '视频' },
  { key: 'audio', label: '音频' },
]
const router = useRouter()
const items = ref([])
const total = ref(0)
const filter = ref('all')
const q = ref('')
const loading = ref(false)
const preview = ref(-1)
const current = computed(() => items.value[preview.value] || null)

function params() {
  const p = new URLSearchParams({ offset: items.value.length, limit: 40 })
  if (filter.value === 'fav') p.set('favorite', 'true')
  else if (filter.value !== 'all') p.set('kind', filter.value)
  if (q.value.trim()) p.set('q', q.value.trim())
  return p
}

async function load() {
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
  load()
}

function setFilter(key) {
  filter.value = key
  reload()
}

async function toggleFav(a) {
  const r = await api.patch(`/api/assets/${a.id}`, { favorite: !a.favorite })
  a.favorite = r.favorite
}

async function remove(a) {
  if (!confirm('确定删除该作品？文件将被永久删除。')) return
  await api.del(`/api/assets/${a.id}`)
  const i = items.value.findIndex((x) => x.id === a.id)
  items.value.splice(i, 1)
  total.value--
  if (preview.value >= items.value.length) preview.value = items.value.length - 1
}

function regenerate(a) {
  router.push({ path: '/image', query: { prompt: a.prompt } })
}

async function upload(e) {
  const files = [...e.target.files]
  for (const f of files) {
    const fd = new FormData()
    fd.append('file', f)
    try {
      await api.post('/api/assets/upload', fd)
    } catch {
      /* 已提示 */
    }
  }
  e.target.value = ''
  toast(`已上传 ${files.length} 个文件`, 'success')
  reload()
}

function onKey(e) {
  if (preview.value < 0) return
  if (e.key === 'Escape') preview.value = -1
  if (e.key === 'ArrowLeft' && preview.value > 0) preview.value--
  if (e.key === 'ArrowRight' && preview.value < items.value.length - 1) preview.value++
}

onMounted(() => {
  load()
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.filters { margin-bottom: 16px; }
.search { width: 240px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.item { position: relative; aspect-ratio: 1; border-radius: 10px; overflow: hidden; cursor: pointer; background: var(--panel-2); }
.item img, .item video { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform .2s; }
.item:hover img { transform: scale(1.04); }
.file { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; font-size: 12px; padding: 8px; text-align: center; word-break: break-all; }
.fav { position: absolute; top: 6px; right: 6px; padding: 2px 8px; border: none; background: rgba(0, 0, 0, .45); color: #fff; opacity: 0; }
.fav.on { opacity: 1; color: #ffd166; }
.item:hover .fav { opacity: 1; }
.viewer { display: flex; gap: 16px; max-width: 1200px; width: 100%; max-height: 92vh; padding: 14px; }
.media { flex: 1; min-width: 0; display: flex; align-items: center; justify-content: center; background: var(--panel-2); border-radius: 8px; }
.media img, .media video { max-width: 100%; max-height: 86vh; object-fit: contain; display: block; }
.info { width: 300px; flex-shrink: 0; display: flex; flex-direction: column; overflow: auto; }
.prompt { margin: 12px 0; white-space: pre-wrap; word-break: break-word; flex: 1; }
.nav { margin-top: 12px; }
.small-text { font-size: 12px; }
.btn.small { padding: 4px 10px; font-size: 13px; }
@media (max-width: 760px) {
  .viewer { flex-direction: column; overflow: auto; }
  .info { width: 100%; }
  .search { width: 100%; }
}
</style>
