<template>
  <n-popover trigger="click" placement="bottom-end" :width="340" style="padding: 0">
    <template #trigger>
      <n-badge :value="store.activeTasks.length" :max="99" :show="store.activeTasks.length > 0" processing>
        <n-button quaternary circle>
          <template #icon><ListTodo :size="18" /></template>
        </n-button>
      </n-badge>
    </template>
    <div class="tc">
      <div class="tc-head">任务中心 <span class="muted">· {{ store.activeTasks.length }} 个进行中</span></div>
      <div class="tc-list">
        <div v-for="t in list" :key="t.id" class="tc-item" @click="go(t)">
          <component :is="ICON[t.kind]" :size="16" class="kind" />
          <div class="body">
            <div class="ellipsis prompt">{{ t.prompt }}</div>
            <n-progress v-if="t.status === 'running' && t.progress" type="line" :percentage="t.progress" :height="3" :show-indicator="false" />
            <div class="sub">
              <n-tag size="tiny" :bordered="false" :type="STATUS_TYPE[t.status]">{{ STATUS_TEXT[t.status] }}</n-tag>
              <span class="muted">{{ t.model }} · {{ relativeTime(t.created_at) }}</span>
            </div>
          </div>
          <n-button v-if="active(t)" quaternary circle size="tiny" title="取消" @click.stop="cancel(t)"><template #icon><X :size="14" /></template></n-button>
        </div>
        <div v-if="!list.length" class="muted empty">暂无任务</div>
      </div>
    </div>
  </n-popover>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NBadge, NButton, NPopover, NProgress, NTag } from 'naive-ui'
import { AudioLines, Clapperboard, Film, Image as ImageIcon, ListTodo, X } from 'lucide-vue-next'
import { api, ui } from '../api'
import { store } from '../store'
import { STATUS_TEXT, STATUS_TYPE } from '../constants'
import { relativeTime } from '../utils/format'

const ICON = { image: ImageIcon, video: Film, tts: AudioLines, render: Clapperboard }
const ROUTE = { image: '/image', video: '/video', tts: '/speech', render: '/projects' }
const LABEL = { image: '图像', video: '视频', tts: '语音', render: '成片' }
const router = useRouter()
const recent = ref([])
let timer = null
let known = new Set()

const active = (t) => t.status === 'pending' || t.status === 'running'
const list = computed(() => {
  const ids = new Set(store.activeTasks.map((t) => t.id))
  return [...store.activeTasks, ...recent.value.filter((t) => !ids.has(t.id))].slice(0, 12)
})

function go(t) {
  if (t.params?.project_id) return router.push(`/projects/${t.params.project_id}`)
  router.push(ROUTE[t.kind])
}

async function cancel(t) {
  await api.post(`/api/tasks/${t.id}/cancel`)
  refresh()
}

async function refresh() {
  try {
    const activeList = await api.get('/api/tasks?status=active&limit=50', { silent: true })
    const nowIds = new Set(activeList.map((t) => t.id))
    // 已结束的任务：通知用户
    for (const id of known) {
      if (nowIds.has(id)) continue
      const t = await api.get(`/api/tasks/${id}`, { silent: true }).catch(() => null)
      if (!t) continue
      recent.value = [t, ...recent.value.filter((x) => x.id !== t.id)].slice(0, 10)
      if (router.currentRoute.value.path === ROUTE[t.kind]) continue
      if (t.status === 'succeeded') {
        ui.notification?.success({ title: `${LABEL[t.kind]}生成完成`, content: t.prompt.slice(0, 60), duration: 6000, onClick: () => go(t) })
      } else if (t.status === 'failed') {
        ui.notification?.error({ title: `${LABEL[t.kind]}生成失败`, content: t.error.slice(0, 120), duration: 8000 })
      }
    }
    known = nowIds
    store.activeTasks = activeList
  } catch {
    /* 忽略 */
  }
}

onMounted(async () => {
  try {
    recent.value = await api.get('/api/tasks?limit=8', { silent: true })
  } catch {
    /* 忽略 */
  }
  refresh()
  timer = setInterval(refresh, 3000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.tc-head { padding: 12px 14px; font-weight: 600; border-bottom: 1px solid var(--border); }
.tc-list { max-height: 420px; overflow: auto; padding: 6px; }
.tc-item { display: flex; gap: 10px; align-items: flex-start; padding: 8px; border-radius: 8px; cursor: pointer; }
.tc-item:hover { background: var(--panel-2); }
.kind { margin-top: 3px; color: var(--muted); flex-shrink: 0; }
.body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.prompt { font-size: 13px; }
.sub { display: flex; gap: 6px; align-items: center; font-size: 12px; min-width: 0; }
.sub .muted { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { text-align: center; padding: 24px 0; font-size: 13px; }
</style>
