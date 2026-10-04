import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发时把 /api 与 /media 代理到本地后端（默认 8080）
const target = process.env.PWD_BACKEND || 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': { target, changeOrigin: true },
      '/media': { target, changeOrigin: true },
    },
  },
})
