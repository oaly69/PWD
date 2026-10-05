import { createRouter, createWebHistory } from 'vue-router'
import { api, loadSite } from './api'
import { store } from './store'

const routes = [
  { path: '/install', component: () => import('./views/Install.vue'), meta: { public: true } },
  { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
  { path: '/register', component: () => import('./views/Login.vue'), meta: { public: true, register: true } },
  {
    path: '/',
    component: () => import('./views/Layout.vue'),
    children: [
      { path: '', component: () => import('./views/Dashboard.vue'), meta: { title: '工作台' } },
      { path: 'chat/:id?', component: () => import('./views/Chat.vue'), meta: { title: '对话', full: true } },
      { path: 'image', component: () => import('./views/ImageStudio.vue'), meta: { title: '图像生成', full: true } },
      { path: 'video', component: () => import('./views/VideoStudio.vue'), meta: { title: '视频生成', full: true } },
      { path: 'speech', component: () => import('./views/SpeechStudio.vue'), meta: { title: '语音合成', full: true } },
      { path: 'gallery', component: () => import('./views/Gallery.vue'), meta: { title: '作品库' } },
      { path: 'library', component: () => import('./views/Library.vue'), meta: { title: '提示词与角色' } },
      { path: 'providers', component: () => import('./views/Providers.vue'), meta: { title: '模型服务', admin: true } },
      { path: 'users', component: () => import('./views/Users.vue'), meta: { title: '用户管理', admin: true } },
      { path: 'settings', component: () => import('./views/Settings.vue'), meta: { title: '系统设置' } },
      { path: 'prompts', redirect: '/library' },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

let siteLoaded = false

router.beforeEach(async (to) => {
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
  const title = to.meta.title
  document.title = title ? `${title} · ${store.site.site_name}` : store.site.site_name
})

export default router
