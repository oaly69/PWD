<template>
  <div
    ref="stageEl"
    class="image-stage"
    :class="{ pannable: canPan, dragging }"
    @wheel.prevent="onWheel"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
    @dblclick="onDblClick"
  >
    <img
      :src="src"
      class="img"
      :class="{ animating, ready: loaded, pixel: view.scale >= 4 }"
      :style="imgStyle"
      draggable="false"
      alt=""
      @load="onLoad"
    />
    <div v-if="!loaded" class="loading">加载中…</div>
    <transition name="hint">
      <div v-if="hintVisible" class="hint">{{ percent }}%</div>
    </transition>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'

const props = defineProps({ src: { type: String, required: true } })
const emit = defineEmits(['close', 'nav'])

const MAX_SCALE = 20
const stageEl = ref(null)
const natural = reactive({ w: 0, h: 0 })
const box = reactive({ w: 0, h: 0 })
const view = reactive({ scale: 1, x: 0, y: 0, rotate: 0, flip: false })
const loaded = ref(false)
const animating = ref(false)
const dragging = ref(false)
const hintVisible = ref(false)

// 适应窗口时的缩放比例（小图不放大）
const fitScale = computed(() => {
  if (!natural.w || !box.w) return 1
  const turned = view.rotate % 180 !== 0
  const w = turned ? natural.h : natural.w
  const h = turned ? natural.w : natural.h
  return Math.min(1, box.w / w, box.h / h)
})
const minScale = computed(() => Math.min(fitScale.value, 1) / 4)
const isFit = computed(() => Math.abs(view.scale - fitScale.value) < 1e-3 && !view.x && !view.y)
const percent = computed(() => Math.round(view.scale * 100))

// 旋转后图片在屏幕上的尺寸
function shownSize(scale = view.scale) {
  const turned = view.rotate % 180 !== 0
  return { w: (turned ? natural.h : natural.w) * scale, h: (turned ? natural.w : natural.h) * scale }
}
const canPan = computed(() => {
  const s = shownSize()
  return s.w > box.w + 1 || s.h > box.h + 1
})

const imgStyle = computed(() => ({
  width: `${natural.w}px`,
  height: `${natural.h}px`,
  marginLeft: `${-natural.w / 2}px`,
  marginTop: `${-natural.h / 2}px`,
  transform: `translate(${view.x}px, ${view.y}px) scaleX(${view.flip ? -1 : 1}) rotate(${view.rotate}deg) scale(${view.scale})`,
}))

function clampPos() {
  const s = shownSize()
  const mx = Math.max(0, (s.w - box.w) / 2)
  const my = Math.max(0, (s.h - box.h) / 2)
  view.x = Math.min(mx, Math.max(-mx, view.x))
  view.y = Math.min(my, Math.max(-my, view.y))
}

let animTimer = 0
function animate() {
  animating.value = true
  clearTimeout(animTimer)
  animTimer = setTimeout(() => { animating.value = false }, 220)
}
let hintTimer = 0
function flashHint() {
  hintVisible.value = true
  clearTimeout(hintTimer)
  hintTimer = setTimeout(() => { hintVisible.value = false }, 800)
}

// 以 (px, py)（相对舞台中心的坐标）为中心缩放到 next
function zoomTo(next, px = 0, py = 0) {
  next = Math.min(MAX_SCALE, Math.max(minScale.value, next))
  const k = next / view.scale
  view.x = px - (px - view.x) * k
  view.y = py - (py - view.y) * k
  view.scale = next
  clampPos()
  flashHint()
}

function toCenter(clientX, clientY) {
  const r = stageEl.value.getBoundingClientRect()
  return [clientX - r.left - r.width / 2, clientY - r.top - r.height / 2]
}

function fit() {
  animate()
  view.scale = fitScale.value
  view.x = 0
  view.y = 0
  flashHint()
}
function actual(px = 0, py = 0) {
  animate()
  // 小图的「原尺寸」就是适应尺寸，此时放大到 2 倍
  zoomTo(fitScale.value >= 1 ? 2 : 1, px, py)
}
function toggleFit(px, py) {
  if (isFit.value) actual(px, py)
  else fit()
}
function zoomBy(factor) {
  animate()
  zoomTo(view.scale * factor)
}
function rotate(deg) {
  const wasFit = isFit.value
  animate()
  view.rotate += deg
  if (wasFit) {
    view.scale = fitScale.value
    view.x = view.y = 0
  } else clampPos()
}
function flip() {
  animate()
  view.flip = !view.flip
}
function reset() {
  animate()
  view.rotate = 0
  view.flip = false
  view.scale = fitScale.value
  view.x = view.y = 0
}

function measure() {
  if (!stageEl.value) return
  const wasFit = isFit.value
  box.w = stageEl.value.clientWidth
  box.h = stageEl.value.clientHeight
  if (wasFit || !loaded.value) {
    view.scale = fitScale.value
    view.x = view.y = 0
  } else clampPos()
}

function onLoad(e) {
  natural.w = e.target.naturalWidth
  natural.h = e.target.naturalHeight
  view.rotate = 0
  view.flip = false
  measure()
  view.scale = fitScale.value
  view.x = view.y = 0
  loaded.value = true
}

watch(() => props.src, () => { loaded.value = false })

// ---- 滚轮 / 触控板 ----
function onWheel(e) {
  if (!loaded.value) return
  const [px, py] = toCenter(e.clientX, e.clientY)
  // 触控板双指缩放会以 ctrlKey + 较小 deltaY 的形式出现
  const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY
  const speed = e.ctrlKey ? 0.01 : 0.0015
  zoomTo(view.scale * Math.exp(-delta * speed), px, py)
}

// ---- 指针：拖拽平移、双指缩放、滑动切换 ----
const pointers = new Map()
let gesture = null
let lastTap = { t: 0, x: 0, y: 0 }

function dist(a, b) { return Math.hypot(a.x - b.x, a.y - b.y) }
function mid(a, b) { return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 } }

function beginGesture() {
  const pts = [...pointers.values()]
  if (pts.length >= 2) {
    const [a, b] = pts
    gesture = { type: 'pinch', d0: dist(a, b) || 1, m0: mid(a, b), s0: view.scale, x0: view.x, y0: view.y, moved: true }
  } else if (pts.length === 1) {
    const p = pts[0]
    gesture = { type: 'pan', sx: p.x, sy: p.y, x0: view.x, y0: view.y, moved: false, start: performance.now(), pannable: canPan.value }
  } else gesture = null
}

function onPointerDown(e) {
  if (!loaded.value || (e.pointerType === 'mouse' && e.button !== 0)) return
  stageEl.value.setPointerCapture?.(e.pointerId)
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY, type: e.pointerType, target: e.target })
  beginGesture()
}

function onPointerMove(e) {
  const p = pointers.get(e.pointerId)
  if (!p || !gesture) return
  p.x = e.clientX
  p.y = e.clientY
  if (gesture.type === 'pinch') {
    const [a, b] = [...pointers.values()]
    const m = mid(a, b)
    const [cx, cy] = toCenter(gesture.m0.x, gesture.m0.y)
    // 先按起始中点缩放，再随中点平移
    const next = Math.min(MAX_SCALE, Math.max(minScale.value, gesture.s0 * dist(a, b) / gesture.d0))
    const k = next / gesture.s0
    view.scale = next
    view.x = cx - (cx - gesture.x0) * k + (m.x - gesture.m0.x)
    view.y = cy - (cy - gesture.y0) * k + (m.y - gesture.m0.y)
    flashHint()
    return
  }
  const dx = e.clientX - gesture.sx
  const dy = e.clientY - gesture.sy
  if (!gesture.moved && Math.hypot(dx, dy) < 4) return
  gesture.moved = true
  dragging.value = true
  if (gesture.pannable) {
    view.x = gesture.x0 + dx
    view.y = gesture.y0 + dy
    clampPos()
  } else if (p.type !== 'mouse') {
    // 未放大时，横向跟手，松手后判断是否切换
    view.x = dx
  }
}

function onPointerUp(e) {
  const p = pointers.get(e.pointerId)
  if (!p) return
  pointers.delete(e.pointerId)
  const g = gesture
  dragging.value = false

  if (g?.type === 'pinch') {
    if (pointers.size === 0) {
      animate()
      if (view.scale < fitScale.value) { view.scale = fitScale.value; view.x = view.y = 0 } else clampPos()
      gesture = null
    } else beginGesture() // 剩下一根手指继续平移
    return
  }
  gesture = null
  if (!g || e.type === 'pointercancel') return

  if (g.moved) {
    if (!g.pannable && p.type !== 'mouse') {
      const dx = e.clientX - g.sx
      const fast = performance.now() - g.start < 300
      animate()
      view.x = 0
      if (Math.abs(dx) > (fast ? 30 : box.w / 4)) emit('nav', dx < 0 ? 1 : -1)
    }
    return
  }

  // 触屏双击（移动端不一定派发 dblclick）
  if (p.type !== 'mouse') {
    const now = performance.now()
    lastTouchAt = now
    if (now - lastTap.t < 300 && Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < 30) {
      lastTap.t = 0
      clearTimeout(tapTimer)
      toggleFit(...toCenter(e.clientX, e.clientY))
      return
    }
    lastTap = { t: now, x: e.clientX, y: e.clientY }
  }
  // 单击空白处关闭（延迟，避免与双击冲突）
  if (p.target === stageEl.value) {
    clearTimeout(tapTimer)
    tapTimer = setTimeout(() => emit('close'), 260)
  }
}
let tapTimer = 0
let lastTouchAt = 0

function onDblClick(e) {
  clearTimeout(tapTimer)
  if (!loaded.value || performance.now() - lastTouchAt < 600) return
  toggleFit(...toCenter(e.clientX, e.clientY))
}

let ro
onMounted(() => {
  ro = new ResizeObserver(() => measure())
  ro.observe(stageEl.value)
  nextTick(measure)
})
onUnmounted(() => {
  ro?.disconnect()
  clearTimeout(tapTimer)
  clearTimeout(animTimer)
  clearTimeout(hintTimer)
})

defineExpose({ zoomIn: () => zoomBy(1.25), zoomOut: () => zoomBy(0.8), fit, actual: () => actual(), toggleFit: () => toggleFit(0, 0), rotate, flip, reset, percent, isFit })
</script>

<style scoped>
.image-stage { position: absolute; inset: 0; overflow: hidden; touch-action: none; user-select: none; -webkit-user-select: none; cursor: zoom-in; }
.image-stage.pannable { cursor: grab; }
.image-stage.dragging { cursor: grabbing; }
.img { position: absolute; left: 50%; top: 50%; max-width: none; transform-origin: center; will-change: transform; opacity: 0; box-shadow: 0 10px 40px rgba(0, 0, 0, .5); -webkit-user-drag: none; }
.img.ready { opacity: 1; }
.img.pixel { image-rendering: pixelated; }
.img.animating { transition: transform .2s ease-out; }
.loading { position: absolute; inset: 0; display: grid; place-items: center; color: rgba(255, 255, 255, .6); font-size: 13px; pointer-events: none; }
.hint { position: absolute; left: 50%; top: 16px; transform: translateX(-50%); padding: 4px 12px; border-radius: 999px; background: rgba(0, 0, 0, .6); color: #fff; font-size: 13px; pointer-events: none; }
.hint-leave-active { transition: opacity .3s; }
.hint-leave-to { opacity: 0; }
</style>
