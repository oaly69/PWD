<template>
  <div
    class="refs"
    :class="{ dragging }"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="onDrop"
  >
    <div v-for="a in modelValue" :key="a.id" class="ref">
      <img :src="a.thumb_url || a.url" />
      <button class="remove" type="button" @click="remove(a)"><X :size="12" /></button>
    </div>
    <n-dropdown v-if="modelValue.length < max" trigger="click" :options="addOptions" @select="onAdd">
      <button type="button" class="add" :disabled="uploading">
        <n-spin v-if="uploading" :size="16" />
        <template v-else>
          <ImagePlus :size="18" />
          <span>{{ modelValue.length ? '添加' : '添加参考图' }}</span>
        </template>
      </button>
    </n-dropdown>
    <div v-if="!modelValue.length" class="hint">拖拽、粘贴或从作品库选择</div>
    <input ref="fileInput" type="file" accept="image/*" :multiple="max > 1" hidden @change="onFiles" />
    <AssetPicker v-model:show="picker" :max="max - modelValue.length" @select="onPicked" />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { NDropdown, NSpin } from 'naive-ui'
import { ImagePlus, X } from 'lucide-vue-next'
import { toast, uploadFile } from '../api'
import AssetPicker from './AssetPicker.vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  max: { type: Number, default: 1 },
})
const emit = defineEmits(['update:modelValue'])

const fileInput = ref(null)
const picker = ref(false)
const dragging = ref(false)
const uploading = ref(false)

const addOptions = [
  { label: '上传本地图片', key: 'upload' },
  { label: '从作品库选择', key: 'gallery' },
]

function onAdd(key) {
  if (key === 'upload') fileInput.value?.click()
  else picker.value = true
}

function add(list) {
  const merged = [...props.modelValue]
  for (const a of list) if (!merged.some((m) => m.id === a.id) && merged.length < props.max) merged.push(a)
  emit('update:modelValue', merged)
}

function remove(a) {
  emit('update:modelValue', props.modelValue.filter((x) => x.id !== a.id))
}

async function uploadMany(files) {
  const images = [...files].filter((f) => f.type.startsWith('image/')).slice(0, props.max - props.modelValue.length)
  if (!images.length) return
  uploading.value = true
  try {
    const uploaded = []
    for (const f of images) uploaded.push(await uploadFile(f))
    add(uploaded)
  } finally {
    uploading.value = false
  }
}

function onFiles(e) {
  uploadMany(e.target.files)
  e.target.value = ''
}

function onDrop(e) {
  dragging.value = false
  uploadMany(e.dataTransfer.files)
}

function onPicked(list) {
  add(list)
}

function onPaste(e) {
  const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith('image/'))
  if (files.length && props.modelValue.length < props.max) {
    e.preventDefault()
    uploadMany(files)
    toast('已从剪贴板添加参考图', 'success')
  }
}

onMounted(() => window.addEventListener('paste', onPaste))
onUnmounted(() => window.removeEventListener('paste', onPaste))
</script>

<style scoped>
.refs { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 8px; border: 1px dashed var(--border); border-radius: 10px; transition: all .15s; }
.refs.dragging { border-color: var(--primary); background: color-mix(in srgb, var(--primary) 6%, transparent); }
.ref { position: relative; width: 64px; height: 64px; border-radius: 8px; overflow: hidden; background: var(--panel-2); }
.ref img { width: 100%; height: 100%; object-fit: cover; }
.remove { position: absolute; top: 3px; right: 3px; width: 18px; height: 18px; border-radius: 50%; border: none; display: grid; place-items: center; background: rgba(0, 0, 0, .55); color: #fff; cursor: pointer; padding: 0; }
.add { height: 64px; min-width: 64px; padding: 0 12px; border-radius: 8px; border: 1px solid var(--border); background: var(--panel); color: var(--text-2); cursor: pointer; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; font-size: 12px; }
.add:hover { border-color: var(--primary); color: var(--primary); }
.hint { font-size: 12px; color: var(--muted); }
</style>
