<template>
  <div class="page">
    <div class="page-head">
      <h1>提示词库</h1>
      <span class="spacer" />
      <button class="primary" @click="edit()">＋ 新建</button>
    </div>
    <div class="row filters">
      <button v-for="f in FILTERS" :key="f.key" class="small" :class="{ primary: category === f.key }" @click="category = f.key">{{ f.label }}</button>
    </div>
    <div v-if="!filtered.length" class="empty card">暂无提示词模板</div>
    <div class="list">
      <div v-for="p in filtered" :key="p.id" class="card item">
        <div class="row">
          <strong class="grow">{{ p.title }}</strong>
          <span class="tag">{{ p.category === 'image' ? '图像' : '对话' }}</span>
        </div>
        <div class="content">{{ p.content }}</div>
        <div v-if="p.negative" class="muted neg">反向：{{ p.negative }}</div>
        <div class="row">
          <button v-if="p.category === 'image'" class="small primary" @click="useImage(p)">去生成</button>
          <button class="small" @click="copy(p.content)">复制</button>
          <span class="spacer" />
          <button class="small ghost" @click="edit(p)">编辑</button>
          <button class="small ghost danger" @click="remove(p)">删除</button>
        </div>
      </div>
    </div>

    <div v-if="form" class="modal-mask" @click.self="form = null">
      <form class="card modal" @submit.prevent="save">
        <h2>{{ form.id ? '编辑模板' : '新建模板' }}</h2>
        <div class="grid-2">
          <label class="field"><span>标题</span><input v-model="form.title" required /></label>
          <label class="field">
            <span>类型</span>
            <select v-model="form.category">
              <option value="image">图像提示词</option>
              <option value="chat">对话角色设定</option>
            </select>
          </label>
        </div>
        <label class="field"><span>内容</span><textarea v-model="form.content" rows="6" /></label>
        <label v-if="form.category === 'image'" class="field"><span>反向提示词</span><textarea v-model="form.negative" rows="2" /></label>
        <div class="row"><span class="spacer" /><button type="button" @click="form = null">取消</button><button class="primary">保存</button></div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, toast } from '../api'

const FILTERS = [
  { key: '', label: '全部' },
  { key: 'image', label: '图像' },
  { key: 'chat', label: '对话' },
]
const router = useRouter()
const prompts = ref([])
const category = ref('')
const form = ref(null)
const filtered = computed(() => prompts.value.filter((p) => !category.value || p.category === category.value))

async function load() {
  prompts.value = await api.get('/api/prompts')
}

function edit(p) {
  form.value = p ? { ...p } : { title: '', category: category.value || 'image', content: '', negative: '' }
}

async function save() {
  const { id, ...body } = form.value
  if (id) await api.put(`/api/prompts/${id}`, body)
  else await api.post('/api/prompts', body)
  form.value = null
  toast('已保存', 'success')
  load()
}

async function remove(p) {
  if (!confirm(`删除模板「${p.title}」？`)) return
  await api.del(`/api/prompts/${p.id}`)
  load()
}

function useImage(p) {
  router.push({ path: '/image', query: { prompt: p.content, negative: p.negative || undefined } })
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    toast('已复制', 'success', 1500)
  } catch {
    toast('复制失败', 'error')
  }
}

onMounted(load)
</script>

<style scoped>
.filters { margin-bottom: 16px; }
.list { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }
.item { display: flex; flex-direction: column; gap: 8px; }
.content { white-space: pre-wrap; word-break: break-word; flex: 1; max-height: 160px; overflow: auto; }
.neg { font-size: 12px; }
</style>
