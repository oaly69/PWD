<template>
  <div class="page dash">
    <section class="hero">
      <div class="hero-text">
        <h1>{{ greeting }}，{{ store.user?.username }}</h1>
        <p>今天想创作点什么？</p>
      </div>
      <div class="quick">
        <div class="quick-tabs">
          <button v-for="m in MODES" :key="m.key" :class="{ active: mode === m.key }" @click="mode = m.key">
            <component :is="m.icon" :size="15" />{{ m.label }}
          </button>
        </div>
        <div class="quick-box">
          <n-input v-model:value="quick" type="textarea" :bordered="false" :autosize="{ minRows: 2, maxRows: 6 }" :placeholder="current.placeholder" @keydown.enter.exact.prevent="go" />
          <n-button type="primary" circle size="large" :disabled="!quick.trim()" @click="go"><template #icon><ArrowUp :size="20" /></template></n-button>
        </div>
      </div>
    </section>

    <n-alert v-if="stats && stats.providers === 0" type="warning" :bordered="false" class="setup" title="还差一步">
      <div class="alert-row">
        <span v-if="store.user?.is_admin">还没有配置模型服务。添加一个 OpenAI 兼容接口或 ComfyUI 后就可以开始创作了。</span>
        <span v-else>管理员还没有配置可用的模型服务，请联系管理员。</span>
        <n-button v-if="store.user?.is_admin" size="small" type="primary" @click="$router.push('/providers')">添加模型服务</n-button>
      </div>
    </n-alert>
    <n-alert v-if="stats?.site?.pending_users" type="info" :bordered="false" class="setup" :title="`有 ${stats.site.pending_users} 个新用户等待审核`">
      <div class="alert-row">
        <span>新注册的用户需要通过审核后才能登录。</span>
        <n-button size="small" type="primary" @click="$router.push('/users')">去审核</n-button>
      </div>
    </n-alert>

    <section class="tools">
      <router-link v-for="t in TOOLS" :key="t.to" :to="t.to" class="tool" :style="{ '--c': t.color }">
        <div class="tool-icon"><component :is="t.icon" :size="22" /></div>
        <div>
          <div class="tool-title">{{ t.title }}</div>
          <div class="tool-desc">{{ t.desc }}</div>
        </div>
        <ChevronRight :size="16" class="tool-arrow" />
      </router-link>
    </section>

    <section class="row2">
      <div class="panel">
        <div class="panel-head"><h3>创作概览</h3></div>
        <div class="stats">
          <div v-for="c in statCards" :key="c.label" class="stat">
            <div class="stat-num">{{ c.value }}</div>
            <div class="stat-label">{{ c.label }}</div>
          </div>
        </div>
        <div class="chart">
          <div class="chart-title muted">近 14 天生成数量</div>
          <div class="bars">
            <div v-for="d in stats?.daily || []" :key="d.date" class="bar-wrap" :title="`${d.date}：${d.count}`">
              <div class="bar" :style="{ height: `${(d.count / maxDaily) * 100}%` }" :class="{ zero: !d.count }" />
              <span class="bar-label">{{ d.date.slice(8) }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>最近对话</h3><router-link to="/chat" class="more">全部</router-link></div>
        <div v-if="convs.length" class="convs">
          <router-link v-for="c in convs" :key="c.id" :to="`/chat/${c.id}`" class="conv">
            <span class="conv-icon">{{ c.icon || '💬' }}</span>
            <span class="ellipsis">{{ c.title }}</span>
            <span class="spacer" />
            <span class="muted time">{{ relativeTime(c.updated_at) }}</span>
          </router-link>
        </div>
        <EmptyState v-else compact :icon="MessageSquare" title="还没有对话" />
      </div>
    </section>

    <section class="panel">
      <div class="panel-head"><h3>最近作品</h3><router-link to="/gallery" class="more">作品库</router-link></div>
      <div v-if="recent.length" class="recent">
        <div v-for="(a, i) in recent" :key="a.id" class="recent-item" @click="viewer = i">
          <img v-if="a.kind === 'image'" :src="a.thumb_url" loading="lazy" />
          <video v-else-if="a.kind === 'video'" :src="a.url + '#t=0.1'" muted preload="metadata" />
          <div v-else class="audio"><Music :size="22" /></div>
        </div>
      </div>
      <EmptyState v-else compact :icon="ImageIcon" title="还没有作品" desc="生成的图片、视频和语音会出现在这里" />
    </section>
    <MediaViewer v-model:index="viewer" :items="recent" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NAlert, NButton, NInput } from 'naive-ui'
import { ArrowUp, AudioLines, ChevronRight, Film, Image as ImageIcon, MessageSquare, Music } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import MediaViewer from '../components/MediaViewer.vue'
import { api } from '../api'
import { store } from '../store'
import { formatBytes, relativeTime } from '../utils/format'

const MODES = [
  { key: 'chat', label: '对话', icon: MessageSquare, placeholder: '问点什么，或让 AI 帮你写点什么…', to: '/chat' },
  { key: 'image', label: '图像', icon: ImageIcon, placeholder: '描述你想生成的画面…', to: '/image' },
  { key: 'video', label: '视频', icon: Film, placeholder: '描述你想生成的视频场景…', to: '/video' },
]
const TOOLS = [
  { to: '/chat', title: '对话创作', desc: '写文案、编剧本、头脑风暴', icon: MessageSquare, color: '#6d5dfc' },
  { to: '/image', title: '图像生成', desc: '文生图、图生图、风格预设', icon: ImageIcon, color: '#e0457b' },
  { to: '/video', title: '视频生成', desc: '文生视频、首帧生视频', icon: Film, color: '#0f9f8f' },
  { to: '/speech', title: '语音合成', desc: '多音色文本转语音', icon: AudioLines, color: '#d97706' },
]

const router = useRouter()
const mode = ref('chat')
const quick = ref('')
const stats = ref(null)
const recent = ref([])
const convs = ref([])
const viewer = ref(-1)

const current = computed(() => MODES.find((m) => m.key === mode.value))
const greeting = computed(() => {
  const h = new Date().getHours()
  return h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好'
})
const maxDaily = computed(() => Math.max(1, ...(stats.value?.daily || []).map((d) => d.count)))
const statCards = computed(() => {
  const s = stats.value || {}
  return [
    { label: '图片', value: s.images ?? '-' },
    { label: '视频', value: s.videos ?? '-' },
    { label: '音频', value: s.audios ?? '-' },
    { label: '对话', value: s.conversations ?? '-' },
    { label: '收藏', value: s.favorites ?? '-' },
    { label: '存储', value: s.storage_bytes != null ? formatBytes(s.storage_bytes) : '-' },
  ]
})

function go() {
  const text = quick.value.trim()
  if (!text) return
  if (mode.value === 'chat') router.push({ path: '/chat', query: { q: text } })
  else router.push({ path: current.value.to, query: { prompt: text } })
}

onMounted(async () => {
  try {
    const [s, a, c] = await Promise.all([api.get('/api/stats'), api.get('/api/assets?limit=16'), api.get('/api/conversations')])
    stats.value = s
    recent.value = a.items
    convs.value = c.slice(0, 6)
  } catch {
    /* 离开页面或网络中断时忽略 */
  }
})
</script>

<style scoped>
.dash { max-width: 1200px; display: flex; flex-direction: column; gap: 20px; }
.hero { position: relative; border-radius: 20px; padding: 36px 36px 28px; overflow: hidden; background:
  radial-gradient(1200px 300px at 0% 0%, color-mix(in srgb, var(--primary) 22%, transparent), transparent 60%),
  radial-gradient(800px 260px at 100% 100%, color-mix(in srgb, #ff7ac6 18%, transparent), transparent 60%), var(--panel); border: 1px solid var(--border); }
.hero h1 { margin: 0; font-size: 28px; letter-spacing: -.01em; }
.hero p { margin: 6px 0 20px; color: var(--text-2); }
.quick { max-width: 760px; }
.quick-tabs { display: flex; gap: 4px; margin-bottom: 8px; }
.quick-tabs button { display: flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 8px; border: none; background: transparent; color: var(--text-2); cursor: pointer; font-size: 13px; }
.quick-tabs button.active { background: var(--panel); color: var(--primary); font-weight: 600; box-shadow: var(--shadow); }
.quick-box { display: flex; align-items: flex-end; gap: 10px; padding: 10px 10px 10px 6px; background: var(--panel); border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--shadow); }
.quick-box:focus-within { border-color: var(--primary); }
.quick-box :deep(.n-input) { background: transparent; }
.setup { border-radius: 12px; }
.alert-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: space-between; }
.tools { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.tool { display: flex; align-items: center; gap: 12px; padding: 16px; border-radius: 14px; background: var(--panel); border: 1px solid var(--border); color: var(--text); transition: all .15s; }
.tool:hover { border-color: var(--c); transform: translateY(-2px); box-shadow: var(--shadow); }
.tool-icon { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; background: color-mix(in srgb, var(--c) 14%, transparent); color: var(--c); flex-shrink: 0; }
.tool-title { font-weight: 600; }
.tool-desc { font-size: 12px; color: var(--muted); margin-top: 2px; }
.tool-arrow { margin-left: auto; color: var(--muted); flex-shrink: 0; }
.row2 { display: grid; grid-template-columns: 1.4fr 1fr; gap: 20px; }
.panel { background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 18px 20px; }
.panel-head { display: flex; align-items: center; margin-bottom: 12px; }
.panel-head h3 { margin: 0; font-size: 15px; }
.more { margin-left: auto; font-size: 13px; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(96px, 1fr)); gap: 8px; }
.stat { padding: 10px 12px; border-radius: 10px; background: var(--panel-2); }
.stat-num { font-size: 20px; font-weight: 700; white-space: nowrap; }
.stat-label { font-size: 12px; color: var(--muted); }
.chart { margin-top: 18px; }
.chart-title { font-size: 12px; margin-bottom: 8px; }
.bars { display: flex; align-items: flex-end; gap: 6px; height: 110px; }
.bar-wrap { flex: 1; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; gap: 4px; }
.bar { width: 100%; max-width: 26px; border-radius: 6px 6px 2px 2px; background: linear-gradient(180deg, var(--primary), color-mix(in srgb, var(--primary) 55%, transparent)); min-height: 3px; transition: height .3s; }
.bar.zero { background: var(--panel-3); }
.bar-label { font-size: 10px; color: var(--muted); }
.convs { display: flex; flex-direction: column; }
.conv { display: flex; align-items: center; gap: 10px; padding: 9px 8px; border-radius: 8px; color: var(--text); font-size: 13.5px; min-width: 0; }
.conv:hover { background: var(--panel-2); }
.conv-icon { width: 20px; text-align: center; }
.time { font-size: 12px; white-space: nowrap; }
.recent { display: grid; grid-template-columns: repeat(8, 1fr); gap: 8px; }
.recent-item { aspect-ratio: 1; border-radius: 10px; overflow: hidden; cursor: pointer; background: var(--panel-2); }
.recent-item img, .recent-item video { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform .25s; }
.recent-item:hover img { transform: scale(1.05); }
.audio { height: 100%; display: grid; place-items: center; color: var(--muted); }
@media (max-width: 1080px) {
  .tools { grid-template-columns: repeat(2, 1fr); }
  .row2 { grid-template-columns: 1fr; }
  .recent { grid-template-columns: repeat(4, 1fr); }
}
@media (max-width: 640px) {
  .hero { padding: 24px 18px 18px; }
  .hero h1 { font-size: 22px; }
  .tools { grid-template-columns: 1fr; }
}
</style>
