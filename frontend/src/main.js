import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { ApiError } from './api'
import './style.css'

const app = createApp(App)

// 接口错误已在请求层统一提示；页面切换导致的请求中断也无需报错
app.config.errorHandler = (err) => {
  if (err instanceof ApiError || err?.name === 'AbortError' || (err instanceof TypeError && /fetch/i.test(err.message))) return
  console.error(err)
}

app.use(router).mount('#app')

// PWA：生产环境注册 Service Worker（仅缓存静态资源，可添加到桌面 / 主屏幕）
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}))
}
