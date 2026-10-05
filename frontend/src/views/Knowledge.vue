<template>
  <div class="page kb-page">
    <div class="page-head">
      <div>
        <h1>知识库</h1>
        <div class="sub">上传文档建立知识库，在对话中勾选后，模型会检索相关内容并标注来源回答</div>
      </div>
      <span class="spacer" />
      <n-button type="primary" @click="editKb()"><template #icon><Plus :size="16" /></template>新建知识库</n-button>
    </div>

    <div v-if="kbs.length" class="layout">
      <aside class="kb-list">
        <button v-for="k in kbs" :key="k.id" class="kb-item" :class="{ active: current?.id === k.id }" @click="select(k)">
          <LibraryBig :size="18" class="kb-icon" />
          <div class="kb-text">
            <div class="ellipsis kb-name">{{ k.name }}</div>
            <div class="muted small">{{ k.documents }} 个文档 · {{ k.embedding_model ? '向量检索' : '关键词检索' }}</div>
          </div>
        </button>
      </aside>

      <section v-if="current" class="detail">
        <div class="detail-head">
          <div class="dh-text">
            <h2 class="ellipsis">{{ current.name }}</h2>
            <div class="muted small">
              {{ current.embedding_label ? `向量模型：${current.embedding_label}` : '关键词检索（未使用向量模型）' }}
              <template v-if="current.description"> · {{ current.description }}</template>
            </div>
          </div>
          <n-button secondary size="small" @click="editKb(current)"><template #icon><Pencil :size="14" /></template>编辑</n-button>
          <n-button secondary size="small" type="error" @click="removeKb(current)"><template #icon><Trash2 :size="14" /></template></n-button>
        </div>

        <div class="drop" :class="{ dragging }" @click="fileInput?.click()" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
          <UploadCloud :size="28" />
          <div>点击或拖拽文档到这里上传</div>
          <div class="muted small">支持 PDF、Word（docx）、PPT（pptx）、Excel（xlsx）、Markdown、TXT、HTML、EPUB、代码文件等，单个不超过 50MB</div>
          <input ref="fileInput" type="file" multiple hidden :accept="ACCEPT" @change="(e) => { upload(e.target.files); e.target.value = '' }" />
        </div>

        <n-data-table :columns="docCols" :data="docs" :bordered="false" size="small" class="table" :row-key="(r) => r.id" />

        <div class="search-box">
          <div class="field-label">检索测试</div>
          <n-input-group>
            <n-input v-model:value="query" placeholder="输入问题，查看会检索到哪些片段" @keydown.enter="search" />
            <n-button type="primary" :loading="searching" :disabled="!query.trim()" @click="search">检索</n-button>
          </n-input-group>
          <div v-for="(h, i) in hits" :key="i" class="hit">
            <div class="hit-head"><b>[{{ i + 1 }}] {{ h.filename }}</b><span class="muted">相关度 {{ (h.score * 100).toFixed(0) }}%</span></div>
            <div class="hit-text">{{ h.text }}</div>
          </div>
          <div v-if="searched && !hits.length" class="muted small" style="margin-top: 10px">没有找到相关内容</div>
        </div>
      </section>
    </div>

    <EmptyState v-else-if="loaded" :icon="LibraryBig" title="还没有知识库" desc="把产品手册、品牌资料、剧本设定等文档放进知识库，对话时模型就能引用其中的内容。">
      <n-button type="primary" @click="editKb()">新建知识库</n-button>
    </EmptyState>

    <n-modal v-model:show="showEdit" preset="card" :title="form.id ? '编辑知识库' : '新建知识库'" style="width: min(520px, 94vw)">
      <n-form label-placement="top">
        <n-form-item label="名称"><n-input v-model:value="form.name" maxlength="64" placeholder="例如：品牌资料" /></n-form-item>
        <n-form-item label="说明"><n-input v-model:value="form.description" placeholder="可选" /></n-form-item>
        <n-form-item label="向量模型">
          <div style="width: 100%">
            <ModelSelect v-model="form.embeddingKey" kind="embedding" placeholder="不使用（关键词检索）" :disabled="!!(form.id && current?.documents)" />
            <div class="muted small" style="margin-top: 6px">
              向量检索能理解语义（如「怎么上线」能匹配「部署方式」），需在模型服务中配置向量模型（如 text-embedding-3-small、BAAI/bge-m3）；不选择时使用关键词检索，无需任何模型。{{ form.id && current?.documents ? '已有文档的知识库不能更换向量模型。' : '' }}
            </div>
          </div>
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="row"><span class="spacer" /><n-button @click="showEdit = false">取消</n-button><n-button type="primary" :disabled="!form.name.trim()" @click="saveKb">保存</n-button></div>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { h, onMounted, onUnmounted, reactive, ref } from 'vue'
import { NButton, NDataTable, NForm, NFormItem, NInput, NInputGroup, NModal, NTag } from 'naive-ui'
import { LibraryBig, Pencil, Plus, Trash2, UploadCloud } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import ModelSelect from '../components/ModelSelect.vue'
import { api, confirmDialog, toast } from '../api'
import { loadProviders, splitModelKey } from '../store'
import { formatBytes, relativeTime } from '../utils/format'

const ACCEPT = '.pdf,.docx,.pptx,.xlsx,.md,.markdown,.txt,.csv,.json,.html,.htm,.epub,.srt,.vtt,.log,.py,.js,.ts,.java,.go,.sql,.yaml,.yml,.xml'
const STATUS = { pending: ['排队中', 'default'], processing: ['处理中', 'info'], ready: ['已就绪', 'success'], failed: ['失败', 'error'] }

const kbs = ref([])
const current = ref(null)
const docs = ref([])
const loaded = ref(false)
const showEdit = ref(false)
const form = reactive({ id: null, name: '', description: '', embeddingKey: '' })
const fileInput = ref(null)
const dragging = ref(false)
const query = ref('')
const hits = ref([])
const searching = ref(false)
const searched = ref(false)
let timer = null

const docCols = [
  { title: '文档', key: 'filename', ellipsis: { tooltip: true } },
  { title: '大小', key: 'size', width: 90, render: (d) => formatBytes(d.size) },
  { title: '片段', key: 'chunk_count', width: 70, render: (d) => (d.status === 'ready' ? d.chunk_count : '—') },
  {
    title: '状态', key: 'status', width: 110,
    render: (d) => h(NTag, { size: 'small', bordered: false, type: STATUS[d.status][1], title: d.error || '' }, () => STATUS[d.status][0]),
  },
  { title: '上传时间', key: 'created_at', width: 110, render: (d) => relativeTime(d.created_at) },
  {
    title: '', key: 'ops', width: 50,
    render: (d) => h(NButton, { size: 'tiny', quaternary: true, type: 'error', onClick: () => removeDoc(d) }, { icon: () => h(Trash2, { size: 14 }) }),
  },
]

async function loadKbs() {
  kbs.value = await api.get('/api/kb')
  loaded.value = true
  if (current.value) current.value = kbs.value.find((k) => k.id === current.value.id) || null
  if (!current.value && kbs.value.length) select(kbs.value[0])
}

async function select(k) {
  current.value = k
  hits.value = []
  searched.value = false
  await loadDocs()
}

async function loadDocs() {
  if (!current.value) return
  const kid = current.value.id
  const list = await api.get(`/api/kb/${kid}/documents`)
  if (current.value?.id !== kid) return
  docs.value = list
  clearTimeout(timer)
  // 有文档在处理时轮询状态
  if (list.some((d) => d.status === 'pending' || d.status === 'processing')) timer = setTimeout(loadDocs, 1500)
  else {
    const k = kbs.value.find((x) => x.id === kid)
    if (k && k.documents !== list.length) loadKbs()
  }
}

function editKb(k) {
  Object.assign(form, k
    ? { id: k.id, name: k.name, description: k.description, embeddingKey: k.embedding_provider_id ? `${k.embedding_provider_id}::${k.embedding_model}` : '' }
    : { id: null, name: '', description: '', embeddingKey: '' })
  showEdit.value = true
}

async function saveKb() {
  const [pid, model] = splitModelKey(form.embeddingKey)
  const body = { name: form.name.trim(), description: form.description, embedding_provider_id: pid, embedding_model: model }
  const k = form.id ? await api.patch(`/api/kb/${form.id}`, body) : await api.post('/api/kb', body)
  showEdit.value = false
  await loadKbs()
  select(kbs.value.find((x) => x.id === k.id))
}

async function removeKb(k) {
  if (!(await confirmDialog({ title: '删除知识库', content: `将删除「${k.name}」及其中的 ${k.documents} 个文档，使用它的对话将不再检索。`, positiveText: '删除' }))) return
  await api.del(`/api/kb/${k.id}`)
  current.value = null
  docs.value = []
  loadKbs()
}

async function upload(files) {
  const list = [...files]
  if (!list.length || !current.value) return
  for (const f of list) {
    const fd = new FormData()
    fd.append('file', f)
    try {
      await api.post(`/api/kb/${current.value.id}/documents`, fd)
    } catch {
      /* 已提示 */
    }
  }
  toast(`已上传 ${list.length} 个文档，正在处理`, 'success')
  loadDocs()
}

function onDrop(e) {
  dragging.value = false
  upload(e.dataTransfer.files)
}

async function removeDoc(d) {
  if (!(await confirmDialog({ title: '删除文档', content: `确定删除「${d.filename}」？`, positiveText: '删除' }))) return
  await api.del(`/api/kb/${d.kb_id}/documents/${d.id}`)
  await loadDocs()
  loadKbs()
}

async function search() {
  if (!query.value.trim()) return
  searching.value = true
  try {
    hits.value = await api.post(`/api/kb/${current.value.id}/search`, { query: query.value.trim() })
    searched.value = true
  } finally {
    searching.value = false
  }
}

onMounted(async () => {
  await loadProviders()
  loadKbs()
})
onUnmounted(() => clearTimeout(timer))
</script>

<style scoped>
.layout { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 18px; align-items: start; }
.kb-list { display: flex; flex-direction: column; gap: 6px; }
.kb-item { display: flex; gap: 10px; align-items: center; text-align: left; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--border); background: var(--panel); color: var(--text); cursor: pointer; }
.kb-item:hover { border-color: color-mix(in srgb, var(--primary) 50%, var(--border)); }
.kb-item.active { border-color: var(--primary); background: color-mix(in srgb, var(--primary) 8%, var(--panel)); }
.kb-icon { color: var(--primary); flex-shrink: 0; }
.kb-text { min-width: 0; }
.kb-name { font-weight: 600; font-size: 14px; }
.small { font-size: 12px; }
.detail { padding: 18px; border-radius: 14px; background: var(--panel); border: 1px solid var(--border); display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.detail-head { display: flex; align-items: center; gap: 8px; }
.dh-text { flex: 1; min-width: 0; }
.dh-text h2 { margin: 0 0 2px; font-size: 18px; }
.drop { border: 1.5px dashed var(--border); border-radius: 12px; padding: 22px; display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center; color: var(--text-2); cursor: pointer; transition: all .15s; }
.drop:hover, .drop.dragging { border-color: var(--primary); color: var(--primary); background: color-mix(in srgb, var(--primary) 5%, transparent); }
.table { border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.hit { margin-top: 10px; padding: 10px 12px; border-radius: 10px; background: var(--panel-2); }
.hit-head { display: flex; justify-content: space-between; font-size: 12.5px; margin-bottom: 4px; }
.hit-text { font-size: 13px; color: var(--text-2); white-space: pre-wrap; line-height: 1.6; max-height: 160px; overflow: auto; }
@media (max-width: 860px) { .layout { grid-template-columns: 1fr; } }
</style>
