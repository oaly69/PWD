<template>
  <Teleport to="body">
    <transition name="fade">
      <div v-if="current" ref="viewerEl" class="viewer" :class="{ 'no-info': !showInfo }" @click.self="close">
        <div class="stage" @click.self="close">
          <button v-if="index > 0" class="nav prev" title="上一张（←）" @click="go(-1)"><ChevronLeft :size="26" /></button>
          <ImageStage v-if="current.kind === 'image'" ref="stage" :key="current.id" :src="current.url" @close="close" @nav="go" />
          <video v-else-if="current.kind === 'video'" :key="current.id" :src="current.url" class="media" controls autoplay loop />
          <div v-else class="audio-box">
            <Music :size="48" :stroke-width="1.5" />
            <audio :key="current.id" :src="current.url" controls autoplay />
          </div>
          <button v-if="index < items.length - 1" class="nav next" title="下一张（→）" @click="go(1)"><ChevronRight :size="26" /></button>

          <div class="viewer-bar" @dblclick.stop>
            <template v-if="current.kind === 'image'">
              <button title="缩小（-）" @click="stage?.zoomOut()"><ZoomOut :size="18" /></button>
              <button class="pct" title="点击切换适应窗口 / 原始尺寸（0 / 1）" @click="stage?.toggleFit()">{{ stage?.percent ?? 100 }}%</button>
              <button title="放大（+）" @click="stage?.zoomIn()"><ZoomIn :size="18" /></button>
              <i class="sep" />
              <button title="适应窗口（0）" @click="stage?.fit()"><Scan :size="18" /></button>
              <button title="向左旋转（Shift+R）" @click="stage?.rotate(-90)"><RotateCcw :size="18" /></button>
              <button title="向右旋转（R）" @click="stage?.rotate(90)"><RotateCw :size="18" /></button>
              <button class="m-hide" title="水平翻转（H）" @click="stage?.flip()"><FlipHorizontal2 :size="18" /></button>
              <button class="m-hide" title="还原" @click="stage?.reset()"><RefreshCcw :size="18" /></button>
              <i class="sep" />
            </template>
            <button title="下载" @click="downloadUrl(current.url, `pwd-${current.id}`)"><Download :size="18" /></button>
            <button v-if="canFullscreen" class="m-hide" :title="fullscreen ? '退出全屏' : '全屏'" @click="toggleFullscreen">
              <component :is="fullscreen ? Minimize : Maximize" :size="18" />
            </button>
            <button :title="showInfo ? '隐藏信息面板（I）' : '显示信息面板（I）'" @click="showInfo = !showInfo">
              <component :is="showInfo ? PanelRightClose : PanelRightOpen" :size="18" />
            </button>
            <button class="close-btn" title="关闭（Esc）" @click="close"><X :size="18" /></button>
          </div>
        </div>

        <aside v-show="showInfo" class="info">
          <div class="info-head">
            <n-tag size="small" :bordered="false" :type="current.source === 'upload' ? 'default' : 'primary'">
              {{ current.source === 'upload' ? '上传素材' : '生成作品' }}
            </n-tag>
            <span class="muted small">{{ index + 1 }} / {{ items.length }}</span>
            <span class="spacer" />
            <n-button quaternary circle size="small" @click="close"><template #icon><X :size="18" /></template></n-button>
          </div>

          <div class="scroll">
            <div class="label">提示词</div>
            <div class="prompt">{{ current.prompt || '（无）' }}</div>
            <n-button v-if="current.prompt" size="tiny" secondary @click="copyPrompt"><template #icon><Copy :size="12" /></template>复制提示词</n-button>
            <template v-if="current.params?.negative_prompt">
              <div class="label">反向提示词</div>
              <div class="prompt neg">{{ current.params.negative_prompt }}</div>
            </template>

            <div class="label">信息</div>
            <dl class="meta">
              <template v-if="current.model"><dt>模型</dt><dd>{{ current.model }}</dd></template>
              <template v-if="current.params?.served_by"><dt>实际服务</dt><dd>{{ current.params.served_by }}（自动切换）</dd></template>
              <template v-if="current.width"><dt>分辨率</dt><dd>{{ current.width }} × {{ current.height }}</dd></template>
              <template v-if="current.params?.style"><dt>风格</dt><dd>{{ current.params.style }}</dd></template>
              <template v-if="current.params?.seed != null"><dt>种子</dt><dd>{{ current.params.seed }}</dd></template>
              <template v-if="current.params?.voice"><dt>音色</dt><dd>{{ current.params.voice }}</dd></template>
              <template v-if="current.params?.seconds"><dt>时长</dt><dd>{{ current.params.seconds }} 秒</dd></template>
              <dt>大小</dt><dd>{{ formatBytes(current.size) }}</dd>
              <template v-if="boards"><dt>作品集</dt><dd>
                <n-select size="tiny" :value="current.board_id || 0" :options="boardOptions" :consistent-menu-width="false" class="board-select" @update:value="moveTo" />
              </dd></template>
              <dt>时间</dt><dd>{{ formatTime(current.created_at) }}</dd>
            </dl>
          </div>

          <div class="actions">
            <n-button secondary :type="current.favorite ? 'warning' : 'default'" @click="toggleFav">
              <template #icon><Star :size="16" :fill="current.favorite ? 'currentColor' : 'none'" /></template>
              {{ current.favorite ? '已收藏' : '收藏' }}
            </n-button>
            <n-button secondary @click="downloadUrl(current.url, `pwd-${current.id}`)"><template #icon><Download :size="16" /></template>下载</n-button>
            <n-dropdown v-if="current.kind === 'image'" trigger="click" :options="EDIT_OPS" @select="(k) => { editOp = k; editing = current }">
              <n-button secondary type="primary"><template #icon><Wand2 :size="16" /></template>编辑图片</n-button>
            </n-dropdown>
            <n-button v-if="current.kind === 'image'" secondary @click="goStudio('image', 'ref')"><template #icon><ImagePlus :size="16" /></template>作为参考图</n-button>
            <n-button v-if="current.kind === 'image'" secondary @click="goStudio('video', 'ref')"><template #icon><Film :size="16" /></template>生成视频</n-button>
            <n-button v-if="current.source === 'generated' && studio" secondary @click="goStudio(studio, 'asset')"><template #icon><Repeat :size="16" /></template>复用参数</n-button>
            <n-button secondary type="error" @click="remove"><template #icon><Trash2 :size="16" /></template>删除</n-button>
          </div>
        </aside>
      </div>
    </transition>
  </Teleport>
  <ImageEditor v-model:asset="editing" :initial-op="editOp" />
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NDropdown, NSelect, NTag } from 'naive-ui'
import ImageEditor from './ImageEditor.vue'
import ImageStage from './ImageStage.vue'
import {
  ChevronLeft, ChevronRight, Copy, Download, Film, FlipHorizontal2, ImagePlus, Maximize, Minimize, Music, PanelRightClose, PanelRightOpen,
  RefreshCcw, Repeat, RotateCcw, RotateCw, Scan, Star, Trash2, Wand2, X, ZoomIn, ZoomOut,
} from 'lucide-vue-next'
import { api, confirmDialog, toast } from '../api'
import { copyText, downloadUrl, formatBytes, formatTime } from '../utils/format'
import { useLocalRef } from '../composables/localRef'

const props = defineProps({
  items: { type: Array, default: () => [] },
  index: { type: Number, default: -1 },
  boards: { type: Array, default: null }, // 传入时显示「作品集」选择
})
const emit = defineEmits(['update:index', 'deleted', 'changed'])
const router = useRouter()
const viewerEl = ref(null)
const stage = ref(null)
const showInfo = useLocalRef('pwd.viewer.info', true)
const fullscreen = ref(false)
const canFullscreen = typeof document !== 'undefined' && !!document.documentElement.requestFullscreen
const editing = ref(null)
const editOp = ref('inpaint')
const EDIT_OPS = [
  { label: '局部重绘', key: 'inpaint' },
  { label: '扩图', key: 'outpaint' },
  { label: '高清放大', key: 'upscale' },
  { label: '去除背景', key: 'rembg' },
]

const current = computed(() => (props.index >= 0 ? props.items[props.index] : null))
const studio = computed(() => ({ image: 'image', video: 'video', audio: 'speech' })[current.value?.kind])

function close() {
  if (document.fullscreenElement) document.exitFullscreen?.()
  emit('update:index', -1)
}

function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen()
  else viewerEl.value?.requestFullscreen?.().catch(() => {})
}
function onFullscreenChange() {
  fullscreen.value = !!document.fullscreenElement
}
function go(d) {
  const i = props.index + d
  if (i >= 0 && i < props.items.length) emit('update:index', i)
}

async function toggleFav() {
  const a = current.value
  const r = await api.patch(`/api/assets/${a.id}`, { favorite: !a.favorite })
  a.favorite = r.favorite
  emit('changed', a)
}

const boardOptions = computed(() => [{ label: '未归类', value: 0 }, ...(props.boards || []).map((b) => ({ label: b.name, value: b.id }))])

async function moveTo(boardId) {
  const a = current.value
  const r = await api.patch(`/api/assets/${a.id}`, { board_id: boardId })
  a.board_id = r.board_id
  toast(boardId ? '已移入作品集' : '已移出作品集', 'success')
  emit('changed', a)
}

async function copyPrompt() {
  if (await copyText(current.value.prompt)) toast('已复制提示词', 'success')
}

function goStudio(target, mode) {
  const id = current.value.id
  close()
  router.push({ path: `/${target}`, query: { [mode]: id } })
}

async function remove() {
  const a = current.value
  if (!(await confirmDialog({ title: '删除作品', content: '文件将被永久删除，无法恢复。确定删除吗？', positiveText: '删除' }))) return
  await api.del(`/api/assets/${a.id}`)
  toast('已删除', 'success')
  emit('deleted', a)
  if (props.index >= props.items.length - 1) emit('update:index', props.items.length - 2)
}

function onKey(e) {
  if (!current.value || editing.value || ['INPUT', 'TEXTAREA'].includes(e.target.tagName) || e.ctrlKey || e.metaKey || e.altKey) return
  const s = stage.value
  const k = e.key
  if (k === 'Escape') {
    // 全屏时 Esc 由浏览器先退出全屏
    if (!document.fullscreenElement) close()
  } else if (k === 'ArrowLeft') go(-1)
  else if (k === 'ArrowRight') go(1)
  else if (k.toLowerCase() === 'f') toggleFav()
  else if (k.toLowerCase() === 'i') showInfo.value = !showInfo.value
  else if (!s) return
  else if (k === '+' || k === '=') s.zoomIn()
  else if (k === '-' || k === '_') s.zoomOut()
  else if (k === '0') s.fit()
  else if (k === '1') s.actual()
  else if (k.toLowerCase() === 'r') s.rotate(e.shiftKey ? -90 : 90)
  else if (k.toLowerCase() === 'h') s.flip()
  else return
  e.preventDefault()
}

onMounted(() => {
  window.addEventListener('keydown', onKey)
  document.addEventListener('fullscreenchange', onFullscreenChange)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})
</script>

<style scoped>
.viewer { position: fixed; inset: 0; z-index: 2000; display: flex; background: rgba(8, 8, 12, .92); backdrop-filter: blur(6px); }
.stage { flex: 1; min-width: 0; position: relative; display: flex; align-items: center; justify-content: center; padding: 24px 24px 72px; overflow: hidden; }
.media { max-width: 100%; max-height: calc(100vh - 96px); object-fit: contain; border-radius: 6px; box-shadow: 0 10px 40px rgba(0, 0, 0, .5); }
.viewer-bar { position: absolute; left: 50%; bottom: 16px; transform: translateX(-50%); z-index: 3; display: flex; align-items: center; gap: 2px; padding: 4px; border-radius: 12px; background: rgba(20, 20, 26, .78); backdrop-filter: blur(8px); box-shadow: 0 4px 20px rgba(0, 0, 0, .35); max-width: calc(100% - 24px); overflow-x: auto; scrollbar-width: none; }
.viewer-bar button { flex-shrink: 0; height: 34px; min-width: 34px; padding: 0 8px; border: none; border-radius: 8px; background: transparent; color: #e8e8ee; cursor: pointer; display: grid; place-items: center; font-size: 12.5px; font-variant-numeric: tabular-nums; }
.viewer-bar button:hover { background: rgba(255, 255, 255, .14); }
.viewer-bar .pct { min-width: 54px; }
.viewer-bar .sep { flex-shrink: 0; width: 1px; height: 18px; margin: 0 4px; background: rgba(255, 255, 255, .18); }
.viewer-bar .close-btn { display: none; }
.no-info .viewer-bar .close-btn, .viewer:fullscreen .viewer-bar .close-btn { display: grid; }
.audio-box { display: flex; flex-direction: column; align-items: center; gap: 24px; color: #ccc; }
.audio-box audio { width: min(480px, 80vw); }
.nav { position: absolute; top: 50%; transform: translateY(-50%); width: 44px; height: 44px; border-radius: 50%; border: none; background: rgba(255, 255, 255, .1); color: #fff; cursor: pointer; display: grid; place-items: center; z-index: 2; }
.nav:hover { background: rgba(255, 255, 255, .2); }
.prev { left: 16px; } .next { right: 16px; }
.info { width: 340px; flex-shrink: 0; background: var(--panel); display: flex; flex-direction: column; border-left: 1px solid var(--border); }
.info-head { display: flex; align-items: center; gap: 8px; padding: 14px 14px 10px 18px; }
.small { font-size: 12px; }
.scroll { flex: 1; overflow: auto; padding: 0 18px 12px; }
.label { font-size: 12px; font-weight: 600; color: var(--muted); margin: 16px 0 6px; }
.prompt { white-space: pre-wrap; word-break: break-word; font-size: 13.5px; line-height: 1.65; margin-bottom: 8px; max-height: 220px; overflow: auto; }
.prompt.neg { color: var(--text-2); }
.meta { display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; margin: 0; font-size: 13px; }
.meta dt { color: var(--muted); }
.meta dd { margin: 0; word-break: break-all; }
.board-select { width: 160px; }
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 14px 18px 18px; border-top: 1px solid var(--border); }
.fade-enter-active, .fade-leave-active { transition: opacity .15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
@media (max-width: 860px) {
  .viewer { flex-direction: column; }
  .stage { flex: none; height: 55vh; padding: 12px 12px 60px; }
  .no-info .stage { flex: 1; height: auto; }
  .media { max-height: calc(55vh - 72px); }
  .no-info .media { max-height: calc(100vh - 72px); }
  .info { width: 100%; flex: 1; min-height: 0; border-left: none; }
  .nav { width: 36px; height: 36px; }
  .prev { left: 8px; } .next { right: 8px; }
  .viewer-bar { bottom: 10px; }
  .viewer-bar button { height: 32px; min-width: 32px; padding: 0 6px; }
  .viewer-bar .m-hide { display: none; }
}
</style>
