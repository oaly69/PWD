<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>提示词与角色</h1>
        <div class="sub">沉淀常用的对话角色和图像提示词，在创作时一键调用</div>
      </div>
      <span class="spacer" />
      <n-input v-model:value="q" clearable placeholder="搜索" style="width: 200px">
        <template #prefix><Search :size="14" /></template>
      </n-input>
      <n-button type="primary" @click="edit()"><template #icon><Plus :size="16" /></template>新建{{ tab === 'chat' ? '角色' : '提示词' }}</n-button>
    </div>

    <n-tabs v-model:value="tab" type="line">
      <n-tab name="chat">对话角色 ({{ count('chat') }})</n-tab>
      <n-tab name="image">图像提示词 ({{ count('image') }})</n-tab>
    </n-tabs>

    <div class="grid">
      <div v-for="p in filtered" :key="p.id" class="card" :class="p.category">
        <div class="card-top">
          <div class="icon">{{ p.icon || (p.category === 'chat' ? '🤖' : '🎨') }}</div>
          <div class="title ellipsis">{{ p.title }}</div>
          <n-dropdown trigger="click" :options="MENU" @select="(k) => onMenu(k, p)">
            <n-button quaternary circle size="small"><template #icon><Ellipsis :size="16" /></template></n-button>
          </n-dropdown>
        </div>
        <div class="content">{{ p.content }}</div>
        <div v-if="p.negative" class="neg"><span>反向</span>{{ p.negative }}</div>
        <div class="card-actions">
          <n-button v-if="p.category === 'chat'" size="small" type="primary" secondary @click="startChat(p)"><template #icon><MessageSquare :size="14" /></template>开始对话</n-button>
          <template v-else>
            <n-button size="small" type="primary" secondary @click="useImage(p)"><template #icon><ImageIcon :size="14" /></template>生成图像</n-button>
            <n-button size="small" secondary @click="useVideo(p)"><template #icon><Film :size="14" /></template>生成视频</n-button>
          </template>
          <n-button size="small" quaternary @click="copy(p.content)"><template #icon><Copy :size="14" /></template></n-button>
        </div>
      </div>
    </div>
    <EmptyState v-if="!filtered.length" :icon="BookText" :title="q ? '没有匹配的内容' : tab === 'chat' ? '还没有对话角色' : '还没有图像提示词'" :desc="tab === 'chat' ? '角色就是预设好的系统提示词，例如「分镜编剧」「文案策划」' : '把常用的画面描述保存下来，生成时一键套用'">
      <n-button type="primary" @click="edit()">新建</n-button>
    </EmptyState>

    <n-modal v-model:show="showForm" preset="card" :title="form.id ? '编辑' : '新建'" style="width: min(620px, 94vw)">
      <n-form label-placement="top" @submit.prevent="save">
        <div class="form-row">
          <n-form-item label="图标" style="width: 110px">
            <n-popover trigger="click" placement="bottom-start">
              <template #trigger><button type="button" class="emoji-btn">{{ form.icon || '＋' }}</button></template>
              <div class="emoji-grid">
                <button v-for="e in EMOJIS" :key="e" type="button" @click="form.icon = e">{{ e }}</button>
              </div>
              <n-input v-model:value="form.icon" size="small" maxlength="4" placeholder="或输入 emoji" style="margin-top: 8px" />
            </n-popover>
          </n-form-item>
          <n-form-item label="名称" style="flex: 1"><n-input v-model:value="form.title" placeholder="例如：分镜编剧" /></n-form-item>
          <n-form-item label="类型" style="width: 140px">
            <n-select v-model:value="form.category" :options="[{ label: '对话角色', value: 'chat' }, { label: '图像提示词', value: 'image' }]" />
          </n-form-item>
        </div>
        <n-form-item :label="form.category === 'chat' ? '角色设定（系统提示词）' : '提示词'">
          <n-input v-model:value="form.content" type="textarea" :autosize="{ minRows: 6, maxRows: 16 }" />
        </n-form-item>
        <n-form-item v-if="form.category === 'image'" label="反向提示词">
          <n-input v-model:value="form.negative" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="row"><span class="spacer" /><n-button @click="showForm = false">取消</n-button><n-button type="primary" :disabled="!form.title.trim()" @click="save">保存</n-button></div>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NDropdown, NForm, NFormItem, NInput, NModal, NPopover, NSelect, NTab, NTabs } from 'naive-ui'
import { BookText, Copy, Ellipsis, Film, Image as ImageIcon, MessageSquare, Plus, Search } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import { api, confirmDialog, toast } from '../api'
import { copyText } from '../utils/format'

const EMOJIS = ['🤖', '✍️', '🎬', '🎨', '🌐', '🧠', '📚', '💼', '🧑‍💻', '📷', '🎵', '🎮', '🍳', '✈️', '💡', '🔮', '🌆', '🏮', '🧸', '🍜', '🌸', '🐱', '🚀', '⚡']
const MENU = [{ label: '编辑', key: 'edit' }, { label: '复制一份', key: 'dup' }, { type: 'divider', key: 'd' }, { label: '删除', key: 'delete' }]

const router = useRouter()
const prompts = ref([])
const tab = ref('chat')
const q = ref('')
const showForm = ref(false)
const form = ref({ title: '', category: 'chat', content: '', negative: '', icon: '' })

const count = (c) => prompts.value.filter((p) => p.category === c).length
const filtered = computed(() => {
  const k = q.value.trim().toLowerCase()
  return prompts.value.filter((p) => p.category === tab.value && (!k || `${p.title}${p.content}`.toLowerCase().includes(k)))
})

async function load() {
  prompts.value = await api.get('/api/prompts')
}

function edit(p) {
  form.value = p ? { ...p } : { title: '', category: tab.value, content: '', negative: '', icon: '' }
  showForm.value = true
}

async function save() {
  const { id, ...body } = form.value
  if (id) await api.put(`/api/prompts/${id}`, body)
  else await api.post('/api/prompts', body)
  showForm.value = false
  tab.value = body.category
  toast('已保存', 'success')
  load()
}

async function onMenu(key, p) {
  if (key === 'edit') edit(p)
  else if (key === 'dup') {
    const { id, ...body } = p
    await api.post('/api/prompts', { ...body, title: `${p.title} 副本` })
    load()
  } else if (key === 'delete') {
    if (!(await confirmDialog({ title: '删除', content: `确定删除「${p.title}」？`, positiveText: '删除' }))) return
    await api.del(`/api/prompts/${p.id}`)
    load()
  }
}

async function startChat(p) {
  const c = await api.post('/api/conversations', { title: p.title, icon: p.icon, system_prompt: p.content })
  router.push(`/chat/${c.id}`)
}

function useImage(p) {
  router.push({ path: '/image', query: { prompt: p.content, negative: p.negative || undefined } })
}
function useVideo(p) {
  router.push({ path: '/video', query: { prompt: p.content } })
}

async function copy(text) {
  if (await copyText(text)) toast('已复制', 'success')
}

onMounted(load)
</script>

<style scoped>
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; margin-top: 16px; }
.card { display: flex; flex-direction: column; gap: 10px; padding: 16px; border-radius: 14px; background: var(--panel); border: 1px solid var(--border); transition: border-color .15s, box-shadow .15s; }
.card:hover { border-color: color-mix(in srgb, var(--primary) 40%, var(--border)); box-shadow: var(--shadow); }
.card-top { display: flex; align-items: center; gap: 10px; }
.icon { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; font-size: 22px; background: var(--panel-2); flex-shrink: 0; }
.title { flex: 1; font-weight: 600; font-size: 15px; }
.content { font-size: 13px; color: var(--text-2); line-height: 1.65; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; flex: 1; white-space: pre-wrap; }
.neg { font-size: 12px; color: var(--muted); display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }
.neg span { font-weight: 600; margin-right: 6px; }
.card-actions { display: flex; gap: 6px; }
.form-row { display: flex; gap: 12px; flex-wrap: wrap; }
.emoji-btn { width: 56px; height: 34px; border-radius: 8px; border: 1px solid var(--border); background: var(--panel); font-size: 20px; cursor: pointer; }
.emoji-grid { display: grid; grid-template-columns: repeat(8, 32px); gap: 2px; }
.emoji-grid button { width: 32px; height: 32px; border: none; background: none; font-size: 18px; cursor: pointer; border-radius: 6px; }
.emoji-grid button:hover { background: var(--panel-2); }
</style>
