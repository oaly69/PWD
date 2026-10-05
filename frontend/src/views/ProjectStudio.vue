<template>
  <div v-if="p" class="page studio-page">
    <div class="head">
      <n-button quaternary circle @click="$router.push('/projects')"><template #icon><ArrowLeft :size="18" /></template></n-button>
      <n-input v-model:value="p.name" class="name-input" :bordered="false" maxlength="128" @blur="save({ name: p.name })" />
      <n-tag size="small" :bordered="false">{{ p.aspect }}</n-tag>
      <span class="spacer" />
      <n-button secondary size="small" @click="downloadUrl(`/api/projects/${p.id}/export.md`)"><template #icon><FileDown :size="14" /></template>导出分镜</n-button>
      <n-button secondary size="small" @click="settingsOpen = true"><template #icon><SlidersHorizontal :size="14" /></template>项目设置</n-button>
      <n-button quaternary size="small" type="error" @click="remove"><template #icon><Trash2 :size="14" /></template></n-button>
    </div>

    <div class="stepper">
      <button v-for="(s, i) in STEPS" :key="s.key" class="st" :class="{ active: tab === s.key, done: stepDone(s.key) }" @click="tab = s.key">
        <span class="st-no"><Check v-if="stepDone(s.key)" :size="12" /><template v-else>{{ i + 1 }}</template></span>
        {{ s.label }}<span v-if="s.count" class="muted st-count">{{ s.count(p) }}</span>
      </button>
    </div>

    <!-- ① 剧本 -->
    <section v-show="tab === 'script'" class="panel">
      <div class="two-col">
        <div>
          <div class="field-label">故事梗概 / 创意</div>
          <n-input v-model:value="p.synopsis" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" placeholder="一句话或一段话描述你的故事" @blur="save({ synopsis: p.synopsis })" />
          <div class="row" style="margin-top: 10px">
            <span class="muted small">目标时长</span>
            <n-select v-model:value="minutes" :options="MINUTES" size="small" style="width: 110px" />
            <n-button type="primary" :loading="busy.script" :disabled="!p.synopsis.trim()" @click="aiScript"><template #icon><Sparkles :size="15" /></template>AI 写剧本</n-button>
          </div>
          <div class="field-label" style="margin-top: 18px">视觉风格</div>
          <n-input v-model:value="p.style" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="例如：电影感，35mm 胶片，暖色调，浅景深" @blur="save({ style: p.style })" />
          <div class="muted small" style="margin-top: 4px">会追加到每个镜头和角色参考图的提示词中，统一整部短片的画面风格</div>
        </div>
        <div>
          <div class="field-label">剧本</div>
          <n-input v-model:value="p.script" type="textarea" class="script" :autosize="{ minRows: 16, maxRows: 30 }" placeholder="可以直接粘贴已有剧本，或用左侧「AI 写剧本」生成" @blur="save({ script: p.script })" />
          <div class="row" style="margin-top: 10px">
            <span class="spacer" />
            <n-button secondary :disabled="!p.script.trim()" @click="tab = 'elements'">下一步：角色与场景 →</n-button>
          </div>
        </div>
      </div>
    </section>

    <!-- ② 角色与场景 -->
    <section v-show="tab === 'elements'" class="panel">
      <div class="toolbar">
        <div class="muted small">为主要角色和场景生成或选择参考图；镜头中出现时会自动带上外观描述{{ p.settings.use_refs ? '和参考图' : '' }}，保持前后一致。</div>
        <span class="spacer" />
        <n-button secondary :loading="busy.elements" :disabled="!p.script.trim()" @click="aiElements"><template #icon><Sparkles :size="15" /></template>从剧本提取</n-button>
        <n-button type="primary" @click="editElement()"><template #icon><Plus :size="15" /></template>添加</n-button>
      </div>
      <div class="el-grid">
        <div v-for="e in p.elements" :key="e.id" class="el-card">
          <div class="el-img" @click="e.ref && preview([e.ref], e.ref)">
            <img v-if="e.ref" :src="e.ref.thumb_url" />
            <div v-else-if="running(e.task)" class="el-ph"><n-spin size="small" /><span>生成中…</span></div>
            <div v-else class="el-ph"><component :is="e.kind === 'character' ? UserRound : Mountain" :size="30" :stroke-width="1.4" /><span v-if="e.task?.status === 'failed'" class="err small">{{ e.task.error }}</span></div>
          </div>
          <div class="el-body">
            <div class="row"><n-tag size="small" :bordered="false" :type="e.kind === 'character' ? 'primary' : 'info'">{{ KIND[e.kind] }}</n-tag><b class="ellipsis">{{ e.name }}</b></div>
            <div class="muted small clamp">{{ e.prompt || e.description || '没有外观描述' }}</div>
            <div class="row el-actions">
              <n-button size="tiny" secondary :loading="running(e.task)" @click="genElement(e)"><template #icon><Wand2 :size="12" /></template>{{ e.ref ? '重新生成' : '生成参考图' }}</n-button>
              <n-button size="tiny" quaternary @click="pickFor = e"><template #icon><ImageIcon :size="12" /></template>选图</n-button>
              <span class="spacer" />
              <n-button size="tiny" quaternary @click="editElement(e)"><template #icon><Pencil :size="12" /></template></n-button>
              <n-button size="tiny" quaternary type="error" @click="removeElement(e)"><template #icon><Trash2 :size="12" /></template></n-button>
            </div>
          </div>
        </div>
      </div>
      <EmptyState v-if="!p.elements.length" compact :icon="Users" title="还没有角色或场景" desc="点击「从剧本提取」让 AI 自动整理" />
    </section>

    <!-- ③ 分镜 -->
    <section v-show="tab === 'shots'" class="panel">
      <div class="toolbar">
        <n-button secondary :loading="busy.storyboard" :disabled="!p.script.trim()" @click="aiStoryboard"><template #icon><Sparkles :size="15" /></template>AI 拆分镜</n-button>
        <n-button secondary @click="editShot()"><template #icon><Plus :size="15" /></template>添加镜头</n-button>
        <span class="spacer" />
        <span class="muted small">只补全缺失的：</span>
        <n-button size="small" type="primary" secondary :disabled="!p.shots.length" @click="batch('keyframe')"><template #icon><ImageIcon :size="14" /></template>关键帧 {{ countOf('keyframe') }}/{{ p.shots.length }}</n-button>
        <n-button size="small" type="primary" secondary :disabled="!p.shots.length" @click="batch('video')"><template #icon><Film :size="14" /></template>视频 {{ countOf('video') }}/{{ p.shots.length }}</n-button>
        <n-button size="small" type="primary" secondary :disabled="!dialogueCount" @click="batch('audio')"><template #icon><AudioLines :size="14" /></template>配音 {{ countOf('audio') }}/{{ dialogueCount }}</n-button>
      </div>

      <div class="shots">
        <div v-for="(s, i) in p.shots" :key="s.id" class="shot">
          <div class="shot-no">{{ i + 1 }}</div>
          <div class="media-col" :class="`a${p.aspect.replace(':', '-')}`">
            <div class="media-box" @click="s.keyframe && preview([s.keyframe], s.keyframe)">
              <img v-if="s.keyframe" :src="s.keyframe.thumb_url" />
              <div v-if="running(s.tasks.keyframe)" class="media-ph overlay"><n-spin size="small" /></div>
              <div v-else-if="!s.keyframe" class="media-ph"><ImageIcon :size="22" :stroke-width="1.4" /><span>关键帧</span></div>
            </div>
            <div class="media-box" @click="s.video && preview([s.video], s.video)">
              <video v-if="s.video" :src="s.video.url + '#t=0.1'" muted preload="metadata" />
              <span v-if="s.video" class="play"><Play :size="16" fill="currentColor" /></span>
              <div v-if="running(s.tasks.video)" class="media-ph overlay"><n-spin size="small" /><span v-if="s.tasks.video.progress">{{ s.tasks.video.progress }}%</span></div>
              <div v-else-if="!s.video" class="media-ph"><Film :size="22" :stroke-width="1.4" /><span>视频</span></div>
            </div>
          </div>
          <div class="shot-body">
            <div class="row shot-title">
              <b class="ellipsis">{{ s.title || `镜头 ${i + 1}` }}</b>
              <n-tag size="tiny" :bordered="false">{{ s.duration }} 秒</n-tag>
              <span v-if="s.camera" class="muted small ellipsis">{{ s.camera }}</span>
            </div>
            <div class="small clamp">{{ s.description }}</div>
            <div v-if="s.dialogue" class="dialogue small"><MessageSquareQuote :size="13" />{{ s.dialogue }}</div>
            <div v-if="s.element_ids.length" class="chips">
              <span v-for="eid in s.element_ids" :key="eid" class="chip">{{ elementName(eid) }}</span>
            </div>
            <audio v-if="s.audio" :src="s.audio.url" controls class="audio" />
            <div v-for="(t, k) in s.tasks" v-show="t.status === 'failed'" :key="k" class="err small">{{ SLOT[k] }}生成失败：{{ t.error }}</div>
          </div>
          <div class="shot-ops">
            <n-dropdown trigger="click" :options="shotMenu(s, i)" @select="(k) => onShotMenu(k, s, i)">
              <n-button size="small" quaternary><template #icon><Ellipsis :size="16" /></template></n-button>
            </n-dropdown>
            <n-button size="tiny" secondary :loading="running(s.tasks.keyframe)" @click="genShot(s, 'keyframe')">画面</n-button>
            <n-button size="tiny" secondary :loading="running(s.tasks.video)" @click="genShot(s, 'video')">视频</n-button>
            <n-button size="tiny" secondary :disabled="!s.dialogue" :loading="running(s.tasks.audio)" @click="genShot(s, 'audio')">配音</n-button>
          </div>
        </div>
      </div>
      <EmptyState v-if="!p.shots.length" compact :icon="LayoutList" title="还没有镜头" desc="点击「AI 拆分镜」根据剧本自动生成分镜表" />
    </section>

    <!-- ④ 成片 -->
    <section v-show="tab === 'render'" class="panel">
      <div class="timeline">
        <div v-for="(s, i) in p.shots" :key="s.id" class="tl-item" :style="{ flexGrow: s.duration }" :title="`${i + 1}. ${s.description}`">
          <img v-if="s.keyframe" :src="s.keyframe.thumb_url" />
          <span class="tl-no">{{ i + 1 }}</span>
          <span class="tl-icons"><Film v-if="s.video" :size="11" /><AudioLines v-if="s.audio" :size="11" /></span>
        </div>
      </div>
      <div class="muted small" style="margin: 6px 0 16px">预计时长约 {{ totalDuration.toFixed(1) }} 秒（有配音的镜头会按配音长度自动延长）</div>

      <div class="render-grid">
        <div class="checklist">
          <div class="ck" :class="{ ok: countOf('keyframe') + countOf('video') > 0 }"><ImageIcon :size="15" />画面：{{ visualCount }}/{{ p.shots.length }} 个镜头可用<span class="muted">（没有视频的镜头用关键帧做缓慢推镜）</span></div>
          <div class="ck" :class="{ ok: countOf('video') === p.shots.length && p.shots.length }"><Film :size="15" />视频片段：{{ countOf('video') }}/{{ p.shots.length }}</div>
          <div class="ck" :class="{ ok: countOf('audio') >= dialogueCount && dialogueCount }"><AudioLines :size="15" />配音：{{ countOf('audio') }}/{{ dialogueCount }}</div>
          <n-checkbox :checked="p.settings.subtitles !== false" @update:checked="(v) => save({ settings: { subtitles: v } })">嵌入字幕轨（台词 / 旁白）</n-checkbox>
          <n-button type="primary" size="large" block :loading="running(p.render_task)" :disabled="!visualCount" @click="render">
            <template #icon><Clapperboard :size="18" /></template>{{ p.output ? '重新合成' : '合成成片' }}
          </n-button>
          <n-progress v-if="running(p.render_task)" type="line" :percentage="p.render_task.progress" />
          <div v-if="p.render_task?.status === 'failed'" class="err small">合成失败：{{ p.render_task.error }}</div>
        </div>
        <div class="output">
          <video v-if="p.output" :key="p.output.id" :src="p.output.url" controls class="out-video" />
          <div v-else class="out-ph"><Clapperboard :size="40" :stroke-width="1.2" /><div class="muted">合成后在这里预览</div></div>
          <div v-if="p.output" class="row">
            <n-button secondary @click="downloadUrl(p.output.url, `${p.name}.mp4`)"><template #icon><Download :size="15" /></template>下载视频</n-button>
            <n-button secondary @click="downloadUrl(`/api/projects/${p.id}/subtitles.srt`)"><template #icon><Captions :size="15" /></template>下载字幕 SRT</n-button>
          </div>
        </div>
      </div>
    </section>

    <!-- 镜头编辑 -->
    <n-modal v-model:show="shotModal" preset="card" :title="shotForm.id ? '编辑镜头' : '添加镜头'" style="width: min(760px, 96vw)" :segmented="{ content: true }">
      <n-form label-placement="top">
        <div class="form-row">
          <n-form-item label="标题" style="flex: 2"><n-input v-model:value="shotForm.title" /></n-form-item>
          <n-form-item label="时长（秒）" style="flex: 1"><n-input-number v-model:value="shotForm.duration" :min="1" :max="60" :step="0.5" /></n-form-item>
        </div>
        <n-form-item label="画面内容"><n-input v-model:value="shotForm.description" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" /></n-form-item>
        <div class="form-row">
          <n-form-item label="景别 / 运镜" style="flex: 1"><n-input v-model:value="shotForm.camera" placeholder="例如：中景，缓慢推近" /></n-form-item>
          <n-form-item label="出场角色 / 场景" style="flex: 1">
            <n-select v-model:value="shotForm.element_ids" multiple :options="p.elements.map((e) => ({ label: e.name, value: e.id }))" placeholder="可选" />
          </n-form-item>
        </div>
        <n-form-item label="台词 / 旁白（用于配音和字幕）"><n-input v-model:value="shotForm.dialogue" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" placeholder="旁白：……" /></n-form-item>
        <n-form-item label="关键帧提示词（留空使用画面内容）"><n-input v-model:value="shotForm.image_prompt" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" /></n-form-item>
        <n-form-item label="视频动态描述（留空使用画面内容）"><n-input v-model:value="shotForm.video_prompt" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" /></n-form-item>
      </n-form>
      <template #footer>
        <div class="row"><span class="spacer" /><n-button @click="shotModal = false">取消</n-button><n-button type="primary" @click="saveShot">保存</n-button></div>
      </template>
    </n-modal>

    <!-- 角色 / 场景编辑 -->
    <n-modal v-model:show="elModal" preset="card" :title="elForm.id ? '编辑' : '添加角色 / 场景'" style="width: min(560px, 94vw)">
      <n-form label-placement="top">
        <div class="form-row">
          <n-form-item label="类型" style="flex: 1">
            <n-radio-group v-model:value="elForm.kind"><n-radio-button v-for="(v, k) in KIND" :key="k" :value="k">{{ v }}</n-radio-button></n-radio-group>
          </n-form-item>
          <n-form-item label="名称" style="flex: 1"><n-input v-model:value="elForm.name" maxlength="64" /></n-form-item>
        </div>
        <n-form-item label="说明"><n-input v-model:value="elForm.description" placeholder="身份、性格或场景说明" /></n-form-item>
        <n-form-item label="外观提示词"><n-input v-model:value="elForm.prompt" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="外貌、年龄、发型、服装 / 环境、光线、色调等具体描述" /></n-form-item>
      </n-form>
      <template #footer>
        <div class="row"><span class="spacer" /><n-button @click="elModal = false">取消</n-button><n-button type="primary" :disabled="!elForm.name.trim()" @click="saveElement">保存</n-button></div>
      </template>
    </n-modal>

    <!-- 项目设置 -->
    <n-drawer v-model:show="settingsOpen" :width="420" placement="right">
      <n-drawer-content title="项目设置" closable>
        <div v-for="k in MODEL_KINDS" :key="k.kind" class="set-row">
          <div class="field-label">{{ k.label }}</div>
          <ModelSelect :model-value="modelKey(k.kind)" :kind="k.kind" placeholder="使用系统默认" @update:model-value="(v) => setModel(k.kind, v)" />
        </div>
        <div class="form-row">
          <div class="set-row" style="flex: 1"><div class="field-label">关键帧尺寸</div><n-input :value="p.settings.image_size" placeholder="1536x1024" @change="(v) => save({ settings: { image_size: v } })" /></div>
          <div class="set-row" style="flex: 1"><div class="field-label">视频尺寸</div><n-input :value="p.settings.video_size" placeholder="1280x720" @change="(v) => save({ settings: { video_size: v } })" /></div>
        </div>
        <div class="set-row">
          <div class="field-label">配音音色</div>
          <n-select :value="p.settings.voice || null" :options="VOICES" filterable tag clearable placeholder="使用模型默认音色" @update:value="(v) => save({ settings: { voice: v || '' } })" />
        </div>
        <div class="set-row">
          <n-checkbox :checked="!!p.settings.use_refs" @update:checked="(v) => save({ settings: { use_refs: v } })">生成关键帧时附带角色参考图</n-checkbox>
          <div class="muted small" style="margin-top: 4px">提升角色一致性，需图像模型支持多图参考（如 gpt-image-1）；不支持的模型请关闭，仅使用外观描述</div>
        </div>
      </n-drawer-content>
    </n-drawer>

    <AssetPicker :show="!!pickFor" :max="1" @update:show="(v) => { if (!v) pickFor = null }" @select="onPick" />
    <MediaViewer v-model:index="viewerIndex" :items="viewerItems" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NCheckbox, NDrawer, NDrawerContent, NDropdown, NForm, NFormItem, NInput, NInputNumber, NModal, NProgress,
  NRadioButton, NRadioGroup, NSelect, NSpin, NTag,
} from 'naive-ui'
import {
  ArrowLeft, AudioLines, Captions, Check, Clapperboard, Download, Ellipsis, FileDown, Film, Image as ImageIcon, LayoutList,
  MessageSquareQuote, Mountain, Pencil, Play, Plus, SlidersHorizontal, Sparkles, Trash2, UserRound, Users, Wand2,
} from 'lucide-vue-next'
import AssetPicker from '../components/AssetPicker.vue'
import EmptyState from '../components/EmptyState.vue'
import MediaViewer from '../components/MediaViewer.vue'
import ModelSelect from '../components/ModelSelect.vue'
import { api, confirmDialog, toast } from '../api'
import { VOICES as VOICE_PRESETS } from '../constants'
import { loadProviders, splitModelKey } from '../store'
import { downloadUrl } from '../utils/format'

const STEPS = [
  { key: 'script', label: '剧本' },
  { key: 'elements', label: '角色与场景', count: (p) => p.elements.length },
  { key: 'shots', label: '分镜', count: (p) => p.shots.length },
  { key: 'render', label: '成片' },
]
const KIND = { character: '角色', scene: '场景', prop: '道具' }
const SLOT = { keyframe: '关键帧', video: '视频', audio: '配音' }
const MINUTES = [0.5, 1, 2, 3, 5].map((m) => ({ label: `${m} 分钟`, value: m }))
const MODEL_KINDS = [
  { kind: 'chat', label: '编剧 / 分镜（对话模型）' },
  { kind: 'image', label: '关键帧与参考图（图像模型）' },
  { kind: 'video', label: '镜头视频（视频模型）' },
  { kind: 'tts', label: '配音（语音模型）' },
]
const VOICES = VOICE_PRESETS

const route = useRoute()
const router = useRouter()
const p = ref(null)
const tab = ref('script')
const minutes = ref(1)
const busy = reactive({ script: false, elements: false, storyboard: false })
const settingsOpen = ref(false)
const shotModal = ref(false)
const shotForm = reactive({})
const elModal = ref(false)
const elForm = reactive({})
const pickFor = ref(null)
const viewerItems = ref([])
const viewerIndex = ref(-1)
let timer = null

const running = (t) => !!t && (t.status === 'pending' || t.status === 'running')
const countOf = (slot) => p.value.shots.filter((s) => s[slot]).length
const dialogueCount = computed(() => p.value?.shots.filter((s) => s.dialogue?.trim()).length || 0)
const visualCount = computed(() => p.value?.shots.filter((s) => s.keyframe || s.video).length || 0)
const totalDuration = computed(() => (p.value?.shots || []).reduce((a, s) => a + Number(s.duration || 0), 0))
const elementName = (id) => p.value.elements.find((e) => e.id === id)?.name || '?'
const anyRunning = computed(() => {
  const x = p.value
  if (!x) return false
  return running(x.render_task) || x.elements.some((e) => running(e.task)) || x.shots.some((s) => Object.values(s.tasks).some(running))
})

function stepDone(key) {
  const x = p.value
  if (key === 'script') return !!x.script.trim()
  if (key === 'elements') return x.elements.length > 0
  if (key === 'shots') return x.shots.length > 0 && x.shots.every((s) => s.keyframe || s.video)
  return !!x.output
}

function setProject(data) {
  p.value = data
}

async function load() {
  setProject(await api.get(`/api/projects/${route.params.id}`))
}

async function save(body) {
  setProject(await api.patch(`/api/projects/${p.value.id}`, body))
}

function modelKey(kind) {
  const st = p.value.settings
  return st[`${kind}_provider_id`] && st[`${kind}_model`] ? `${st[`${kind}_provider_id`]}::${st[`${kind}_model`]}` : ''
}

function setModel(kind, key) {
  const [pid, model] = splitModelKey(key)
  save({ settings: { [`${kind}_provider_id`]: pid, [`${kind}_model`]: model } })
}

async function remove() {
  if (!(await confirmDialog({ title: '删除项目', content: `确定删除「${p.value.name}」？已生成的图片、视频与成片会保留在作品库的项目作品集中。`, positiveText: '删除' }))) return
  await api.del(`/api/projects/${p.value.id}`)
  router.push('/projects')
}

// ---------------------------------------------------------------- AI 步骤

async function aiScript() {
  if (p.value.script.trim() && !(await confirmDialog({ title: '重新生成剧本', content: '将覆盖当前剧本，确定继续？', positiveText: '生成' }))) return
  busy.script = true
  try {
    const r = await api.post(`/api/projects/${p.value.id}/ai/script`, { synopsis: p.value.synopsis, minutes: minutes.value })
    p.value.script = r.script
    toast('剧本已生成，可以直接修改', 'success')
  } finally {
    busy.script = false
  }
}

async function aiElements() {
  busy.elements = true
  try {
    const r = await api.post(`/api/projects/${p.value.id}/ai/elements`)
    setProject(r.project)
    toast(r.added ? `新增 ${r.added} 个角色 / 场景` : '没有发现新的角色或场景', 'success')
  } finally {
    busy.elements = false
  }
}

async function aiStoryboard() {
  if (p.value.shots.length && !(await confirmDialog({ title: '重新拆分镜', content: `将替换现有的 ${p.value.shots.length} 个镜头（已生成的画面仍保留在作品库）。`, positiveText: '重新拆分' }))) return
  busy.storyboard = true
  try {
    setProject(await api.post(`/api/projects/${p.value.id}/ai/storyboard`, { replace: true }))
    toast(`已拆分为 ${p.value.shots.length} 个镜头`, 'success')
  } finally {
    busy.storyboard = false
  }
}

// ---------------------------------------------------------------- 角色与场景

function editElement(e) {
  Object.assign(elForm, e ? { id: e.id, kind: e.kind, name: e.name, description: e.description, prompt: e.prompt, ref_asset_id: e.ref?.id || null }
    : { id: null, kind: 'character', name: '', description: '', prompt: '', ref_asset_id: null })
  elModal.value = true
}

async function saveElement() {
  const { id, ...body } = elForm
  setProject(id ? await api.patch(`/api/projects/${p.value.id}/elements/${id}`, body) : await api.post(`/api/projects/${p.value.id}/elements`, body))
  elModal.value = false
}

async function removeElement(e) {
  if (!(await confirmDialog({ title: '删除', content: `确定删除「${e.name}」？`, positiveText: '删除' }))) return
  setProject(await api.del(`/api/projects/${p.value.id}/elements/${e.id}`))
}

async function genElement(e) {
  setProject(await api.post(`/api/projects/${p.value.id}/elements/${e.id}/generate`))
}

async function onPick(list) {
  const e = pickFor.value
  pickFor.value = null
  if (!e || !list.length) return
  setProject(await api.patch(`/api/projects/${p.value.id}/elements/${e.id}`, {
    kind: e.kind, name: e.name, description: e.description, prompt: e.prompt, ref_asset_id: list[0].id,
  }))
}

// ---------------------------------------------------------------- 分镜

function shotBody(s) {
  return {
    title: s.title, description: s.description, camera: s.camera, dialogue: s.dialogue, duration: s.duration,
    element_ids: s.element_ids, image_prompt: s.image_prompt, video_prompt: s.video_prompt,
    keyframe_asset_id: s.keyframe?.id ?? s.keyframe_asset_id ?? null, video_asset_id: s.video?.id ?? s.video_asset_id ?? null,
    audio_asset_id: s.audio?.id ?? s.audio_asset_id ?? null,
  }
}

function editShot(s, afterId) {
  Object.assign(shotForm, s ? { id: s.id, ...shotBody(s) }
    : { id: null, after_id: afterId ?? null, title: '', description: '', camera: '', dialogue: '', duration: 4, element_ids: [], image_prompt: '', video_prompt: '', keyframe_asset_id: null, video_asset_id: null, audio_asset_id: null })
  shotModal.value = true
}

async function saveShot() {
  const { id, ...body } = shotForm
  setProject(id ? await api.put(`/api/projects/${p.value.id}/shots/${id}`, body) : await api.post(`/api/projects/${p.value.id}/shots`, body))
  shotModal.value = false
}

function shotMenu(s, i) {
  return [
    { label: '编辑', key: 'edit' },
    { label: '在后面插入镜头', key: 'insert' },
    { label: '上移', key: 'up', disabled: i === 0 },
    { label: '下移', key: 'down', disabled: i === p.value.shots.length - 1 },
    { type: 'divider', key: 'd1' },
    { label: '清除视频（改用关键帧）', key: 'clear-video', disabled: !s.video },
    { label: '清除配音', key: 'clear-audio', disabled: !s.audio },
    { type: 'divider', key: 'd2' },
    { label: '删除镜头', key: 'delete' },
  ]
}

async function onShotMenu(key, s, i) {
  const pid = p.value.id
  if (key === 'edit') editShot(s)
  else if (key === 'insert') editShot(null, s.id)
  else if (key === 'up' || key === 'down') {
    const ids = p.value.shots.map((x) => x.id)
    const j = key === 'up' ? i - 1 : i + 1;
    [ids[i], ids[j]] = [ids[j], ids[i]]
    setProject(await api.post(`/api/projects/${pid}/shots/reorder`, { ids }))
  } else if (key === 'clear-video' || key === 'clear-audio') {
    const body = shotBody(s)
    body[key === 'clear-video' ? 'video_asset_id' : 'audio_asset_id'] = null
    setProject(await api.put(`/api/projects/${pid}/shots/${s.id}`, body))
  } else if (key === 'delete') {
    if (!(await confirmDialog({ title: '删除镜头', content: `确定删除镜头 ${i + 1}？`, positiveText: '删除' }))) return
    setProject(await api.del(`/api/projects/${pid}/shots/${s.id}`))
  }
}

async function genShot(s, slot) {
  const r = await api.post(`/api/projects/${p.value.id}/generate`, { slot, shot_ids: [s.id], only_missing: false })
  setProject(r.project)
}

async function batch(slot) {
  const r = await api.post(`/api/projects/${p.value.id}/generate`, { slot, only_missing: true })
  setProject(r.project)
  toast(r.created ? `已提交 ${r.created} 个${SLOT[slot]}任务` : `所有镜头都已有${SLOT[slot]}`, r.created ? 'success' : 'info')
}

async function render() {
  setProject(await api.post(`/api/projects/${p.value.id}/render`))
}

function preview(list, a) {
  viewerItems.value = list
  viewerIndex.value = list.findIndex((x) => x.id === a.id)
}

// 有任务进行中时轮询项目状态
watch(anyRunning, (on) => {
  clearInterval(timer)
  if (on) timer = setInterval(() => load().catch(() => null), 2500)
})

onMounted(async () => {
  await loadProviders()
  await load()
  if (p.value.shots.length) tab.value = p.value.output ? 'render' : 'shots'
  else if (p.value.script) tab.value = 'elements'
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.studio-page { max-width: 1280px; }
.head { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.name-input { max-width: 420px; }
.name-input :deep(input) { font-size: 22px; font-weight: 700; }
.stepper { display: flex; gap: 6px; margin-bottom: 16px; flex-wrap: wrap; }
.st { display: flex; align-items: center; gap: 8px; padding: 8px 16px 8px 10px; border-radius: 20px; border: 1px solid var(--border); background: var(--panel); color: var(--text-2); cursor: pointer; font-size: 14px; }
.st.active { border-color: var(--primary); color: var(--primary); font-weight: 600; background: color-mix(in srgb, var(--primary) 8%, var(--panel)); }
.st-no { width: 20px; height: 20px; border-radius: 50%; display: grid; place-items: center; font-size: 11.5px; background: var(--panel-2); }
.st.done .st-no { background: var(--success); color: #fff; }
.st-count { font-size: 12px; font-weight: 400; }
.panel { padding: 18px; border-radius: 14px; background: var(--panel); border: 1px solid var(--border); }
.two-col { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 3fr); gap: 22px; }
.script :deep(textarea) { font-size: 14px; line-height: 1.8; }
.small { font-size: 12.5px; }
.err { color: var(--danger); }
.toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.el-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
.el-card { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; background: var(--bg); display: flex; flex-direction: column; }
.el-img { aspect-ratio: 1; background: var(--panel-2); display: grid; place-items: center; cursor: zoom-in; overflow: hidden; }
.el-img img { width: 100%; height: 100%; object-fit: cover; }
.el-ph { display: flex; flex-direction: column; align-items: center; gap: 6px; color: var(--muted); padding: 10px; text-align: center; }
.el-body { padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; }
.el-body .row { gap: 6px; min-width: 0; }
.clamp { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.55; }
.el-actions { gap: 2px !important; }
.shots { display: flex; flex-direction: column; gap: 10px; }
.shot { display: grid; grid-template-columns: 28px auto minmax(0, 1fr) auto; gap: 12px; align-items: start; padding: 10px; border: 1px solid var(--border); border-radius: 12px; background: var(--bg); }
.shot-no { width: 26px; height: 26px; border-radius: 8px; background: color-mix(in srgb, var(--primary) 12%, transparent); color: var(--primary); display: grid; place-items: center; font-weight: 700; font-size: 13px; }
.media-col { display: flex; gap: 6px; }
.media-box { position: relative; width: 160px; aspect-ratio: 16 / 9; border-radius: 8px; overflow: hidden; background: var(--panel-2); cursor: zoom-in; }
.a9-16 .media-box, .a3-4 .media-box { width: 84px; aspect-ratio: 9 / 16; }
.a1-1 .media-box { width: 110px; aspect-ratio: 1; }
.media-box img, .media-box video { width: 100%; height: 100%; object-fit: cover; display: block; }
.media-ph { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; color: var(--muted); font-size: 11.5px; }
.media-ph.overlay { background: rgba(0, 0, 0, .45); color: #fff; }
.play { position: absolute; left: 6px; bottom: 6px; color: #fff; filter: drop-shadow(0 1px 2px rgba(0, 0, 0, .6)); }
.shot-body { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.shot-title { gap: 8px; min-width: 0; }
.dialogue { display: flex; gap: 6px; align-items: flex-start; color: var(--text-2); background: var(--panel-2); padding: 4px 8px; border-radius: 6px; }
.chips { display: flex; gap: 4px; flex-wrap: wrap; }
.chip { font-size: 11.5px; padding: 1px 8px; border-radius: 8px; background: color-mix(in srgb, var(--primary) 10%, transparent); color: var(--primary); }
.audio { height: 30px; width: min(320px, 100%); }
.shot-ops { display: flex; flex-direction: column; gap: 4px; align-items: stretch; }
.timeline { display: flex; gap: 3px; height: 72px; border-radius: 10px; overflow: hidden; background: var(--panel-2); padding: 3px; }
.tl-item { position: relative; flex-basis: 0; min-width: 24px; border-radius: 6px; overflow: hidden; background: var(--border); }
.tl-item img { width: 100%; height: 100%; object-fit: cover; }
.tl-no { position: absolute; left: 4px; top: 2px; font-size: 11px; font-weight: 700; color: #fff; text-shadow: 0 1px 2px rgba(0, 0, 0, .7); }
.tl-icons { position: absolute; right: 4px; bottom: 2px; display: flex; gap: 2px; color: #fff; filter: drop-shadow(0 1px 1px rgba(0, 0, 0, .7)); }
.render-grid { display: grid; grid-template-columns: minmax(260px, 1fr) minmax(0, 2fr); gap: 20px; align-items: start; }
.checklist { display: flex; flex-direction: column; gap: 10px; }
.ck { display: flex; gap: 8px; align-items: center; font-size: 13.5px; color: var(--text-2); flex-wrap: wrap; }
.ck.ok { color: var(--success); }
.ck .muted { font-size: 12px; }
.output { display: flex; flex-direction: column; gap: 10px; }
.out-video { width: 100%; max-height: 60vh; border-radius: 10px; background: #000; }
.out-ph { aspect-ratio: 16 / 9; border-radius: 10px; border: 1.5px dashed var(--border); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: var(--muted); }
.form-row { display: flex; gap: 12px; }
.set-row { margin-bottom: 14px; }
@media (max-width: 900px) {
  .two-col, .render-grid { grid-template-columns: 1fr; }
  .shot { grid-template-columns: 24px minmax(0, 1fr); }
  .media-col { grid-column: 2; }
  .shot-body, .shot-ops { grid-column: 2; }
  .shot-ops { flex-direction: row; flex-wrap: wrap; }
}
</style>
