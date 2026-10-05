<template>
  <div class="tb" :class="layout">
    <n-input v-model:value="q" size="small" clearable :placeholder="`搜索${LABEL[category]}`" class="tb-search">
      <template #prefix><Search :size="14" /></template>
    </n-input>
    <div class="groups">
      <button v-for="g in groups" :key="g" type="button" class="group" :class="{ active: group === g }" @click="group = g">{{ g }}</button>
    </div>
    <div class="items">
      <button v-for="t in filtered" :key="t.id" type="button" class="item" :title="t.content" @click="emit('select', t)">
        <span class="icon">{{ t.icon || '📝' }}</span>
        <span class="text">
          <span class="title">{{ t.title }}<span v-if="!t.shared" class="mine">我的</span></span>
          <span class="desc">{{ t.content }}</span>
        </span>
      </button>
      <div v-if="!filtered.length" class="empty muted">没有匹配的模板</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { NInput } from 'naive-ui'
import { Search } from 'lucide-vue-next'
import { api } from '../api'

const props = defineProps({
  category: { type: String, required: true }, // chat / image / video
  layout: { type: String, default: 'list' }, // list / grid
})
const emit = defineEmits(['select'])
const LABEL = { chat: '角色', image: '图像提示词', video: '视频提示词' }

const templates = ref([])
const q = ref('')
const group = ref('全部')

const groups = computed(() => {
  const set = new Set(templates.value.map((t) => (t.shared ? t.group || '其他' : '我的')))
  return ['全部', ...(set.has('我的') ? ['我的'] : []), ...[...set].filter((g) => g !== '我的')]
})

const filtered = computed(() => {
  const k = q.value.trim().toLowerCase()
  return templates.value.filter((t) => {
    const g = t.shared ? t.group || '其他' : '我的'
    if (group.value !== '全部' && g !== group.value) return false
    return !k || `${t.title}${t.content}`.toLowerCase().includes(k)
  })
})

onMounted(async () => {
  templates.value = await api.get(`/api/prompts?category=${props.category}`, { silent: true }).catch(() => [])
})
</script>

<style scoped>
.tb { display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.groups { display: flex; flex-wrap: wrap; gap: 6px; }
.group { padding: 3px 10px; border-radius: 12px; border: 1px solid var(--border); background: var(--panel); color: var(--text-2); font-size: 12px; cursor: pointer; }
.group:hover { border-color: var(--primary); }
.group.active { background: var(--primary); border-color: var(--primary); color: #fff; }
.items { overflow: auto; display: flex; flex-direction: column; gap: 2px; }
.list .items { max-height: 340px; }
.grid .items { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; max-height: 60vh; align-content: start; }
.item { display: flex; gap: 10px; align-items: flex-start; text-align: left; padding: 8px; border: 1px solid transparent; border-radius: 10px; background: none; color: var(--text); cursor: pointer; }
.item:hover { background: var(--panel-2); }
.grid .item { border-color: var(--border); padding: 12px; background: var(--panel); }
.grid .item:hover { border-color: var(--primary); background: var(--panel); }
.icon { width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center; background: var(--panel-2); font-size: 16px; flex-shrink: 0; }
.grid .icon { width: 38px; height: 38px; font-size: 20px; border-radius: 10px; }
.text { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.title { font-weight: 600; font-size: 13px; }
.mine { margin-left: 6px; font-size: 11px; font-weight: 400; color: var(--primary); }
.desc { font-size: 12px; color: var(--muted); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.5; }
.grid .desc { -webkit-line-clamp: 3; }
.empty { text-align: center; padding: 20px 0; font-size: 13px; }
</style>
