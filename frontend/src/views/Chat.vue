<template>
  <div class="chat">
    <aside class="convs">
      <button class="primary" style="width: 100%" @click="newConv">＋ 新对话</button>
      <div class="list">
        <div v-for="c in convs" :key="c.id" class="conv" :class="{ active: current && c.id === current.id }" @click="open(c.id)">
          <span class="grow ellipsis">{{ c.title }}</span>
          <button class="ghost small" title="删除" @click.stop="removeConv(c)">✕</button>
        </div>
        <div v-if="!convs.length" class="empty">暂无对话</div>
      </div>
    </aside>

    <section class="body" v-if="current">
      <div class="toolbar">
        <input v-model="current.title" class="title-input" @change="saveConv" />
        <select v-model="modelKey" @change="saveConv">
          <option value="">选择模型…</option>
          <optgroup v-for="p in chatProviders" :key="p.id" :label="p.name">
            <option v-for="m in p.chat_models" :key="m" :value="`${p.id}::${m}`">{{ m }}</option>
          </optgroup>
        </select>
        <button class="ghost" @click="showSystem = !showSystem">{{ showSystem ? '收起设定' : '角色设定' }}</button>
      </div>
      <div v-if="showSystem" class="system">
        <div class="row" style="margin-bottom: 6px">
          <strong class="grow">系统提示词（角色设定）</strong>
          <select v-if="chatPrompts.length" style="width: auto" @change="useTemplate($event)">
            <option value="">从提示词库选择…</option>
            <option v-for="p in chatPrompts" :key="p.id" :value="p.id">{{ p.title }}</option>
          </select>
        </div>
        <textarea v-model="current.system_prompt" rows="3" placeholder="例如：你是一名资深短视频编剧……" @change="saveConv" />
      </div>

      <div class="messages" ref="scroller">
        <div v-if="!current.messages.length" class="empty">开始你的创作吧 ✨</div>
        <div v-for="(m, i) in current.messages" :key="m.id || 'tmp' + i" class="msg" :class="m.role">
          <div class="bubble">
            <div v-if="m.role === 'assistant'" class="md" v-html="render(m.content)" />
            <div v-else class="plain">{{ m.content }}</div>
            <span v-if="m.streaming" class="cursor">▍</span>
          </div>
          <div class="ops" v-if="!m.streaming">
            <button class="ghost small" @click="copy(m.content)">复制</button>
            <button v-if="m.id" class="ghost small" @click="removeMsg(m)">删除</button>
            <button v-if="m.role === 'assistant' && i === current.messages.length - 1 && !sending" class="ghost small" @click="regenerate">重新生成</button>
          </div>
        </div>
      </div>

      <div class="composer">
        <textarea
          v-model="input"
          rows="3"
          placeholder="输入内容，Enter 发送，Shift+Enter 换行"
          @keydown.enter.exact.prevent="send"
        />
        <div class="row">
          <span class="muted hint">{{ currentModelLabel }}</span>
          <span class="spacer" />
          <button v-if="sending" class="danger" @click="stop">停止</button>
          <button v-else class="primary" :disabled="!input.trim()" @click="send">发送</button>
        </div>
      </div>
    </section>
    <section v-else class="body empty">选择或新建一个对话</section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { api, streamPost, toast } from '../api'

const route = useRoute()
const router = useRouter()
const convs = ref([])
const current = ref(null)
const providers = ref([])
const chatPrompts = ref([])
const input = ref('')
const sending = ref(false)
const showSystem = ref(false)
const scroller = ref(null)
let controller = null

const chatProviders = computed(() => providers.value.filter((p) => p.kind === 'openai' && p.enabled && p.chat_models.length))

const modelKey = computed({
  get: () => (current.value?.provider_id && current.value?.model ? `${current.value.provider_id}::${current.value.model}` : ''),
  set: (v) => {
    const [pid, ...rest] = v.split('::')
    current.value.provider_id = pid ? Number(pid) : null
    current.value.model = rest.join('::')
  },
})

const currentModelLabel = computed(() => {
  const p = providers.value.find((x) => x.id === current.value?.provider_id)
  return p && current.value.model ? `${p.name} / ${current.value.model}` : '未选择模型'
})

const render = (text) => DOMPurify.sanitize(marked.parse(text || ''))

async function loadConvs() {
  convs.value = await api.get('/api/conversations')
}

async function open(id) {
  if (sending.value) stop()
  if (String(route.params.id) !== String(id)) router.replace(`/chat/${id}`)
  current.value = await api.get(`/api/conversations/${id}`)
  showSystem.value = !!current.value.system_prompt && !current.value.messages.length
  scrollBottom()
}

async function newConv() {
  const c = await api.post('/api/conversations', {})
  convs.value.unshift(c)
  await open(c.id)
}

async function saveConv() {
  const { id, title, provider_id, model, system_prompt } = current.value
  await api.patch(`/api/conversations/${id}`, { title, provider_id, model, system_prompt })
  const item = convs.value.find((c) => c.id === id)
  if (item) item.title = title
}

async function removeConv(c) {
  if (!confirm(`删除对话「${c.title}」？`)) return
  await api.del(`/api/conversations/${c.id}`)
  convs.value = convs.value.filter((x) => x.id !== c.id)
  if (current.value?.id === c.id) {
    current.value = null
    router.replace('/chat')
  }
}

async function removeMsg(m) {
  await api.del(`/api/conversations/${current.value.id}/messages/${m.id}`)
  current.value.messages = current.value.messages.filter((x) => x.id !== m.id)
}

function useTemplate(e) {
  const p = chatPrompts.value.find((x) => String(x.id) === e.target.value)
  if (p) {
    current.value.system_prompt = p.content
    saveConv()
  }
  e.target.value = ''
}

function scrollBottom() {
  nextTick(() => {
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
  })
}

async function stream(body) {
  const conv = current.value
  const reply = { role: 'assistant', content: '', streaming: true }
  conv.messages.push(reply)
  const msg = conv.messages[conv.messages.length - 1]
  sending.value = true
  controller = new AbortController()
  try {
    await streamPost(`/api/conversations/${conv.id}/messages`, body, (ev) => {
      if (ev.delta) {
        msg.content += ev.delta
        scrollBottom()
      }
      if (ev.message_id) msg.id = ev.message_id
      if (ev.error) toast(ev.error, 'error', 6000)
    }, controller.signal)
  } catch (e) {
    if (e.name !== 'AbortError') console.error(e)
  } finally {
    msg.streaming = false
    sending.value = false
    controller = null
    // 重新加载以获得服务端的消息 ID 和标题
    const fresh = await api.get(`/api/conversations/${conv.id}`)
    if (current.value?.id === conv.id) current.value = fresh
    const item = convs.value.find((c) => c.id === conv.id)
    if (item) item.title = fresh.title
    scrollBottom()
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  if (!current.value.model) return toast('请先选择模型', 'error')
  input.value = ''
  current.value.messages.push({ role: 'user', content: text })
  scrollBottom()
  await stream({ content: text })
}

async function regenerate() {
  const msgs = current.value.messages
  while (msgs.length && msgs[msgs.length - 1].role === 'assistant') msgs.pop()
  await stream({ regenerate: true })
}

function stop() {
  controller?.abort()
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    toast('已复制', 'success', 1500)
  } catch {
    toast('复制失败', 'error')
  }
}

watch(() => route.params.id, (id) => {
  if (id && Number(id) !== current.value?.id) open(id)
})

onMounted(async () => {
  ;[providers.value, chatPrompts.value] = await Promise.all([api.get('/api/providers'), api.get('/api/prompts?category=chat')])
  await loadConvs()
  if (route.params.id) await open(route.params.id)
  else if (convs.value.length) await open(convs.value[0].id)
})
</script>

<style scoped>
.chat { display: flex; flex: 1; min-height: 0; height: 100%; }
.convs { width: 240px; flex-shrink: 0; border-right: 1px solid var(--border); padding: 12px; display: flex; flex-direction: column; gap: 10px; background: var(--panel); }
.list { overflow: auto; flex: 1; display: flex; flex-direction: column; gap: 2px; }
.conv { display: flex; align-items: center; padding: 6px 8px 6px 10px; border-radius: 8px; cursor: pointer; }
.conv:hover { background: var(--panel-2); }
.conv.active { background: var(--primary-soft); color: var(--primary); }
.conv button { opacity: 0; padding: 2px 6px; }
.conv:hover button { opacity: 1; }
.ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.body { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.body.empty { justify-content: center; }
.toolbar { display: flex; gap: 8px; padding: 10px 16px; border-bottom: 1px solid var(--border); background: var(--panel); }
.toolbar select { width: 260px; }
.title-input { flex: 1; border-color: transparent; font-weight: 600; }
.system { padding: 10px 16px; border-bottom: 1px solid var(--border); background: var(--panel); }
.messages { flex: 1; overflow: auto; padding: 20px 16px; display: flex; flex-direction: column; gap: 16px; }
.msg { display: flex; flex-direction: column; max-width: 860px; width: 100%; margin: 0 auto; }
.msg.user { align-items: flex-end; }
.bubble { padding: 10px 14px; border-radius: 12px; background: var(--panel); border: 1px solid var(--border); max-width: 100%; overflow-x: auto; }
.msg.user .bubble { background: var(--primary-soft); border-color: transparent; }
.plain { white-space: pre-wrap; word-break: break-word; }
.cursor { animation: blink 1s steps(1) infinite; color: var(--primary); }
@keyframes blink { 50% { opacity: 0; } }
.ops { display: flex; gap: 2px; opacity: 0; transition: opacity .15s; }
.msg:hover .ops { opacity: 1; }
.ops button { color: var(--muted); font-size: 12px; padding: 2px 6px; }
.composer { border-top: 1px solid var(--border); padding: 12px 16px; background: var(--panel); }
.composer textarea { min-height: 70px; margin-bottom: 8px; }
.hint { font-size: 12px; }
@media (max-width: 760px) {
  .chat { flex-direction: column; }
  .convs { width: 100%; max-height: 160px; border-right: none; border-bottom: 1px solid var(--border); }
  .toolbar { flex-wrap: wrap; }
  .toolbar select { width: 100%; }
}
</style>
