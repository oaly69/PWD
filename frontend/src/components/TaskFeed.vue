<template>
  <div class="feed">
    <div v-if="loading && !tasks.length" class="skeletons">
      <div v-for="i in 2" :key="i" class="task-card"><div class="sk-line shimmer" /><div class="sk-block shimmer" /></div>
    </div>
    <EmptyState v-else-if="!tasks.length" :icon="emptyIcon" :title="emptyTitle" :desc="emptyDesc" />

    <div v-for="t in tasks" :key="t.id" class="task-card">
      <div class="head">
        <n-tag size="small" round :bordered="false" :type="STATUS_TYPE[t.status]">
          <template v-if="active(t)" #icon><n-spin :size="10" /></template>
          {{ STATUS_TEXT[t.status] }}<template v-if="t.status === 'running' && t.progress"> · {{ t.progress }}%</template>
        </n-tag>
        <span v-if="t.params?.batch_id" class="batch-tag" :title="`批量任务 ${t.params.batch_id}`"><Layers :size="11" /> {{ t.params.batch_index }}/{{ t.params.batch_total }}</span>
        <span class="meta ellipsis">{{ summary(t) }}</span>
        <span class="spacer" />
        <span class="time">{{ relativeTime(t.created_at) }}</span>
        <n-dropdown trigger="click" :options="menu(t)" @select="(k) => onMenu(k, t)">
          <n-button quaternary circle size="tiny"><template #icon><Ellipsis :size="16" /></template></n-button>
        </n-dropdown>
      </div>
      <div class="prompt" :title="t.prompt">{{ t.prompt }}</div>

      <n-progress v-if="t.status === 'running' && kind === 'video'" type="line" :percentage="t.progress || 0" :show-indicator="false" :height="4" style="margin-bottom: 10px" />
      <div v-if="t.status === 'failed'" class="error"><CircleAlert :size="14" /> {{ t.error }}</div>

      <!-- 生成中占位 -->
      <div v-if="active(t) && kind !== 'tts'" class="grid" :class="kind">
        <div v-for="i in placeholderCount(t)" :key="i" class="ph shimmer" :style="ratioStyle(t)">
          <component :is="kind === 'video' ? Film : ImageIcon" :size="22" :stroke-width="1.5" />
        </div>
      </div>
      <div v-else-if="active(t)" class="audio-ph shimmer" />

      <!-- 结果 -->
      <div v-else-if="t.assets.length" class="grid" :class="kind">
        <div v-for="a in t.assets" :key="a.id" class="result" :class="a.kind">
          <template v-if="a.kind === 'image'">
            <img :src="a.thumb_url || a.url" loading="lazy" @click="open(a)" />
            <div class="hover">
              <button title="收藏" :class="{ on: a.favorite }" @click.stop="toggleFav(a)"><Star :size="15" :fill="a.favorite ? 'currentColor' : 'none'" /></button>
              <button title="作为参考图" @click.stop="emit('use-ref', a)"><ImagePlus :size="15" /></button>
              <button title="下载" @click.stop="downloadUrl(a.url, `pwd-${a.id}`)"><Download :size="15" /></button>
            </div>
          </template>
          <video v-else-if="a.kind === 'video'" :src="a.url" controls preload="metadata" loop />
          <div v-else class="audio-row">
            <audio :src="a.url" controls preload="none" />
            <n-button quaternary circle size="small" @click="downloadUrl(a.url, `pwd-${a.id}`)"><template #icon><Download :size="15" /></template></n-button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="hasMore" class="more"><n-button :loading="loading" secondary @click="load">加载更多</n-button></div>
    <MediaViewer v-model:index="viewerIndex" :items="viewerItems" @deleted="onDeleted" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { NButton, NDropdown, NProgress, NSpin, NTag } from 'naive-ui'
import { AudioLines, CircleAlert, Download, Ellipsis, Film, Image as ImageIcon, ImagePlus, Layers, Star } from 'lucide-vue-next'
import { api, confirmDialog, toast } from '../api'
import { STATUS_TEXT, STATUS_TYPE } from '../constants'
import { copyText, downloadUrl, relativeTime } from '../utils/format'
import EmptyState from './EmptyState.vue'
import MediaViewer from './MediaViewer.vue'

const props = defineProps({ kind: { type: String, required: true } })
const emit = defineEmits(['reuse', 'use-ref'])

const PAGE = 20
const tasks = ref([])
const loading = ref(false)
const hasMore = ref(false)
const viewerIndex = ref(-1)
let timer = null

const emptyIcon = computed(() => ({ image: ImageIcon, video: Film, tts: AudioLines })[props.kind])
const emptyTitle = computed(() => ({ image: '开始你的第一张作品', video: '开始生成第一个视频', tts: '把文字变成声音' })[props.kind])
const emptyDesc = computed(() => ({
  image: '在左侧输入提示词，选择风格与比例，点击生成。支持上传参考图进行图生图。',
  video: '视频生成通常需要几分钟，提交后可以离开页面，完成后会在右下角提醒你。',
  tts: '输入文本、选择音色，即可合成语音，结果会自动保存到作品库。',
})[props.kind])

const viewerItems = computed(() => tasks.value.flatMap((t) => t.assets.filter((a) => a.kind === 'image')))

const active = (t) => t.status === 'pending' || t.status === 'running'

function summary(t) {
  const p = t.params || {}
  const parts = [t.model]
  if (p.size) parts.push(p.size)
  if (p.style) parts.push(p.style)
  if (p.seconds) parts.push(`${p.seconds}s`)
  if (p.voice) parts.push(p.voice)
  if (p.reference_asset_ids?.length) parts.push('参考图')
  return parts.join(' · ')
}

function placeholderCount(t) {
  return props.kind === 'image' ? t.params?.n || 1 : 1
}

function ratioStyle(t) {
  const [w, h] = String(t.params?.size || '1x1').split('x').map(Number)
  return { aspectRatio: w && h ? `${w} / ${h}` : '1 / 1' }
}

function menu(t) {
  const items = [
    { label: '复用参数', key: 'reuse' },
    { label: '复制提示词', key: 'copy' },
  ]
  if (active(t)) items.push({ label: '取消任务', key: 'cancel' })
  else {
    items.push({ label: '重新生成', key: 'retry' })
    items.push({ label: '删除记录', key: 'delete' })
  }
  if (t.params?.batch_id) {
    const same = tasks.value.filter((x) => x.params?.batch_id === t.params.batch_id)
    items.push({ type: 'divider', key: 'd' })
    if (same.some(active)) items.push({ label: '取消整批未完成的任务', key: 'batch-cancel' })
    items.push({ label: '下载整批结果（zip）', key: 'batch-download' })
  }
  return items
}

async function batchDownload(bid) {
  const rows = await api.get(`/api/task-batches/${bid}`)
  const ids = rows.flatMap((x) => x.assets.map((a) => a.id))
  if (!ids.length) return toast('这一批还没有生成结果', 'info')
  downloadUrl(`/api/assets-zip?ids=${ids.join(',')}`)
}

async function onMenu(key, t) {
  if (key === 'reuse') emit('reuse', t)
  else if (key === 'copy') (await copyText(t.prompt)) && toast('已复制', 'success')
  else if (key === 'batch-cancel') {
    const r = await api.post(`/api/task-batches/${t.params.batch_id}/cancel`)
    toast(`已取消 ${r.cancelled} 个任务`, 'info')
    poll()
  } else if (key === 'batch-download') batchDownload(t.params.batch_id)
  else if (key === 'cancel') {
    await api.post(`/api/tasks/${t.id}/cancel`)
    toast('已取消', 'info')
  } else if (key === 'retry') add(await api.post(`/api/tasks/${t.id}/retry`))
  else if (key === 'delete') {
    if (!(await confirmDialog({ title: '删除记录', content: '仅删除生成记录，已生成的作品仍保留在作品库中。', positiveText: '删除' }))) return
    await api.del(`/api/tasks/${t.id}`)
    tasks.value = tasks.value.filter((x) => x.id !== t.id)
  }
}

function open(a) {
  viewerIndex.value = viewerItems.value.findIndex((x) => x.id === a.id)
}

async function toggleFav(a) {
  const r = await api.patch(`/api/assets/${a.id}`, { favorite: !a.favorite })
  a.favorite = r.favorite
}

function onDeleted(a) {
  for (const t of tasks.value) t.assets = t.assets.filter((x) => x.id !== a.id)
}

async function load() {
  loading.value = true
  try {
    const more = await api.get(`/api/tasks?kind=${props.kind}&limit=${PAGE}&offset=${tasks.value.length}`)
    tasks.value.push(...more)
    hasMore.value = more.length === PAGE
  } finally {
    loading.value = false
  }
}

async function poll() {
  const pending = tasks.value.filter(active)
  if (!pending.length) return
  try {
    // 一次取回所有进行中的任务；已不在列表中的说明刚结束，再单独取最终结果
    const live = new Map((await api.get(`/api/tasks?kind=${props.kind}&status=active&limit=100`, { silent: true })).map((x) => [x.id, x]))
    for (const t of pending) {
      const fresh = live.get(t.id) || (await api.get(`/api/tasks/${t.id}`, { silent: true }).catch(() => null))
      if (fresh) Object.assign(t, fresh)
    }
  } catch {
    /* 忽略轮询错误 */
  }
}

function add(task) {
  tasks.value.unshift(task)
}

defineExpose({ add })

onMounted(() => {
  load()
  timer = setInterval(poll, 2000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.feed { display: flex; flex-direction: column; gap: 14px; }
.task-card { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 14px 16px 16px; }
.head { display: flex; align-items: center; gap: 8px; min-width: 0; }
.batch-tag { display: inline-flex; align-items: center; gap: 3px; flex-shrink: 0; font-size: 11.5px; font-weight: 600; padding: 1px 7px; border-radius: 10px; color: var(--primary); background: color-mix(in srgb, var(--primary) 12%, transparent); }
.meta { font-size: 12px; color: var(--muted); min-width: 0; }
.time { font-size: 12px; color: var(--muted); white-space: nowrap; }
.prompt { margin: 8px 0 12px; font-size: 13.5px; line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: var(--text-2); }
.error { display: flex; gap: 6px; align-items: flex-start; color: var(--danger); font-size: 13px; background: color-mix(in srgb, var(--danger) 8%, transparent); padding: 8px 10px; border-radius: 8px; word-break: break-word; }
.error svg { flex-shrink: 0; margin-top: 3px; }
.grid { display: grid; gap: 10px; }
.grid.image { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); align-items: start; }
.grid.video { grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }
.grid.tts { grid-template-columns: 1fr; }
.ph { border-radius: 10px; display: grid; place-items: center; color: var(--muted); max-height: 360px; }
.audio-ph { height: 54px; border-radius: 27px; }
.result { position: relative; border-radius: 10px; overflow: hidden; background: var(--panel-2); }
.result.image img { width: 100%; display: block; cursor: zoom-in; transition: transform .25s; }
.result.image:hover img { transform: scale(1.02); }
.result video { width: 100%; display: block; max-height: 480px; background: #000; }
.result.audio { background: transparent; overflow: visible; }
.audio-row { display: flex; align-items: center; gap: 8px; }
.audio-row audio { flex: 1; height: 42px; }
.hover { position: absolute; right: 8px; bottom: 8px; display: flex; gap: 6px; opacity: 0; transition: opacity .15s; }
.result:hover .hover { opacity: 1; }
.hover button { width: 30px; height: 30px; border-radius: 8px; border: none; background: rgba(0, 0, 0, .55); color: #fff; display: grid; place-items: center; cursor: pointer; backdrop-filter: blur(4px); }
.hover button:hover { background: rgba(0, 0, 0, .75); }
.hover button.on { color: #ffd166; }
.skeletons .sk-line { height: 14px; width: 40%; border-radius: 6px; margin-bottom: 14px; }
.skeletons .sk-block { height: 220px; border-radius: 10px; }
.more { text-align: center; padding: 6px 0 20px; }
@media (hover: none) { .hover { opacity: 1; } }
</style>
