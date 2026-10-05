<template>
  <div class="tb" :class="layout">
    <n-input v-model:value="q" size="small" clearable :placeholder="`搜索${LABEL[category]}`" class="tb-search">
      <template #prefix><Search :size="14" /></template>
    </n-input>
    <div class="groups">
      <button v-for="g in groups" :key="g" type="button" class="group" :class="{ active: group === g }" @click="group = g">{{ g }}</button>
    </div>
    <!-- 带变量的模板：先填写变量 -->
    <div v-if="filling" class="fill">
      <div class="fill-head">
        <span class="icon">{{ filling.icon || '📝' }}</span>
        <b class="ellipsis">{{ filling.title }}</b>
        <span class="spacer" />
        <n-button size="tiny" quaternary @click="filling = null">返回</n-button>
      </div>
      <div v-for="v in vars" :key="v.name" class="fill-row">
        <label>{{ v.name }}</label>
        <n-input v-model:value="values[v.name]" size="small" :placeholder="v.default || `填写${v.name}`" @keydown.enter.prevent="confirmFill" />
      </div>
      <div class="fill-preview">{{ preview }}</div>
      <n-button type="primary" size="small" block @click="confirmFill">使用此模板</n-button>
    </div>
    <div v-else class="items">
      <button v-for="t in filtered" :key="t.id" type="button" class="item" :title="t.content" @click="pick(t)">
        <span class="icon">{{ t.icon || '📝' }}</span>
        <span class="text">
          <span class="title">{{ t.title }}<span v-if="!t.shared" class="mine">我的</span><span v-if="hasVars(t)" class="var-tag">变量</span></span>
          <span class="desc">{{ t.content }}</span>
        </span>
      </button>
      <div v-if="!filtered.length" class="empty muted">没有匹配的模板</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { NButton, NInput } from 'naive-ui'
import { Search } from 'lucide-vue-next'
import { api } from '../api'
import { fillVariables, parseVariables } from '../utils/variables'

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

const filling = ref(null)
const values = reactive({})
const vars = computed(() => (filling.value ? parseVariables(filling.value.content) : []))
const preview = computed(() => fillVariables(filling.value?.content, values))
const hasVars = (t) => /\{\{[^{}]+\}\}/.test(t.content)

function pick(t) {
  if (!parseVariables(t.content).length) return emit('select', t)
  for (const k of Object.keys(values)) delete values[k]
  filling.value = t
}

function confirmFill() {
  const t = filling.value
  filling.value = null
  emit('select', { ...t, content: fillVariables(t.content, values) })
}

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
.var-tag { margin-left: 6px; font-size: 10.5px; font-weight: 500; padding: 0 5px; border-radius: 4px; color: var(--warning); background: color-mix(in srgb, var(--warning) 14%, transparent); }
.fill { display: flex; flex-direction: column; gap: 8px; }
.fill-head { display: flex; align-items: center; gap: 8px; min-width: 0; }
.fill-row { display: grid; grid-template-columns: 90px 1fr; align-items: center; gap: 8px; font-size: 13px; }
.fill-row label { color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fill-preview { font-size: 12.5px; color: var(--text-2); background: var(--panel-2); border-radius: 8px; padding: 8px 10px; white-space: pre-wrap; max-height: 160px; overflow: auto; line-height: 1.6; }
.empty { text-align: center; padding: 20px 0; font-size: 13px; }
</style>
