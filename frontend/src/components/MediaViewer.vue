<template>
  <Teleport to="body">
    <transition name="fade">
      <div v-if="current" class="viewer" @click.self="close">
        <div class="stage" @click.self="close">
          <button v-if="index > 0" class="nav prev" @click="go(-1)"><ChevronLeft :size="26" /></button>
          <img v-if="current.kind === 'image'" :key="current.id" :src="current.url" class="media" @dblclick="zoom = !zoom" :class="{ zoom }" />
          <video v-else-if="current.kind === 'video'" :key="current.id" :src="current.url" class="media" controls autoplay loop />
          <div v-else class="audio-box">
            <Music :size="48" :stroke-width="1.5" />
            <audio :key="current.id" :src="current.url" controls autoplay />
          </div>
          <button v-if="index < items.length - 1" class="nav next" @click="go(1)"><ChevronRight :size="26" /></button>
        </div>

        <aside class="info">
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
              <template v-if="current.width"><dt>分辨率</dt><dd>{{ current.width }} × {{ current.height }}</dd></template>
              <template v-if="current.params?.style"><dt>风格</dt><dd>{{ current.params.style }}</dd></template>
              <template v-if="current.params?.seed != null"><dt>种子</dt><dd>{{ current.params.seed }}</dd></template>
              <template v-if="current.params?.voice"><dt>音色</dt><dd>{{ current.params.voice }}</dd></template>
              <template v-if="current.params?.seconds"><dt>时长</dt><dd>{{ current.params.seconds }} 秒</dd></template>
              <dt>大小</dt><dd>{{ formatBytes(current.size) }}</dd>
              <dt>时间</dt><dd>{{ formatTime(current.created_at) }}</dd>
            </dl>
          </div>

          <div class="actions">
            <n-button secondary :type="current.favorite ? 'warning' : 'default'" @click="toggleFav">
              <template #icon><Star :size="16" :fill="current.favorite ? 'currentColor' : 'none'" /></template>
              {{ current.favorite ? '已收藏' : '收藏' }}
            </n-button>
            <n-button secondary @click="downloadUrl(current.url, `pwd-${current.id}`)"><template #icon><Download :size="16" /></template>下载</n-button>
            <n-button v-if="current.kind === 'image'" secondary @click="goStudio('image', 'ref')"><template #icon><ImagePlus :size="16" /></template>作为参考图</n-button>
            <n-button v-if="current.kind === 'image'" secondary @click="goStudio('video', 'ref')"><template #icon><Film :size="16" /></template>生成视频</n-button>
            <n-button v-if="current.source === 'generated' && studio" secondary @click="goStudio(studio, 'asset')"><template #icon><Repeat :size="16" /></template>复用参数</n-button>
            <n-button secondary type="error" @click="remove"><template #icon><Trash2 :size="16" /></template>删除</n-button>
          </div>
        </aside>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NTag } from 'naive-ui'
import { ChevronLeft, ChevronRight, Copy, Download, Film, ImagePlus, Music, Repeat, Star, Trash2, X } from 'lucide-vue-next'
import { api, confirmDialog, toast } from '../api'
import { copyText, downloadUrl, formatBytes, formatTime } from '../utils/format'

const props = defineProps({
  items: { type: Array, default: () => [] },
  index: { type: Number, default: -1 },
})
const emit = defineEmits(['update:index', 'deleted', 'changed'])
const router = useRouter()
const zoom = ref(false)

const current = computed(() => (props.index >= 0 ? props.items[props.index] : null))
const studio = computed(() => ({ image: 'image', video: 'video', audio: 'speech' })[current.value?.kind])

function close() {
  emit('update:index', -1)
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
  if (!current.value || ['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return
  if (e.key === 'Escape') close()
  else if (e.key === 'ArrowLeft') go(-1)
  else if (e.key === 'ArrowRight') go(1)
  else if (e.key.toLowerCase() === 'f') toggleFav()
}

watch(() => props.index, () => { zoom.value = false })
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.viewer { position: fixed; inset: 0; z-index: 2000; display: flex; background: rgba(8, 8, 12, .92); backdrop-filter: blur(6px); }
.stage { flex: 1; min-width: 0; position: relative; display: flex; align-items: center; justify-content: center; padding: 24px; }
.media { max-width: 100%; max-height: calc(100vh - 48px); object-fit: contain; border-radius: 6px; box-shadow: 0 10px 40px rgba(0, 0, 0, .5); cursor: zoom-in; }
.media.zoom { max-width: none; max-height: none; cursor: zoom-out; }
.stage:has(.zoom) { overflow: auto; align-items: flex-start; justify-content: flex-start; }
video.media { cursor: default; }
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
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 14px 18px 18px; border-top: 1px solid var(--border); }
.fade-enter-active, .fade-leave-active { transition: opacity .15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
@media (max-width: 860px) {
  .viewer { flex-direction: column; }
  .stage { flex: none; height: 55vh; padding: 12px; }
  .media { max-height: calc(55vh - 24px); }
  .info { width: 100%; flex: 1; min-height: 0; border-left: none; }
}
</style>
