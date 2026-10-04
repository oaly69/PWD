import { createRouter, createWebHistory } from 'vue-router'
import { api, loadSite, state } from './api'

const routes = [
  { path: '/install', component: () => import('./views/Install.vue'), meta: { public: true } },
  { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('./views/Layout.vue'),
    children: [
      { path: '', component: () => import('./views/Dashboard.vue'), meta: { title: '工作台' } },
      { path: 'chat/:id?', component: () => import('./views/Chat.vue'), meta: { title: '对话创作' } },
      { path: 'image', component: () => import('./views/Image.vue'), meta: { title: '图像生成' } },
      { path: 'gallery', component: () => import('./views/Gallery.vue'), meta: { title: '作品库' } },
      { path: 'prompts', component: () => import('./views/Prompts.vue'), meta: { title: '提示词库' } },
      { path: 'providers', component: () => import('./views/Providers.vue'), meta: { title: '模型服务' } },
      { path: 'settings', component: () => import('./views/Settings.vue'), meta: { title: '系统设置' } },
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
  if (!state.site.installed) {
    return to.path === '/install' ? true : '/install'
  }
  if (to.path === '/install') return '/'
  if (to.meta.public) return true
  if (!state.user) {
    try {
      state.user = await api.get('/api/auth/me', { silent: true })
    } catch {
      return { path: '/login', query: { next: to.fullPath } }
    }
  }
  return true
})

export default router
