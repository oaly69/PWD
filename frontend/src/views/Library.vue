<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>提示词与角色</h1>
        <div class="sub">内置 {{ builtinCount }} 个模板，也可以保存自己常用的提示词；创作时在输入框的「模板」中一键调用</div>
      </div>
      <span class="spacer" />
      <n-input v-model:value="q" clearable placeholder="搜索标题或内容" style="width: 220px">
        <template #prefix><Search :size="14" /></template>
      </n-input>
      <n-button type="primary" @click="edit()"><template #icon><Plus :size="16" /></template>新建{{ TABS[tab].unit }}</n-button>
    </div>

    <n-tabs v-model:value="tab" type="line" @update:value="group = '全部分组'">
      <n-tab v-for="(t, key) in TABS" :key="key" :name="key">{{ t.label }} ({{ count(key) }})</n-tab>
    </n-tabs>

    <div class="filters">
      <n-radio-group v-model:value="owner" size="small">
        <n-radio-button value="all">全部</n-radio-button>
        <n-radio-button value="mine">我的</n-radio-button>
        <n-radio-button value="shared">公共</n-radio-button>
      </n-radio-group>
      <div class="groups">
        <button v-for="g in groups" :key="g" type="button" class="group" :class="{ active: group === g }" @click="group = g">{{ g }}</button>
      </div>
    </div>

    <div class="grid">
      <div v-for="p in visible" :key="p.id" class="card">
        <div class="card-top">
          <div class="icon">{{ p.icon || TABS[p.category].icon }}</div>
          <div class="title-box">
            <div class="title ellipsis">{{ p.title }}</div>
            <div class="meta">
              <span v-if="!p.shared" class="tag mine">我的</span>
              <span v-else-if="p.builtin" class="tag">内置</span>
              <span v-else class="tag">共享</span>
              <span v-if="p.group" class="muted">{{ p.group }}</span>
            </div>
          </div>
          <n-dropdown trigger="click" :options="menu(p)" @select="(k) => onMenu(k, p)">
            <n-button quaternary circle size="small"><template #icon><Ellipsis :size="16" /></template></n-button>
          </n-dropdown>
        </div>
        <div class="content">{{ p.content }}</div>
        <div v-if="p.negative" class="neg"><span>反向</span>{{ p.negative }}</div>
        <div class="card-actions">
          <n-button v-if="p.category === 'chat'" size="small" type="primary" secondary @click="startChat(p)"><template #icon><MessageSquare :size="14" /></template>开始对话</n-button>
          <n-button v-else-if="p.category === 'image'" size="small" type="primary" secondary @click="useIn('image', p)"><template #icon><ImageIcon :size="14" /></template>生成图像</n-button>
          <n-button v-else size="small" type="primary" secondary @click="useIn('video', p)"><template #icon><Film :size="14" /></template>生成视频</n-button>
          <n-button size="small" quaternary @click="copy(p.content)"><template #icon><Copy :size="14" /></template></n-button>
        </div>
      </div>
    </div>
    <div v-if="visible.length < filtered.length" class="more"><n-button secondary @click="limit += 60">显示更多（{{ visible.length }}/{{ filtered.length }}）</n-button></div>
    <EmptyState v-if="loaded && !filtered.length" :icon="BookText" :title="q || group !== '全部分组' || owner !== 'all' ? '没有匹配的内容' : `还没有${TABS[tab].label}`">
      <n-button type="primary" @click="edit()">新建</n-button>
    </EmptyState>

    <n-modal v-model:show="showForm" preset="card" :title="form.id ? '编辑' : '新建'" style="width: min(640px, 94vw)">
      <n-form label-placement="top">
        <div class="form-row">
          <n-form-item label="图标" style="width: 90px">
            <n-popover trigger="click" placement="bottom-start">
              <template #trigger><button type="button" class="emoji-btn">{{ form.icon || '＋' }}</button></template>
              <div class="emoji-grid">
                <button v-for="e in EMOJIS" :key="e" type="button" @click="form.icon = e">{{ e }}</button>
              </div>
              <n-input v-model:value="form.icon" size="small" maxlength="4" placeholder="或输入 emoji" style="margin-top: 8px" />
            </n-popover>
          </n-form-item>
          <n-form-item label="名称" style="flex: 1; min-width: 160px"><n-input v-model:value="form.title" placeholder="例如：分镜编剧" /></n-form-item>
          <n-form-item label="类型" style="width: 130px">
            <n-select v-model:value="form.category" :options="CATEGORY_OPTIONS" />
          </n-form-item>
          <n-form-item label="分组" style="width: 140px">
            <n-select v-model:value="form.group" :options="groupOptions" filterable tag clearable placeholder="可选" />
          </n-form-item>
        </div>
        <n-form-item :label="form.category === 'chat' ? '角色设定（系统提示词）' : '提示词'" :show-feedback="false" style="margin-bottom: 18px">
          <div style="width: 100%">
            <n-input v-model:value="form.content" type="textarea" :autosize="{ minRows: 6, maxRows: 16 }" />
            <div class="muted var-hint" v-pre>支持变量：写成 {{主题}} 或 {{风格|赛博朋克}}（竖线后为默认值），在创作页使用模板时会弹出表单填写。</div>
          </div>
        </n-form-item>
        <n-form-item v-if="form.category === 'image'" label="反向提示词">
          <n-input v-model:value="form.negative" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" />
        </n-form-item>
        <n-checkbox v-if="admin" v-model:checked="form.shared">共享给所有用户</n-checkbox>
      </n-form>
      <template #footer>
        <div class="row"><span class="spacer" /><n-button @click="showForm = false">取消</n-button><n-button type="primary" :disabled="!form.title.trim()" @click="save">保存</n-button></div>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCheckbox, NDropdown, NForm, NFormItem, NInput, NModal, NPopover, NRadioButton, NRadioGroup, NSelect, NTab, NTabs } from 'naive-ui'
import { BookText, Copy, Ellipsis, Film, Image as ImageIcon, MessageSquare, Plus, Search } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import { api, confirmDialog, toast } from '../api'
import { store } from '../store'
import { copyText } from '../utils/format'

const TABS = {
  chat: { label: '对话角色', unit: '角色', icon: '🤖' },
  image: { label: '图像提示词', unit: '提示词', icon: '🎨' },
  video: { label: '视频提示词', unit: '提示词', icon: '🎬' },
}
const CATEGORY_OPTIONS = Object.entries(TABS).map(([value, t]) => ({ label: t.label, value }))
const EMOJIS = ['🤖', '✍️', '🎬', '🎨', '🌐', '🧠', '📚', '💼', '🧑‍💻', '📷', '🎵', '🎮', '🍳', '✈️', '💡', '🔮', '🌆', '🏮', '🧸', '🍜', '🌸', '🐱', '🚀', '⚡']

const router = useRouter()
const prompts = ref([])
const loaded = ref(false)
const tab = ref('chat')
const q = ref('')
const owner = ref('all')
const group = ref('全部分组')
const limit = ref(60)
const showForm = ref(false)
const form = ref({})

const admin = computed(() => !!store.user?.is_admin)
const builtinCount = computed(() => prompts.value.filter((p) => p.builtin).length)
const count = (c) => prompts.value.filter((p) => p.category === c).length
const inTab = computed(() => prompts.value.filter((p) => p.category === tab.value))
const groups = computed(() => ['全部分组', ...new Set(inTab.value.map((p) => p.group).filter(Boolean))])
const groupOptions = computed(() => [...new Set(prompts.value.filter((p) => p.category === form.value.category).map((p) => p.group).filter(Boolean))].map((g) => ({ label: g, value: g })))

const filtered = computed(() => {
  const k = q.value.trim().toLowerCase()
  return inTab.value.filter((p) => {
    if (owner.value === 'mine' && p.shared) return false
    if (owner.value === 'shared' && !p.shared) return false
    if (group.value !== '全部分组' && p.group !== group.value) return false
    return !k || `${p.title}${p.content}`.toLowerCase().includes(k)
  })
})
const visible = computed(() => filtered.value.slice(0, limit.value))

watch([tab, q, owner, group], () => { limit.value = 60 })

const canEdit = (p) => !p.shared || admin.value

function menu(p) {
  return [
    ...(canEdit(p) ? [{ label: '编辑', key: 'edit' }] : []),
    { label: '复制一份', key: 'dup' },
    ...(canEdit(p) ? [{ type: 'divider', key: 'd' }, { label: '删除', key: 'delete' }] : []),
  ]
}

async function load() {
  prompts.value = await api.get('/api/prompts')
  loaded.value = true
}

function edit(p) {
  form.value = p
    ? { ...p }
    : { title: '', category: tab.value, content: '', negative: '', icon: '', group: group.value === '全部分组' ? '' : group.value, shared: false }
  showForm.value = true
}

async function save() {
  const { id, title, category, content, negative, icon, group: g, shared } = form.value
  const body = { title, category, content, negative: negative || '', icon: icon || '', group: g || '', shared: !!shared }
  if (id) await api.put(`/api/prompts/${id}`, body)
  else await api.post('/api/prompts', body)
  showForm.value = false
  tab.value = category
  toast('已保存', 'success')
  load()
}

async function onMenu(key, p) {
  if (key === 'edit') edit(p)
  else if (key === 'dup') {
    await api.post('/api/prompts', { title: `${p.title} 副本`, category: p.category, content: p.content, negative: p.negative || '', icon: p.icon || '', group: p.group || '' })
    owner.value = 'mine'
    toast('已复制到「我的」，可以自由编辑', 'success')
    load()
  } else if (key === 'delete') {
    const extra = p.shared ? '这是公共模板，删除后所有用户都将看不到它。' : ''
    if (!(await confirmDialog({ title: '删除', content: `确定删除「${p.title}」？${extra}`, positiveText: '删除' }))) return
    await api.del(`/api/prompts/${p.id}`)
    load()
  }
}

async function startChat(p) {
  const c = await api.post('/api/conversations', { title: p.title, icon: p.icon, system_prompt: p.content })
  router.push(`/chat/${c.id}`)
}

function useIn(target, p) {
  router.push({ path: `/${target}`, query: { prompt: p.content, negative: p.negative || undefined } })
}

async function copy(text) {
  if (await copyText(text)) toast('已复制', 'success')
}

onMounted(load)
</script>

<style scoped>
.filters { display: flex; align-items: flex-start; gap: 14px; margin: 14px 0 6px; flex-wrap: wrap; }
.groups { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
.group { padding: 3px 12px; border-radius: 14px; border: 1px solid var(--border); background: var(--panel); color: var(--text-2); font-size: 12.5px; cursor: pointer; }
.group:hover { border-color: var(--primary); color: var(--text); }
.group.active { background: var(--primary); border-color: var(--primary); color: #fff; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; margin-top: 14px; }
.card { display: flex; flex-direction: column; gap: 10px; padding: 16px; border-radius: 14px; background: var(--panel); border: 1px solid var(--border); transition: border-color .15s, box-shadow .15s; }
.card:hover { border-color: color-mix(in srgb, var(--primary) 40%, var(--border)); box-shadow: var(--shadow); }
.card-top { display: flex; align-items: center; gap: 10px; }
.icon { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; font-size: 22px; background: var(--panel-2); flex-shrink: 0; }
.title-box { flex: 1; min-width: 0; }
.title { font-weight: 600; font-size: 15px; }
.meta { display: flex; gap: 6px; align-items: center; font-size: 12px; margin-top: 2px; }
.tag { font-size: 11px; padding: 0 6px; border-radius: 6px; background: var(--panel-2); color: var(--muted); }
.tag.mine { background: color-mix(in srgb, var(--primary) 14%, transparent); color: var(--primary); }
.var-hint { font-size: 12px; margin-top: 6px; }
.content { font-size: 13px; color: var(--text-2); line-height: 1.65; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; flex: 1; white-space: pre-wrap; }
.neg { font-size: 12px; color: var(--muted); display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }
.neg span { font-weight: 600; margin-right: 6px; }
.card-actions { display: flex; gap: 6px; }
.more { text-align: center; margin-top: 18px; }
.form-row { display: flex; gap: 12px; flex-wrap: wrap; }
.emoji-btn { width: 56px; height: 34px; border-radius: 8px; border: 1px solid var(--border); background: var(--panel); font-size: 20px; cursor: pointer; }
.emoji-grid { display: grid; grid-template-columns: repeat(8, 32px); gap: 2px; }
.emoji-grid button { width: 32px; height: 32px; border: none; background: none; font-size: 18px; cursor: pointer; border-radius: 6px; }
.emoji-grid button:hover { background: var(--panel-2); }
</style>
