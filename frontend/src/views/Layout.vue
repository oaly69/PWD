<template>
  <n-layout has-sider class="shell">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="68"
      :width="232"
      :collapsed="collapsed"
      :native-scrollbar="false"
      class="sider"
      :class="{ mobile: isMobile, open: mobileOpen }"
    >
      <div class="brand" :class="{ collapsed }">
        <img src="/favicon.svg" alt="" />
        <span v-if="!collapsed" class="ellipsis">{{ store.site.site_name }}</span>
      </div>
      <n-menu
        :value="activeKey"
        :options="menuOptions"
        :collapsed="collapsed"
        :collapsed-width="68"
        :collapsed-icon-size="20"
        :indent="18"
        @update:value="navigate"
      />
      <div class="sider-foot" :class="{ collapsed }">
        <n-button quaternary :circle="collapsed" size="small" class="collapse-btn" @click="toggleCollapse">
          <template #icon><component :is="collapsed ? PanelLeftOpen : PanelLeftClose" :size="18" /></template>
          <span v-if="!collapsed">收起侧栏</span>
        </n-button>
      </div>
    </n-layout-sider>
    <div v-if="isMobile && mobileOpen" class="mask" @click="mobileOpen = false" />

    <n-layout class="main">
      <header class="topbar">
        <n-button v-if="isMobile" quaternary circle @click="mobileOpen = true"><template #icon><Menu :size="20" /></template></n-button>
        <div class="title">{{ route.meta.title }}</div>
        <span class="spacer" />
        <TaskCenter />
        <n-dropdown :options="themeOptions" trigger="click" @select="setThemeMode">
          <n-button quaternary circle :title="'主题'">
            <template #icon><component :is="themeIcon" :size="18" /></template>
          </n-button>
        </n-dropdown>
        <n-dropdown :options="userOptions" trigger="click" @select="onUser">
          <button class="avatar-btn">
            <span class="avatar">{{ (store.user?.username || '?').slice(0, 1).toUpperCase() }}</span>
            <span v-if="!isMobile" class="uname">{{ store.user?.username }}</span>
            <ChevronDown :size="14" />
          </button>
        </n-dropdown>
      </header>
      <main class="content" :class="{ full: route.meta.full }">
        <router-view v-slot="{ Component }">
          <keep-alive :include="['Chat']">
            <component :is="Component" :key="route.meta.full ? route.path.split('/')[1] : route.fullPath" />
          </keep-alive>
        </router-view>
      </main>
    </n-layout>
  </n-layout>
</template>

<script setup>
import { computed, h, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { NButton, NDropdown, NLayout, NLayoutSider, NMenu } from 'naive-ui'
import {
  AudioLines, BookText, ChevronDown, Film, GalleryHorizontalEnd, Image as ImageIcon, LayoutDashboard, LogOut, Menu,
  MessageSquare, Monitor, Moon, PanelLeftClose, PanelLeftOpen, Plug, Settings, Sun,
} from 'lucide-vue-next'
import TaskCenter from '../components/TaskCenter.vue'
import { api } from '../api'
import { loadProviders, store } from '../store'
import { setThemeMode, themeMode } from '../composables/theme'

const route = useRoute()
const router = useRouter()
const width = ref(window.innerWidth)
const isMobile = computed(() => width.value < 860)
const mobileOpen = ref(false)
let savedCollapsed = false
try { savedCollapsed = localStorage.getItem('pwd.sider') === '1' } catch { /* 忽略 */ }
const desktopCollapsed = ref(savedCollapsed)
const collapsed = computed(() => (isMobile.value ? false : desktopCollapsed.value))

const icon = (C) => () => h(C, { size: 18 })
const link = (to, label) => () => h(RouterLink, { to }, { default: () => label })

const menuOptions = [
  { label: link('/', '工作台'), key: '/', icon: icon(LayoutDashboard) },
  {
    type: 'group', label: '创作', key: 'create',
    children: [
      { label: link('/chat', '对话'), key: '/chat', icon: icon(MessageSquare) },
      { label: link('/image', '图像生成'), key: '/image', icon: icon(ImageIcon) },
      { label: link('/video', '视频生成'), key: '/video', icon: icon(Film) },
      { label: link('/speech', '语音合成'), key: '/speech', icon: icon(AudioLines) },
    ],
  },
  {
    type: 'group', label: '资产', key: 'assets',
    children: [
      { label: link('/gallery', '作品库'), key: '/gallery', icon: icon(GalleryHorizontalEnd) },
      { label: link('/library', '提示词与角色'), key: '/library', icon: icon(BookText) },
    ],
  },
  {
    type: 'group', label: '系统', key: 'system',
    children: [
      { label: link('/providers', '模型服务'), key: '/providers', icon: icon(Plug) },
      { label: link('/settings', '系统设置'), key: '/settings', icon: icon(Settings) },
    ],
  },
]

const activeKey = computed(() => (route.path === '/' ? '/' : `/${route.path.split('/')[1]}`))

const themeOptions = [
  { label: '浅色', key: 'light', icon: icon(Sun) },
  { label: '深色', key: 'dark', icon: icon(Moon) },
  { label: '跟随系统', key: 'system', icon: icon(Monitor) },
]
const themeIcon = computed(() => ({ light: Sun, dark: Moon, system: Monitor })[themeMode.value])

const userOptions = [
  { label: '系统设置', key: 'settings', icon: icon(Settings) },
  { type: 'divider', key: 'd' },
  { label: '退出登录', key: 'logout', icon: icon(LogOut) },
]

function navigate(key) {
  router.push(key)
}

function toggleCollapse() {
  desktopCollapsed.value = !desktopCollapsed.value
  try { localStorage.setItem('pwd.sider', desktopCollapsed.value ? '1' : '0') } catch { /* 忽略 */ }
}

async function onUser(key) {
  if (key === 'settings') router.push('/settings')
  if (key === 'logout') {
    await api.post('/api/auth/logout')
    store.user = null
    router.replace('/login')
  }
}

function onResize() {
  width.value = window.innerWidth
}

watch(() => route.fullPath, () => { mobileOpen.value = false })
onMounted(() => {
  window.addEventListener('resize', onResize)
  loadProviders()
})
onUnmounted(() => window.removeEventListener('resize', onResize))
</script>

<style scoped>
.shell { height: 100vh; }
.sider { z-index: 300; }
.sider :deep(.n-layout-sider-scroll-container) { display: flex; flex-direction: column; }
.brand { display: flex; align-items: center; gap: 10px; height: 60px; padding: 0 20px; font-weight: 700; font-size: 16px; flex-shrink: 0; }
.brand.collapsed { justify-content: center; padding: 0; }
.brand img { width: 30px; height: 30px; flex-shrink: 0; }
.sider :deep(.n-menu) { flex: 1; }
.sider :deep(.n-menu-item-group-title) { font-size: 11.5px; letter-spacing: .06em; }
.sider-foot { padding: 10px 12px 14px; }
.sider-foot.collapsed { display: flex; justify-content: center; }
.collapse-btn { width: 100%; justify-content: flex-start; color: var(--muted); }
.sider-foot.collapsed .collapse-btn { width: auto; }
.main { height: 100vh; display: flex; flex-direction: column; }
.main :deep(> .n-layout-scroll-container) { display: flex; flex-direction: column; height: 100%; }
.topbar { height: 56px; flex-shrink: 0; display: flex; align-items: center; gap: 6px; padding: 0 16px 0 24px; border-bottom: 1px solid var(--border); background: var(--bg); }
.title { font-weight: 600; font-size: 15px; }
.avatar-btn { display: flex; align-items: center; gap: 8px; border: none; background: none; color: var(--text); cursor: pointer; padding: 4px 8px 4px 4px; border-radius: 20px; margin-left: 4px; }
.avatar-btn:hover { background: var(--panel-2); }
.avatar { width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: linear-gradient(135deg, var(--primary), color-mix(in srgb, var(--primary) 55%, #ff7ac6)); color: #fff; font-weight: 700; font-size: 13px; }
.uname { font-size: 13px; }
.content { flex: 1; min-height: 0; overflow: auto; }
.content.full { overflow: hidden; display: flex; }
.content.full > :deep(*) { flex: 1; min-width: 0; }
.mask { position: fixed; inset: 0; background: rgba(0, 0, 0, .4); z-index: 250; }
.sider.mobile { position: fixed !important; top: 0; bottom: 0; left: 0; transform: translateX(-100%); transition: transform .2s; }
.sider.mobile.open { transform: none; }
@media (max-width: 860px) {
  .topbar { padding: 0 10px; }
}
</style>
