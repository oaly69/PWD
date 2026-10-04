<template>
  <div class="page">
    <div class="page-head"><h1>你好，{{ state.user?.username }} 👋</h1></div>

    <div v-if="stats && stats.providers === 0" class="card notice">
      还没有配置任何模型服务，<router-link to="/providers">去添加</router-link> 一个 OpenAI 兼容接口或 ComfyUI 后即可开始创作。
    </div>

    <div class="stats">
      <div class="card stat" v-for="s in cards" :key="s.label">
        <div class="num">{{ s.value }}</div>
        <div class="muted">{{ s.label }}</div>
      </div>
    </div>

    <div class="quick">
      <router-link to="/chat" class="card q"><span>💬</span><div><h3>对话创作</h3><div class="muted">写文案、改剧本、头脑风暴</div></div></router-link>
      <router-link to="/image" class="card q"><span>🎨</span><div><h3>图像生成</h3><div class="muted">文生图，支持 OpenAI 兼容接口与 ComfyUI</div></div></router-link>
      <router-link to="/gallery" class="card q"><span>🖼️</span><div><h3>作品库</h3><div class="muted">管理生成结果与上传素材</div></div></router-link>
    </div>

    <h2 style="margin-top: 26px">最近作品</h2>
    <div v-if="recent.length" class="recent">
      <router-link v-for="a in recent" :key="a.id" to="/gallery"><img :src="a.url" loading="lazy" :alt="a.prompt" /></router-link>
    </div>
    <div v-else class="empty card">暂无作品</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, state } from '../api'

const stats = ref(null)
const recent = ref([])

const cards = computed(() => {
  const s = stats.value || {}
  return [
    { label: '模型服务', value: s.providers ?? '-' },
    { label: '对话', value: s.conversations ?? '-' },
    { label: '作品', value: s.assets ?? '-' },
    { label: '收藏', value: s.favorites ?? '-' },
    { label: '进行中任务', value: s.tasks_running ?? '-' },
  ]
})

onMounted(async () => {
  stats.value = await api.get('/api/stats')
  recent.value = (await api.get('/api/assets?kind=image&limit=12')).items
})
</script>

<style scoped>
.notice { margin-bottom: 16px; border-left: 4px solid var(--warning); }
.stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
.stat .num { font-size: 26px; font-weight: 700; }
.quick { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin-top: 16px; }
.q { display: flex; gap: 14px; align-items: center; color: var(--text); }
.q:hover { border-color: var(--primary); }
.q span { font-size: 30px; }
.q h3 { margin: 0 0 2px; }
.recent { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }
.recent img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px; display: block; background: var(--panel-2); }
</style>
