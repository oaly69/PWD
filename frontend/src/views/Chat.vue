<template>
  <div class="chat">
    <!-- 会话列表 -->
    <aside class="convs" :class="{ open: listOpen }">
      <div class="convs-head">
        <n-button type="primary" class="new-btn" @click="newConv()"><template #icon><Plus :size="16" /></template>新对话</n-button>
        <n-tooltip><template #trigger>
          <n-button secondary @click="rolePicker = 'new'"><template #icon><Bot :size="16" /></template></n-button>
        </template>从角色开始</n-tooltip>
      </div>
      <n-input v-model:value="search" size="small" clearable placeholder="搜索对话" class="search" @update:value="onSearch">
        <template #prefix><Search :size="14" /></template>
      </n-input>
      <div class="list">
        <template v-for="g in groups" :key="g.label">
          <div class="group">{{ g.label }}</div>
          <div
            v-for="c in g.items"
            :key="c.id"
            class="conv"
            :class="{ active: current && c.id === current.id }"
            @click="open(c.id)"
          >
            <span class="conv-icon">{{ c.icon || '💬' }}</span>
            <span class="conv-title ellipsis">{{ c.title }}</span>
            <n-dropdown trigger="click" :options="convMenu(c)" @select="(k) => onConvMenu(k, c)">
              <button class="conv-more" @click.stop><Ellipsis :size="15" /></button>
            </n-dropdown>
          </div>
        </template>
        <EmptyState v-if="!convs.length" compact :icon="MessageSquare" :title="search ? '没有匹配的对话' : '还没有对话'" />
      </div>
    </aside>
    <div v-if="listOpen" class="list-mask" @click="listOpen = false" />

    <!-- 对话区 -->
    <section class="body">
      <header class="chat-head">
        <n-button class="list-toggle" quaternary circle @click="listOpen = true"><template #icon><PanelLeftOpen :size="18" /></template></n-button>
        <template v-if="current">
          <span class="head-icon">{{ current.icon || '💬' }}</span>
          <div class="head-title ellipsis" title="点击重命名" @click="rename(current)">{{ current.title }}</div>
          <span class="spacer" />
          <ModelSelect v-model="modelKey" kind="chat" size="small" class="model-select" />
          <n-tooltip><template #trigger>
            <n-button quaternary circle @click="settingsOpen = true"><template #icon><SlidersHorizontal :size="18" /></template></n-button>
          </template>对话设置</n-tooltip>
          <n-tooltip><template #trigger>
            <n-button quaternary circle :disabled="!current.messages.length" @click="exportConv(current)"><template #icon><FileDown :size="18" /></template></n-button>
          </template>导出为 Markdown</n-tooltip>
        </template>
      </header>

      <div ref="scroller" class="messages" @scroll="onScroll" @click="(e) => handleCodeCopy(e)">
        <div v-if="current && !current.messages.length" class="welcome">
          <div class="welcome-icon">{{ current.icon || '✨' }}</div>
          <h2>{{ current.system_prompt ? current.title : '今天想创作点什么？' }}</h2>
          <p v-if="current.system_prompt" class="muted role-desc">{{ current.system_prompt.slice(0, 120) }}{{ current.system_prompt.length > 120 ? '…' : '' }}</p>
          <div class="suggestions">
            <button v-for="s in SUGGESTIONS" :key="s" class="suggestion" @click="input = s; focusInput()">{{ s }}</button>
          </div>
        </div>

        <div v-for="(m, i) in current?.messages || []" :key="m.id || 'tmp' + i" class="msg" :class="m.role">
          <div class="avatar" :class="m.role">
            <template v-if="m.role === 'user'">{{ (store.user?.username || 'U').slice(0, 1).toUpperCase() }}</template>
            <template v-else>{{ current.icon || '🤖' }}</template>
          </div>
          <div class="msg-main">
            <div v-if="m.role === 'assistant' && !(m.alternatives?.length > 1)" class="msg-meta">{{ m.model || current.model }}<span v-if="m.served_by" class="served" title="原服务请求失败，已自动切换"> · 由「{{ m.served_by }}」提供</span></div>
            <div v-if="m.attachments?.length" class="attachments">
              <img v-for="a in m.attachments" :key="a.id" :src="a.thumb_url || a.url" @click="preview(m.attachments, a)" />
            </div>
            <div v-if="m.files?.length" class="file-chips">
              <span v-for="f in m.files" :key="f.name" class="file-chip"><FileText :size="13" />{{ f.name }}<span class="muted">{{ formatChars(f.chars) }}</span></span>
            </div>

            <!-- 编辑用户消息 -->
            <div v-if="editing === m.id" class="edit-box">
              <n-input v-model:value="editText" type="textarea" :autosize="{ minRows: 2, maxRows: 12 }" />
              <div class="row edit-actions">
                <n-button size="small" @click="editing = null">取消</n-button>
                <n-button size="small" @click="saveEdit(m, false)">仅保存</n-button>
                <n-button size="small" type="primary" @click="saveEdit(m, true)">作为新分支发送</n-button>
              </div>
            </div>

            <!-- 多模型对比：同一问题的多个回答并排展示 -->
            <div v-else-if="m.alternatives?.length > 1" class="compare" :style="{ '--cols': Math.min(m.alternatives.length, 4) }">
              <div v-for="alt in m.alternatives" :key="alt.id || alt.model" class="compare-col" :class="{ chosen: !m.streaming && alt.id === m.id }">
                <div class="compare-head">
                  <span class="ellipsis" :title="alt.served_by ? `由「${alt.served_by}」提供` : alt.model">{{ alt.model }}<template v-if="alt.served_by"> ↻</template></span>
                  <span class="spacer" />
                  <n-button v-if="!m.streaming && !alt.streaming" quaternary size="tiny" @click="copy(alt.content)"><template #icon><Copy :size="13" /></template></n-button>
                  <n-tag v-if="!m.streaming && alt.id === m.id" size="small" type="primary" :bordered="false">当前</n-tag>
                  <n-button v-else-if="!m.streaming && alt.id" size="tiny" secondary @click="switchBranch(alt.id)">选用</n-button>
                </div>
                <div v-if="reasoningOf(alt) && !bodyOf(alt)" class="muted compare-think">思考中…</div>
                <div v-if="bodyOf(alt)" class="md" v-html="renderMarkdown(bodyOf(alt))" />
                <div v-if="alt.streaming && !bodyOf(alt) && !reasoningOf(alt)" class="typing"><span /><span /><span /></div>
                <div v-if="alt.error" class="msg-error"><CircleAlert :size="14" /> {{ alt.error }}</div>
              </div>
            </div>

            <template v-else>
              <div v-if="m.status" class="status-line"><Loader2 :size="13" class="spin" />{{ m.status }}</div>
              <div v-for="(t, ti) in m.tools || []" :key="ti" class="tool-call" :class="{ open: openTools.has(`${m.id || i}-${ti}`) }">
                <button class="tool-head" @click="toggleTool(`${m.id || i}-${ti}`)">
                  <Loader2 v-if="t.running" :size="13" class="spin" /><Wrench v-else :size="13" />
                  <span>{{ t.running ? '正在调用' : '已调用' }}「{{ t.label || t.name }}」</span>
                  <ChevronDown :size="13" class="chev" />
                </button>
                <div class="tool-body">
                  <div class="tool-label">参数</div><pre>{{ prettyArgs(t.args) }}</pre>
                  <template v-if="t.result"><div class="tool-label">结果</div><pre>{{ t.result }}</pre></template>
                </div>
                <div v-if="t.assets?.length" class="tool-assets">
                  <img v-for="a in t.assets" :key="a.id" :src="a.thumb_url || a.url" @click="preview(t.assets, a)" />
                </div>
              </div>
              <div v-if="reasoningOf(m)" class="reasoning" :class="{ open: openReasoning.has(m.id || i) || (m.streaming && !bodyOf(m)) }">
                <button class="reasoning-head" @click="toggleReasoning(m.id || i)">
                  <Brain :size="14" />
                  <span>{{ m.streaming && !bodyOf(m) ? '思考中…' : '思考过程' }}</span>
                  <ChevronDown :size="14" class="chev" />
                </button>
                <div class="reasoning-body">{{ reasoningOf(m) }}</div>
              </div>
              <div v-if="bodyOf(m) || m.role === 'user'" class="bubble" :class="m.role">
                <div v-if="m.role === 'assistant'" class="md" v-html="renderMarkdown(bodyOf(m))" />
                <div v-else class="plain">{{ m.content }}</div>
              </div>
              <div v-if="m.streaming && !bodyOf(m) && !reasoningOf(m)" class="typing"><span /><span /><span /></div>
              <div v-if="m.error" class="msg-error"><CircleAlert :size="14" /> {{ m.error }}</div>
              <div v-for="n in m.notices || []" :key="n" class="notice"><CircleAlert :size="13" /> {{ n }}</div>
              <div v-if="m.sources?.length" class="sources">
                <span class="muted src-title">参考来源</span>
                <component
                  :is="src.url ? 'a' : 'span'"
                  v-for="(src, si) in m.sources"
                  :key="si"
                  class="src"
                  :href="src.url"
                  target="_blank"
                  rel="noopener"
                  :title="src.snippet"
                >
                  <b>{{ si + 1 }}</b><Globe v-if="src.type === 'web'" :size="12" /><LibraryBig v-else :size="12" /><span class="ellipsis">{{ src.title || src.url }}</span>
                </component>
              </div>
            </template>
            <div v-if="!m.streaming && editing !== m.id" class="ops">
              <div v-if="m.siblings?.length > 1 && !(m.alternatives?.length > 1)" class="branch-nav">
                <button :disabled="sending || branchIndex(m) === 0" @click="switchSibling(m, -1)"><ChevronLeft :size="14" /></button>
                <span>{{ branchIndex(m) + 1 }} / {{ m.siblings.length }}</span>
                <button :disabled="sending || branchIndex(m) === m.siblings.length - 1" @click="switchSibling(m, 1)"><ChevronRight :size="14" /></button>
              </div>
              <n-button v-if="!(m.alternatives?.length > 1)" quaternary size="tiny" @click="copy(m.content)"><template #icon><Copy :size="13" /></template></n-button>
              <n-button v-if="m.role === 'user' && m.id" quaternary size="tiny" :disabled="sending" @click="startEdit(m)"><template #icon><Pencil :size="13" /></template></n-button>
              <n-tooltip v-if="m.role === 'assistant' && m.id"><template #trigger>
                <n-button quaternary size="tiny" :disabled="sending" @click="regenerate(m)"><template #icon><RefreshCw :size="13" /></template></n-button>
              </template>重新生成（保留原回答为另一个分支）</n-tooltip>
              <n-tooltip v-if="m.id"><template #trigger>
                <n-button quaternary size="tiny" :disabled="sending" @click="removeMsg(m)"><template #icon><Trash2 :size="13" /></template></n-button>
              </template>删除此消息及其后续分支</n-tooltip>
            </div>
          </div>
        </div>
        <div v-if="!current" class="welcome">
          <EmptyState :icon="MessageSquare" title="选择或新建一个对话" />
        </div>
      </div>

      <button v-if="!atBottom" class="to-bottom" @click="scrollBottom(true)"><ArrowDown :size="16" /></button>

      <div v-if="current" class="composer-wrap">
        <div class="composer" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
          <div v-if="pending.length || pendingFiles.length" class="pending">
            <div v-for="a in pending" :key="a.id" class="pending-item">
              <img :src="a.thumb_url || a.url" />
              <button @click="pending = pending.filter((x) => x.id !== a.id)"><X :size="11" /></button>
            </div>
            <div v-for="f in pendingFiles" :key="f.name" class="pending-file" :title="f.truncated ? '文档较长，只发送前 10 万字' : ''">
              <FileText :size="16" />
              <div class="pf-text"><div class="ellipsis">{{ f.name }}</div><div class="muted">{{ formatChars(f.chars) }}{{ f.truncated ? '（已截断）' : '' }}</div></div>
              <button @click="pendingFiles = pendingFiles.filter((x) => x !== f)"><X :size="11" /></button>
            </div>
          </div>
          <n-input
            ref="inputRef"
            v-model:value="input"
            type="textarea"
            :bordered="false"
            :autosize="{ minRows: 1, maxRows: 10 }"
            placeholder="输入消息，Enter 发送，Shift + Enter 换行，可粘贴图片"
            @keydown="onKeydown"
            @paste="onPaste"
          />
          <div class="composer-bar">
            <n-tooltip><template #trigger>
              <n-button quaternary circle size="small" :loading="uploading" @click="fileInput?.click()"><template #icon><Paperclip :size="16" /></template></n-button>
            </template>添加图片或文档（PDF、Word、PPT、Excel、TXT 等）</n-tooltip>
            <input ref="fileInput" type="file" :accept="`image/*,${DOC_ACCEPT}`" multiple hidden @change="(e) => { addFiles(e.target.files); e.target.value = '' }" />
            <n-popover trigger="click" placement="top-start" :show-arrow="false" @update:show="(v) => v && loadKbs()">
              <template #trigger>
                <n-button quaternary size="small" class="tool-btn" :type="kbIds.length ? 'primary' : 'default'">
                  <template #icon><LibraryBig :size="15" /></template><span class="btn-text">{{ kbIds.length ? `知识库 ${kbIds.length}` : '知识库' }}</span>
                </n-button>
              </template>
              <div class="pick-pop">
                <div class="field-label">对话时检索这些知识库</div>
                <n-checkbox-group :value="kbIds" @update:value="(v) => setParam('kb_ids', v.length ? v : null)">
                  <div v-for="k in kbs" :key="k.id" class="pick-row"><n-checkbox :value="k.id" :label="`${k.name}（${k.documents} 个文档）`" /></div>
                </n-checkbox-group>
                <div v-if="!kbs.length" class="muted hint">还没有知识库，<router-link to="/knowledge">去创建 →</router-link></div>
              </div>
            </n-popover>
            <n-tooltip v-if="settings.search_available"><template #trigger>
              <n-button quaternary size="small" class="tool-btn" :type="params.web_search ? 'primary' : 'default'" @click="setParam('web_search', params.web_search ? null : true)">
                <template #icon><Globe :size="15" /></template><span class="btn-text">联网</span>
              </n-button>
            </template>{{ params.web_search ? '已开启联网搜索，点击关闭' : '开启后每次提问都会先联网搜索' }}</n-tooltip>
            <n-popover trigger="click" placement="top-start" :show-arrow="false" @update:show="(v) => v && loadTools()">
              <template #trigger>
                <n-button quaternary size="small" class="tool-btn" :type="toolIds.length ? 'primary' : 'default'">
                  <template #icon><Wrench :size="15" /></template><span class="btn-text">{{ toolIds.length ? `工具 ${toolIds.length}` : '工具' }}</span>
                </n-button>
              </template>
              <div class="pick-pop tools-pop">
                <div class="field-label">允许模型调用的工具（需模型支持 Function Calling）</div>
                <n-spin :show="toolsLoading" size="small">
                  <n-checkbox-group :value="toolIds" @update:value="(v) => setParam('tools', v.length ? v : null)">
                    <div v-for="t in toolCatalog" :key="t.id" class="pick-row tool-row">
                      <n-checkbox :value="t.id" :disabled="!!t.error">
                        <span class="tool-name">{{ t.label }}</span>
                        <n-tag v-if="t.source === 'mcp'" size="tiny" :bordered="false">{{ t.server }}</n-tag>
                      </n-checkbox>
                      <div class="muted tool-desc">{{ t.error ? `连接失败：${t.error}` : t.description }}</div>
                    </div>
                  </n-checkbox-group>
                </n-spin>
              </div>
            </n-popover>
            <n-tooltip v-if="settings.stt_available"><template #trigger>
              <n-button quaternary circle size="small" :type="recording ? 'error' : 'default'" :loading="transcribing" @click="toggleRecord">
                <template #icon><component :is="recording ? Square : Mic" :size="15" /></template>
              </n-button>
            </template>{{ recording ? '点击结束录音并识别' : '语音输入' }}</n-tooltip>
            <n-popover trigger="click" placement="top-start" :show-arrow="false">
              <template #trigger>
                <n-button quaternary size="small" :type="compareKeys.length ? 'primary' : 'default'" class="compare-btn">
                  <template #icon><Columns3 :size="15" /></template>{{ compareKeys.length ? `对比 ${compareKeys.length} 个模型` : '多模型对比' }}
                </n-button>
              </template>
              <div class="compare-pop">
                <div class="field-label">同时发送给多个模型（最多 4 个），回答并排对比</div>
                <ModelSelect v-model="compareKeys" kind="chat" multiple placeholder="选择 2～4 个模型" style="width: 340px" />
                <div class="row" style="margin-top: 8px">
                  <span class="muted hint">对比后可在任一回答上点「选用」继续对话</span>
                  <span class="spacer" />
                  <n-button v-if="compareKeys.length" size="tiny" @click="compareKeys = []">关闭对比</n-button>
                </div>
              </div>
            </n-popover>
            <span class="muted model-label ellipsis">{{ compareKeys.length ? compareKeys.map((k) => splitModelKey(k)[1]).join(' · ') : modelLabel }}</span>
            <span class="spacer" />
            <n-button v-if="sending" type="error" secondary circle @click="stop"><template #icon><Square :size="14" fill="currentColor" /></template></n-button>
            <n-button v-else type="primary" circle :disabled="!input.trim() && !pending.length && !pendingFiles.length" @click="send"><template #icon><ArrowUp :size="18" /></template></n-button>
          </div>
        </div>
      </div>
    </section>

    <!-- 对话设置 -->
    <n-drawer v-model:show="settingsOpen" :width="380" placement="right">
      <n-drawer-content v-if="current" title="对话设置" closable>
        <div class="field-label">图标</div>
        <n-input v-model:value="current.icon" maxlength="4" placeholder="一个 emoji，例如 🎬" style="width: 160px" @blur="saveConv" />
        <div class="field-label" style="margin-top: 16px">角色设定（系统提示词）</div>
        <n-input v-model:value="current.system_prompt" type="textarea" :autosize="{ minRows: 5, maxRows: 14 }" placeholder="例如：你是一名资深短视频编剧……" @blur="saveConv" />
        <div class="row" style="margin-top: 6px">
          <n-button size="tiny" secondary @click="rolePicker = 'apply'">从角色库选择</n-button>
        </div>

        <div class="section-title">模型参数</div>
        <div class="param">
          <div class="field-label">温度 <span class="muted">{{ params.temperature ?? '默认' }}</span></div>
          <n-slider :value="params.temperature ?? 0.7" :min="0" :max="2" :step="0.1" @update:value="(v) => setParam('temperature', v)" />
          <div class="hint">越高越有创意，越低越严谨</div>
        </div>
        <div class="param">
          <div class="field-label">Top P <span class="muted">{{ params.top_p ?? '默认' }}</span></div>
          <n-slider :value="params.top_p ?? 1" :min="0" :max="1" :step="0.05" @update:value="(v) => setParam('top_p', v)" />
        </div>
        <div class="param">
          <div class="field-label">最大回复长度</div>
          <n-input-number :value="params.max_tokens ?? null" :min="1" :max="200000" placeholder="不限制" clearable @update:value="(v) => setParam('max_tokens', v)" />
        </div>
        <div class="param">
          <div class="field-label">携带历史消息数 <span class="muted">{{ params.context_count ?? 30 }}</span></div>
          <n-slider :value="params.context_count ?? 30" :min="1" :max="100" @update:value="(v) => setParam('context_count', v)" />
        </div>
        <n-button size="small" secondary @click="resetParams">恢复默认参数</n-button>
      </n-drawer-content>
    </n-drawer>

    <MediaViewer v-model:index="viewerIndex" :items="viewerItems" />

    <n-modal :show="!!rolePicker" preset="card" :title="rolePicker === 'new' ? '选择一个角色开始对话' : '为当前对话选择角色'" style="width: min(980px, 96vw)" @update:show="(v) => { if (!v) rolePicker = null }">
      <TemplateBrowser v-if="rolePicker" category="chat" layout="grid" @select="onRolePicked" />
    </n-modal>
  </div>
</template>

<script setup>
import { computed, h, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NCheckbox, NCheckboxGroup, NDrawer, NDrawerContent, NDropdown, NInput, NInputNumber, NModal, NPopover, NSlider, NSpin, NTag, NTooltip } from 'naive-ui'
import {
  ArrowDown, ArrowUp, Bot, Brain, ChevronDown, ChevronLeft, ChevronRight, CircleAlert, Columns3, Copy, FileText, Globe, LibraryBig, Loader2, Mic, Wrench, Ellipsis, FileDown, MessageSquare, PanelLeftOpen,
  Paperclip, Pencil, Plus, RefreshCw, Search, SlidersHorizontal, Square, Trash2, X,
} from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import TemplateBrowser from '../components/TemplateBrowser.vue'
import MediaViewer from '../components/MediaViewer.vue'
import ModelSelect from '../components/ModelSelect.vue'
import { api, confirmDialog, streamPost, toast, ui, uploadFile } from '../api'
import { loadProviders, loadSettings, providerName, splitModelKey, store } from '../store'
import { copyText, downloadUrl, groupByDate } from '../utils/format'
import { handleCodeCopy, renderMarkdown, splitThink } from '../utils/markdown'

defineOptions({ name: 'Chat' })

const SUGGESTIONS = [
  '帮我写一条关于秋日咖啡的小红书文案',
  '把这个故事梗概扩写成 6 个镜头的分镜脚本：',
  '给我 10 个科幻短片的创意点子',
  '帮我写一段赛博朋克城市的 AI 绘画提示词',
]

const route = useRoute()
const router = useRouter()
const convs = ref([])
const current = ref(null)
const rolePicker = ref(null) // 'new' 新建对话 / 'apply' 应用到当前对话
const search = ref('')
const input = ref('')
const pending = ref([])
const sending = ref(false)
const uploading = ref(false)
const dragging = ref(false)
const listOpen = ref(false)
const settingsOpen = ref(false)
const editing = ref(null)
const editText = ref('')
const openReasoning = ref(new Set())
const atBottom = ref(true)
const scroller = ref(null)
const inputRef = ref(null)
const fileInput = ref(null)
const viewerItems = ref([])
const viewerIndex = ref(-1)
const compareKeys = ref([])
const pendingFiles = ref([])
const kbs = ref([])
const toolCatalog = ref([])
const toolsLoading = ref(false)
const openTools = ref(new Set())
const settings = ref({})
const recording = ref(false)
const transcribing = ref(false)
let recorder = null
const DOC_ACCEPT = '.pdf,.docx,.pptx,.xlsx,.md,.markdown,.txt,.csv,.json,.html,.htm,.epub,.srt,.vtt,.log,.py,.js,.ts,.java,.go,.sql,.yaml,.yml,.xml'
let controller = null
let searchTimer = null

const groups = computed(() => groupByDate(convs.value))
const params = computed(() => current.value?.params || {})
const kbIds = computed(() => params.value.kb_ids || [])
const toolIds = computed(() => params.value.tools || [])
const formatChars = (n) => (n >= 10000 ? `${(n / 10000).toFixed(1)} 万字` : `${n} 字`)
const prettyArgs = (a) => {
  try { return JSON.stringify(JSON.parse(a || '{}'), null, 2) } catch { return a }
}

function toggleTool(key) {
  const s = new Set(openTools.value)
  s.has(key) ? s.delete(key) : s.add(key)
  openTools.value = s
}

async function loadKbs() {
  kbs.value = await api.get('/api/kb', { silent: true }).catch(() => [])
}

async function loadTools() {
  if (toolCatalog.value.length) return
  toolsLoading.value = true
  try {
    toolCatalog.value = await api.get('/api/tools', { silent: true })
  } catch {
    toolCatalog.value = []
  } finally {
    toolsLoading.value = false
  }
}

async function toggleRecord() {
  if (recording.value) {
    recorder?.stop()
    return
  }
  if (!navigator.mediaDevices?.getUserMedia) return toast('当前浏览器不支持录音（需要 HTTPS 访问）', 'error')
  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    return toast('无法使用麦克风，请检查浏览器权限', 'error')
  }
  const chunks = []
  recorder = new MediaRecorder(stream)
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)
  recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop())
    recording.value = false
    const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
    if (blob.size < 1000) return
    const fd = new FormData()
    fd.append('file', blob, `voice.${(recorder.mimeType || 'audio/webm').includes('mp4') ? 'mp4' : 'webm'}`)
    transcribing.value = true
    try {
      const r = await api.post('/api/audio/transcribe', fd)
      input.value = input.value ? `${input.value} ${r.text}` : r.text
      focusInput()
    } finally {
      transcribing.value = false
    }
  }
  recorder.start()
  recording.value = true
}

const modelKey = computed({
  get: () => (current.value?.provider_id && current.value?.model ? `${current.value.provider_id}::${current.value.model}` : ''),
  set: (v) => {
    const [pid, model] = splitModelKey(v)
    current.value.provider_id = pid
    current.value.model = model
    saveConv()
  },
})

const modelLabel = computed(() => (current.value?.model ? `${providerName(current.value.provider_id)} · ${current.value.model}` : '未选择模型'))


const reasoningOf = (m) => m.reasoning || splitThink(m.content).think
const bodyOf = (m) => (m.reasoning ? m.content : splitThink(m.content).body)

function convMenu(c) {
  return [
    { label: c.pinned ? '取消置顶' : '置顶', key: 'pin' },
    { label: '重命名', key: 'rename' },
    { label: 'AI 生成标题', key: 'title' },
    { label: '导出 Markdown', key: 'export' },
    { type: 'divider', key: 'd' },
    { label: '删除', key: 'delete' },
  ]
}

async function onConvMenu(key, c) {
  if (key === 'pin') {
    await api.patch(`/api/conversations/${c.id}`, { pinned: !c.pinned })
    c.pinned = !c.pinned
    if (current.value?.id === c.id) current.value.pinned = c.pinned
  } else if (key === 'rename') rename(c)
  else if (key === 'title') {
    const r = await api.post(`/api/conversations/${c.id}/title`)
    c.title = r.title
    if (current.value?.id === c.id) current.value.title = r.title
  } else if (key === 'export') exportConv(c)
  else if (key === 'delete') removeConv(c)
}

function rename(c) {
  const value = ref(c.title)
  ui.dialog.create({
    title: '重命名对话',
    content: () => h(NInput, { value: value.value, 'onUpdate:value': (v) => { value.value = v }, autofocus: true }),
    positiveText: '保存',
    negativeText: '取消',
    onPositiveClick: async () => {
      const title = value.value.trim() || c.title
      await api.patch(`/api/conversations/${c.id}`, { title })
      c.title = title
      const item = convs.value.find((x) => x.id === c.id)
      if (item) item.title = title
      if (current.value?.id === c.id) current.value.title = title
    },
  })
}

function exportConv(c) {
  downloadUrl(`/api/conversations/${c.id}/export`)
}

async function loadConvs() {
  const q = search.value.trim()
  convs.value = await api.get(`/api/conversations${q ? `?q=${encodeURIComponent(q)}` : ''}`)
}

function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(loadConvs, 250)
}

async function open(id) {
  listOpen.value = false
  if (current.value?.id === Number(id)) return
  if (sending.value) stop()
  editing.value = null
  if (String(route.params.id) !== String(id)) router.replace(`/chat/${id}`)
  current.value = await api.get(`/api/conversations/${id}`)
  scrollBottom(true)
}

async function newConv(body = {}) {
  const c = await api.post('/api/conversations', body)
  convs.value.unshift(c)
  await open(c.id)
  focusInput()
}

function onRolePicked(r) {
  const mode = rolePicker.value
  rolePicker.value = null
  if (mode === 'new') newConv({ title: r.title, icon: r.icon, system_prompt: r.content })
  else applyRole(r)
}

function applyRole(r) {
  current.value.system_prompt = r.content
  current.value.icon = r.icon || current.value.icon
  saveConv()
}

async function saveConv() {
  if (!current.value) return
  const { id, title, icon, provider_id, model, system_prompt, params: p } = current.value
  await api.patch(`/api/conversations/${id}`, { title, icon, provider_id, model, system_prompt, params: p || {} })
  const item = convs.value.find((c) => c.id === id)
  if (item) Object.assign(item, { title, icon })
}

function setParam(key, value) {
  current.value.params = { ...(current.value.params || {}), [key]: value ?? undefined }
  if (value == null) delete current.value.params[key]
  clearTimeout(setParam.t)
  setParam.t = setTimeout(() => { setParam.t = null; saveConv() }, 400)
}

/** 发送前把尚未保存的对话设置（知识库、联网、工具、参数）立即写入，避免与发送请求竞争。 */
async function flushParams() {
  if (!setParam.t) return
  clearTimeout(setParam.t)
  setParam.t = null
  await saveConv()
}

function resetParams() {
  current.value.params = {}
  saveConv()
}

async function removeConv(c) {
  if (!(await confirmDialog({ title: '删除对话', content: `确定删除「${c.title}」？此操作不可恢复。`, positiveText: '删除' }))) return
  await api.del(`/api/conversations/${c.id}`)
  convs.value = convs.value.filter((x) => x.id !== c.id)
  if (current.value?.id === c.id) {
    current.value = null
    router.replace('/chat')
  }
}

async function removeMsg(m) {
  await api.del(`/api/conversations/${current.value.id}/messages/${m.id}`)
  await refresh()
}

async function refresh() {
  const conv = current.value
  const fresh = await api.get(`/api/conversations/${conv.id}`)
  if (current.value?.id === conv.id) current.value = fresh
  return fresh
}

const branchIndex = (m) => Math.max(0, (m.siblings || []).indexOf(m.id))

async function switchBranch(messageId) {
  const conv = current.value
  const fresh = await api.post(`/api/conversations/${conv.id}/branch`, { message_id: messageId })
  if (current.value?.id === conv.id) current.value = fresh
}

function switchSibling(m, step) {
  const target = m.siblings[branchIndex(m) + step]
  if (target) switchBranch(target)
}

function startEdit(m) {
  editing.value = m.id
  editText.value = m.content
}

async function saveEdit(m, resend) {
  const conv = current.value
  const text = editText.value
  editing.value = null
  if (!resend) {
    await api.patch(`/api/conversations/${conv.id}/messages/${m.id}`, { content: text })
    m.content = text
    return
  }
  // 编辑后发送：原消息保留为另一个分支
  const idx = conv.messages.findIndex((x) => x.id === m.id)
  conv.messages.splice(idx)
  conv.messages.push({ role: 'user', content: text, attachments: m.attachments })
  await stream({ content: text, attachments: (m.attachments || []).map((a) => a.id), parent_id: m.parent_id ?? null })
}

function toggleReasoning(key) {
  const s = new Set(openReasoning.value)
  s.has(key) ? s.delete(key) : s.add(key)
  openReasoning.value = s
}

function onScroll() {
  const el = scroller.value
  if (el) atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

function scrollBottom(force = false) {
  nextTick(() => {
    const el = scroller.value
    if (el && (force || atBottom.value)) el.scrollTop = el.scrollHeight
  })
}

function focusInput() {
  nextTick(() => inputRef.value?.focus())
}

async function addFiles(files) {
  const list = [...files]
  const images = list.filter((f) => f.type.startsWith('image/'))
  const docs = list.filter((f) => !f.type.startsWith('image/'))
  if (!list.length) return
  uploading.value = true
  try {
    for (const f of images) pending.value.push(await uploadFile(f))
    for (const f of docs) {
      const fd = new FormData()
      fd.append('file', f)
      try {
        pendingFiles.value.push(await api.post('/api/files/extract', fd))
      } catch {
        /* 已提示 */
      }
    }
  } finally {
    uploading.value = false
  }
}

function onPaste(e) {
  const files = [...(e.clipboardData?.files || [])]
  if (files.some((f) => f.type.startsWith('image/'))) {
    e.preventDefault()
    addFiles(files)
  }
}

function onDrop(e) {
  dragging.value = false
  addFiles(e.dataTransfer.files)
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

function compareModels() {
  return compareKeys.value.map((k) => {
    const [provider_id, model] = splitModelKey(k)
    return { provider_id, model }
  })
}

async function stream(body) {
  await flushParams()
  const conv = current.value
  const models = compareModels()
  if (models.length) body.models = models
  conv.messages.push({ role: 'assistant', content: '', reasoning: '', streaming: true, model: models.length === 1 ? models[0].model : conv.model })
  const msg = conv.messages[conv.messages.length - 1]
  sending.value = true
  atBottom.value = true
  scrollBottom(true)
  controller = new AbortController()
  try {
    await streamPost(`/api/conversations/${conv.id}/messages`, body, (ev) => {
      if (ev.start) {
        if (ev.replies.length > 1) msg.alternatives = ev.replies.map((r) => ({ id: r.id, model: r.model, content: '', reasoning: '', streaming: true }))
        else msg.id = ev.replies[0]?.id
        return
      }
      if (ev.status === 'searching') {
        msg.status = ev.kb && ev.web ? '正在检索知识库并联网搜索…' : ev.kb ? '正在检索知识库…' : '正在联网搜索…'
        return
      }
      if (ev.sources) {
        msg.status = ''
        msg.sources = ev.sources
        msg.notices = ev.notices
        return
      }
      const target = msg.alternatives ? msg.alternatives[ev.i] : msg
      if (!target) return
      if (ev.tool) {
        target.tools = [...(target.tools || []), { ...ev.tool, running: true }]
        return
      }
      if (ev.tool_done) {
        const t = (target.tools || []).find((x) => x.running && x.name === ev.tool_done.name)
        if (t) Object.assign(t, ev.tool_done, { running: false })
        if (ev.tool_done.sources?.length) target.sources = [...(target.sources || []), ...ev.tool_done.sources]
        scrollBottom()
        return
      }
      msg.status = ''
      if (ev.delta) target.content += ev.delta
      if (ev.reasoning) target.reasoning += ev.reasoning
      if (ev.failover) target.served_by = ev.failover
      if (ev.error) target.error = ev.error
      if (ev.done || ev.error) target.streaming = false
      scrollBottom()
    }, controller.signal)
  } catch (e) {
    if (e.name !== 'AbortError') msg.error = e.message
  } finally {
    msg.streaming = false
    sending.value = false
    controller = null
    const err = msg.error
    const fresh = await refresh().catch(() => null)
    if (fresh) {
      // 请求本身失败（未进入流式）时，在末尾提示错误
      if (err && current.value?.id === conv.id) {
        const last = fresh.messages[fresh.messages.length - 1]
        if (last?.role === 'assistant' && !last.error) last.error = err
        else if (last?.role !== 'assistant') fresh.messages.push({ role: 'assistant', content: '', error: err })
      }
      const item = convs.value.find((c) => c.id === conv.id)
      if (item) item.title = fresh.title
      convs.value.sort((a, b) => (b.pinned - a.pinned) || (a.id === conv.id ? -1 : b.id === conv.id ? 1 : 0))
    }
    scrollBottom()
  }
}

async function send() {
  const text = input.value.trim()
  if ((!text && !pending.value.length && !pendingFiles.value.length) || sending.value) return
  if (!current.value.model && compareKeys.value.length < 1) return toast('请先在右上角选择模型', 'warning')
  const attachments = pending.value
  const files = pendingFiles.value
  input.value = ''
  pending.value = []
  pendingFiles.value = []
  current.value.messages.push({ role: 'user', content: text, attachments, files: files.map((f) => ({ name: f.name, chars: f.chars })) })
  await stream({ content: text, attachments: attachments.map((a) => a.id), files: files.map((f) => ({ name: f.name, text: f.text })) })
}

async function regenerate(m) {
  // 为该回答对应的问题生成一个新的回答分支，原回答保留
  const msgs = current.value.messages
  const idx = msgs.findIndex((x) => x.id === m.id)
  if (idx < 0) return
  msgs.splice(idx)
  await stream({ regenerate: true, parent_id: m.parent_id })
}

function stop() {
  controller?.abort()
}

async function copy(text) {
  if (await copyText(text)) toast('已复制', 'success')
}

function preview(list, a) {
  viewerItems.value = list
  viewerIndex.value = list.findIndex((x) => x.id === a.id)
}

watch(() => route.params.id, (id) => {
  if (route.path.startsWith('/chat') && id && Number(id) !== current.value?.id) open(id)
})

// keep-alive 时再次从工作台带着问题进入
watch(() => route.query.q, async (q) => {
  if (!q || !route.path.startsWith('/chat')) return
  await newConv()
  input.value = String(q)
  await send()
})

onMounted(async () => {
  await loadProviders()
  loadSettings().then((s) => { settings.value = s || {} }).catch(() => null)
  await loadConvs()
  if (route.query.q) {
    // 来自工作台的快捷提问：新建对话并直接发送
    const q = String(route.query.q)
    await newConv()
    input.value = q
    await send()
  } else if (route.params.id) await open(route.params.id)
  else if (convs.value.length) await open(convs.value[0].id)
})

</script>

<style scoped>
.chat { display: flex; height: 100%; min-height: 0; position: relative; }
.convs { width: 272px; flex-shrink: 0; display: flex; flex-direction: column; border-right: 1px solid var(--border); background: var(--panel); }
.convs-head { display: flex; gap: 8px; padding: 14px 12px 10px; }
.new-btn { flex: 1; }
.search { margin: 0 12px 8px; width: auto; }
.list { flex: 1; overflow: auto; padding: 0 8px 12px; }
.group { font-size: 11.5px; color: var(--muted); padding: 12px 8px 4px; font-weight: 600; }
.conv { display: flex; align-items: center; gap: 8px; padding: 8px 6px 8px 10px; border-radius: 8px; cursor: pointer; font-size: 13.5px; }
.conv:hover { background: var(--panel-2); }
.conv.active { background: color-mix(in srgb, var(--primary) 12%, transparent); color: var(--primary); font-weight: 500; }
.conv-icon { font-size: 15px; width: 20px; text-align: center; flex-shrink: 0; }
.conv-title { flex: 1; min-width: 0; }
.conv-more { opacity: 0; border: none; background: none; color: var(--muted); cursor: pointer; padding: 2px 4px; border-radius: 4px; display: grid; place-items: center; }
.conv:hover .conv-more, .conv.active .conv-more { opacity: 1; }
.conv-more:hover { background: var(--panel-3); color: var(--text); }

.body { flex: 1; min-width: 0; display: flex; flex-direction: column; position: relative; }
.chat-head { height: 56px; flex-shrink: 0; display: flex; align-items: center; gap: 8px; padding: 0 16px; border-bottom: 1px solid var(--border); }
.list-toggle { display: none; }
.head-icon { font-size: 20px; }
.head-title { font-weight: 600; font-size: 15px; cursor: pointer; min-width: 0; }
.model-select { width: 240px; }

.messages { flex: 1; overflow: auto; padding: 24px 20px 12px; }
.welcome { max-width: 720px; margin: 8vh auto 0; text-align: center; }
.welcome-icon { font-size: 44px; margin-bottom: 8px; }
.welcome h2 { margin: 0 0 8px; font-size: 22px; }
.role-desc { font-size: 13px; line-height: 1.6; max-width: 560px; margin: 0 auto; }
.suggestions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 28px; }
.suggestion { text-align: left; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--border); background: var(--panel); color: var(--text-2); cursor: pointer; font-size: 13.5px; line-height: 1.5; transition: all .15s; }
.suggestion:hover { border-color: var(--primary); color: var(--text); transform: translateY(-1px); }

.msg { display: flex; gap: 12px; max-width: 860px; margin: 0 auto 22px; }
.msg.user { flex-direction: row-reverse; }
.avatar { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; flex-shrink: 0; font-size: 17px; background: var(--panel-2); border: 1px solid var(--border); }
.avatar.user { background: linear-gradient(135deg, var(--primary), color-mix(in srgb, var(--primary) 55%, #ff7ac6)); color: #fff; font-size: 14px; font-weight: 700; border: none; }
.msg-main { min-width: 0; max-width: calc(100% - 46px); display: flex; flex-direction: column; }
.msg.user .msg-main { align-items: flex-end; }
.msg-meta { font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.bubble { padding: 10px 14px; border-radius: 14px; max-width: 100%; }
.bubble.assistant { background: var(--panel); border: 1px solid var(--border); border-top-left-radius: 4px; }
.bubble.user { background: color-mix(in srgb, var(--primary) 12%, var(--panel)); border-top-right-radius: 4px; }
.plain { white-space: pre-wrap; word-break: break-word; line-height: 1.7; font-size: 14.5px; }
.attachments { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
.attachments img { width: 120px; height: 120px; object-fit: cover; border-radius: 10px; cursor: zoom-in; border: 1px solid var(--border); }
.reasoning { margin-bottom: 8px; border-radius: 10px; background: var(--panel-2); max-width: 100%; }
.reasoning-head { display: flex; align-items: center; gap: 6px; border: none; background: none; color: var(--muted); font-size: 12.5px; cursor: pointer; padding: 7px 12px; }
.reasoning .chev { transition: transform .2s; }
.reasoning.open .chev { transform: rotate(180deg); }
.reasoning-body { display: none; padding: 0 14px 10px; font-size: 13px; color: var(--text-2); white-space: pre-wrap; line-height: 1.65; max-height: 320px; overflow: auto; border-left: 2px solid var(--border); margin: 0 12px 4px; }
.reasoning.open .reasoning-body { display: block; }
.typing { display: flex; gap: 4px; padding: 14px 16px; background: var(--panel); border: 1px solid var(--border); border-radius: 14px; border-top-left-radius: 4px; width: fit-content; }
.typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); animation: bounce 1.2s infinite; }
.typing span:nth-child(2) { animation-delay: .15s; } .typing span:nth-child(3) { animation-delay: .3s; }
@keyframes bounce { 0%, 60%, 100% { transform: translateY(0); opacity: .5; } 30% { transform: translateY(-4px); opacity: 1; } }
.msg-error { margin-top: 6px; display: flex; gap: 6px; color: var(--danger); font-size: 13px; background: color-mix(in srgb, var(--danger) 8%, transparent); padding: 8px 10px; border-radius: 8px; word-break: break-word; }
.ops { display: flex; gap: 2px; margin-top: 4px; opacity: 0; transition: opacity .15s; }
.msg:hover .ops { opacity: 1; }
.edit-box { width: min(640px, 100%); }
.served { color: var(--warning); }
.file-chips { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; justify-content: flex-end; }
.file-chip { display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px; padding: 5px 10px; border-radius: 10px; background: var(--panel); border: 1px solid var(--border); }
.file-chip .muted { font-size: 11.5px; }
.status-line { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--muted); margin-bottom: 6px; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.tool-call { margin-bottom: 8px; border-radius: 10px; background: var(--panel-2); max-width: 100%; }
.tool-head { display: flex; align-items: center; gap: 6px; border: none; background: none; color: var(--text-2); font-size: 12.5px; cursor: pointer; padding: 7px 12px; }
.tool-call .chev { transition: transform .2s; }
.tool-call.open .chev { transform: rotate(180deg); }
.tool-body { display: none; padding: 0 12px 10px; }
.tool-call.open .tool-body { display: block; }
.tool-label { font-size: 11.5px; color: var(--muted); margin: 4px 0 2px; }
.tool-body pre { margin: 0; font-size: 12px; white-space: pre-wrap; word-break: break-word; max-height: 220px; overflow: auto; background: var(--panel); padding: 8px; border-radius: 6px; }
.tool-assets { display: flex; gap: 8px; flex-wrap: wrap; padding: 0 12px 10px; }
.tool-assets img { width: 220px; max-width: 100%; border-radius: 10px; cursor: zoom-in; border: 1px solid var(--border); }
.notice { margin-top: 6px; display: flex; gap: 6px; align-items: center; font-size: 12.5px; color: var(--warning); }
.sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 8px; }
.src-title { font-size: 12px; }
.src { display: inline-flex; align-items: center; gap: 4px; max-width: 240px; font-size: 12px; padding: 3px 8px; border-radius: 8px; background: var(--panel-2); color: var(--text-2); text-decoration: none; }
a.src:hover { color: var(--primary); }
.src b { font-size: 11px; color: var(--primary); }
.pending-file { position: relative; display: flex; align-items: center; gap: 8px; height: 56px; padding: 0 12px; border-radius: 8px; background: var(--panel-2); max-width: 220px; font-size: 12.5px; }
.pending-file .pf-text { min-width: 0; }
.pending-file .muted { font-size: 11.5px; }
.pending-file button { position: absolute; top: -5px; right: -5px; width: 18px; height: 18px; border-radius: 50%; border: none; background: var(--text); color: var(--panel); display: grid; place-items: center; cursor: pointer; padding: 0; }
.tool-btn { font-size: 12.5px; padding: 0 6px; }
.pick-pop { max-width: 360px; padding: 4px 2px; }
.pick-row { padding: 4px 0; }
.tools-pop { width: 360px; max-height: 360px; overflow: auto; }
.tool-row { border-bottom: 1px solid var(--border); padding: 6px 0; }
.tool-name { font-weight: 500; margin-right: 6px; }
.tool-desc { font-size: 12px; padding-left: 24px; line-height: 1.5; }
.branch-nav { display: inline-flex; align-items: center; gap: 2px; font-size: 12px; color: var(--muted); margin-right: 4px; font-variant-numeric: tabular-nums; }
.branch-nav button { border: none; background: none; color: var(--muted); cursor: pointer; padding: 2px; border-radius: 4px; display: grid; place-items: center; }
.branch-nav button:hover:not(:disabled) { background: var(--panel-2); color: var(--text); }
.branch-nav button:disabled { opacity: .35; cursor: default; }
.msg.assistant:has(.compare) { max-width: min(1400px, 100%); }
.msg-main:has(.compare) { flex: 1; }
.compare { display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); gap: 10px; width: 100%; }
.compare-col { min-width: 0; border: 1px solid var(--border); background: var(--panel); border-radius: 12px; padding: 8px 12px 10px; display: flex; flex-direction: column; gap: 6px; }
.compare-col.chosen { border-color: color-mix(in srgb, var(--primary) 60%, var(--border)); box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary) 25%, transparent); }
.compare-head { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); font-weight: 600; min-width: 0; }
.compare-think { font-size: 12.5px; }
.compare-col .typing { border: none; padding: 8px 0; }
.compare-btn { font-size: 12.5px; }
.compare-pop { padding: 4px 2px; }
.edit-actions { justify-content: flex-end; margin-top: 8px; }

.to-bottom { position: absolute; right: 28px; bottom: 140px; width: 34px; height: 34px; border-radius: 50%; border: 1px solid var(--border); background: var(--panel); color: var(--text-2); display: grid; place-items: center; cursor: pointer; box-shadow: var(--shadow); }
.composer-wrap { padding: 8px 20px 18px; }
.composer { max-width: 860px; margin: 0 auto; border: 1px solid var(--border); border-radius: 16px; background: var(--panel); box-shadow: var(--shadow); padding: 8px 10px 8px; transition: border-color .15s; }
.composer:focus-within, .composer.dragging { border-color: var(--primary); }
.composer :deep(.n-input) { background: transparent; }
.composer :deep(.n-input__textarea-el) { font-size: 14.5px; }
.composer-bar { display: flex; align-items: center; gap: 6px; padding-top: 4px; }
.model-label { font-size: 12px; min-width: 0; }
.pending { display: flex; gap: 6px; padding: 4px 4px 8px; flex-wrap: wrap; }
.pending-item { position: relative; width: 56px; height: 56px; }
.pending-item img { width: 100%; height: 100%; object-fit: cover; border-radius: 8px; }
.pending-item button { position: absolute; top: -5px; right: -5px; width: 18px; height: 18px; border-radius: 50%; border: none; background: var(--text); color: var(--panel); display: grid; place-items: center; cursor: pointer; padding: 0; }
.param { margin-bottom: 16px; }
.hint { font-size: 12px; color: var(--muted); }
.list-mask { display: none; }

@media (max-width: 860px) {
  .convs { position: absolute; z-index: 20; top: 0; bottom: 0; left: 0; transform: translateX(-100%); transition: transform .2s; box-shadow: var(--shadow); }
  .convs.open { transform: none; }
  .list-mask { display: block; position: absolute; inset: 0; z-index: 15; background: rgba(0, 0, 0, .3); }
  .list-toggle { display: inline-flex; }
  .model-select { width: 150px; }
  .suggestions { grid-template-columns: 1fr; }
  .messages { padding: 16px 12px 8px; }
  .composer-wrap { padding: 6px 10px 12px; }
  .ops { opacity: 1; }
  .compare { grid-template-columns: 1fr; }
  .btn-text { display: none; }
}
</style>
