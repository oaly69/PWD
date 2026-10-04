<template>
  <div class="layout" :class="{ open: menuOpen }">
    <aside class="side">
      <div class="logo">
        <img src="/favicon.svg" alt="" />
        <span>{{ state.site.site_name }}</span>
      </div>
      <nav>
        <router-link v-for="n in NAV" :key="n.to" :to="n.to" :class="{ active: isActive(n.to) }" @click="menuOpen = false">
          <span class="icon">{{ n.icon }}</span>{{ n.label }}
        </router-link>
      </nav>
      <div class="user">
        <span class="grow">👤 {{ state.user?.username }}</span>
        <button class="ghost small" @click="logout">退出</button>
      </div>
      <div class="ver muted">v{{ state.site.version }}</div>
    </aside>
    <div class="mask" @click="menuOpen = false" />
    <main class="main">
      <header class="topbar">
        <button class="ghost" @click="menuOpen = !menuOpen">☰</button>
        <strong>{{ route.meta.title }}</strong>
      </header>
      <router-view :key="route.path.startsWith('/chat') ? 'chat' : route.fullPath" />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, state } from '../api'

const NAV = [
  { to: '/', label: '工作台', icon: '🏠' },
  { to: '/chat', label: '对话创作', icon: '💬' },
  { to: '/image', label: '图像生成', icon: '🎨' },
  { to: '/gallery', label: '作品库', icon: '🖼️' },
  { to: '/prompts', label: '提示词库', icon: '📝' },
  { to: '/providers', label: '模型服务', icon: '🔌' },
  { to: '/settings', label: '系统设置', icon: '⚙️' },
]

const route = useRoute()
const router = useRouter()
const menuOpen = ref(false)

const isActive = (to) => (to === '/' ? route.path === '/' : route.path.startsWith(to))

async function logout() {
  await api.post('/api/auth/logout')
  state.user = null
  router.replace('/login')
}
</script>

<style scoped>
.layout { display: flex; height: 100%; }
.side {
  width: 220px; flex-shrink: 0; background: var(--panel); border-right: 1px solid var(--border);
  display: flex; flex-direction: column; padding: 16px 12px;
}
.logo { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 16px; padding: 0 8px 18px; }
.logo img { width: 30px; height: 30px; }
nav { display: flex; flex-direction: column; gap: 2px; flex: 1; }
nav a { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 8px; color: var(--text); }
nav a:hover { background: var(--panel-2); }
nav a.active { background: var(--primary-soft); color: var(--primary); font-weight: 600; }
.icon { width: 20px; text-align: center; }
.user { display: flex; align-items: center; gap: 8px; padding: 10px 8px 4px; border-top: 1px solid var(--border); }
.ver { font-size: 12px; padding: 0 8px; }
.main { flex: 1; min-width: 0; overflow: auto; display: flex; flex-direction: column; }
.topbar { display: none; }
.mask { display: none; }
@media (max-width: 760px) {
  .side { position: fixed; z-index: 200; top: 0; bottom: 0; left: 0; transform: translateX(-100%); transition: transform .2s; }
  .layout.open .side { transform: none; }
  .layout.open .mask { display: block; position: fixed; inset: 0; z-index: 150; background: rgba(0, 0, 0, .35); }
  .topbar { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--border); background: var(--panel); }
}
</style>
