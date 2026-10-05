import { createRouter, createWebHistory } from 'vue-router'
import { api, loadSite, ui } from './api'
import { store } from './store'

// 侧边栏各页面的按需加载入口；登录后空闲时预取，首次点击菜单不再等待下载
const views = {
  Dashboard: () => import('./views/Dashboard.vue'),
  Chat: () => import('./views/Chat.vue'),
  ImageStudio: () => import('./views/ImageStudio.vue'),
  VideoStudio: () => import('./views/VideoStudio.vue'),
  SpeechStudio: () => import('./views/SpeechStudio.vue'),
  Projects: () => import('./views/Projects.vue'),
  ProjectStudio: () => import('./views/ProjectStudio.vue'),
  Gallery: () => import('./views/Gallery.vue'),
  Knowledge: () => import('./views/Knowledge.vue'),
  Library: () => import('./views/Library.vue'),
  Providers: () => import('./views/Providers.vue'),
  Users: () => import('./views/Users.vue'),
  Settings: () => import('./views/Settings.vue'),
}

const routes = [
  { path: '/install', component: () => import('./views/Install.vue'), meta: { public: true } },
  { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
  { path: '/register', component: () => import('./views/Login.vue'), meta: { public: true, register: true } },
  {
    path: '/',
    component: () => import('./views/Layout.vue'),
    children: [
      { path: '', component: views.Dashboard, meta: { title: '工作台' } },
      { path: 'chat/:id?', component: views.Chat, meta: { title: '对话', full: true } },
      { path: 'image', component: views.ImageStudio, meta: { title: '图像生成', full: true } },
      { path: 'video', component: views.VideoStudio, meta: { title: '视频生成', full: true } },
      { path: 'speech', component: views.SpeechStudio, meta: { title: '语音合成', full: true } },
      { path: 'projects', component: views.Projects, meta: { title: '短片项目' } },
      { path: 'projects/:id', component: views.ProjectStudio, meta: { title: '短片项目' } },
      { path: 'gallery', component: views.Gallery, meta: { title: '作品库' } },
      { path: 'knowledge', component: views.Knowledge, meta: { title: '知识库' } },
      { path: 'library', component: views.Library, meta: { title: '提示词与角色' } },
      { path: 'providers', component: views.Providers, meta: { title: '模型服务', admin: true } },
      { path: 'users', component: views.Users, meta: { title: '用户管理', admin: true } },
      { path: 'settings', component: views.Settings, meta: { title: '系统设置' } },
      { path: 'prompts', redirect: '/library' },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

let siteLoaded = false

let barTimer = null
const stopBar = (ok = true) => {
  clearTimeout(barTimer)
  barTimer = null
  ui.loadingBar?.[ok ? 'finish' : 'error']()
}

router.beforeEach(async (to) => {
  // 页面切换超过 150ms（首次下载页面代码等）时显示顶部进度条
  clearTimeout(barTimer)
  barTimer = setTimeout(() => ui.loadingBar?.start(), 150)
  if (!siteLoaded) {
    try {
      await loadSite()
      siteLoaded = true
    } catch {
      /* 后端不可用时继续，由页面处理 */
    }
  }
  if (!store.site.installed) return to.path === '/install' ? true : '/install'
  if (to.path === '/install') return '/'
  if (to.meta.public) return true
  if (!store.user) {
    try {
      store.user = await api.get('/api/auth/me', { silent: true })
    } catch {
      return { path: '/login', query: { next: to.fullPath } }
    }
  }
  if (to.matched.some((r) => r.meta.admin) && !store.user.is_admin) return '/'
  return true
})

router.afterEach((to) => {
  stopBar()
  const title = to.meta.title
  document.title = title ? `${title} · ${store.site.site_name}` : store.site.site_name
})

router.onError(() => stopBar(false))

let prefetched = false
/** 浏览器空闲时依次预取各页面代码（已登录用户进入主界面后调用一次）。 */
export function prefetchViews() {
  if (prefetched) return
  prefetched = true
  const queue = Object.values(views)
  const idle = window.requestIdleCallback || ((cb) => setTimeout(cb, 200))
  const next = () => {
    const load = queue.shift()
    if (load) load().catch(() => {}).finally(() => idle(next))
  }
  idle(next)
}

export default router
