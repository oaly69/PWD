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
