<template>
  <div>
    <div class="row head">
      <div class="muted desc">用户组用于限制普通用户可用的能力和模型，并设置每日 / 每月用量上限。管理员不受限制；不属于任何组的用户也不受限制。</div>
      <span class="spacer" />
      <n-button type="primary" @click="edit()"><template #icon><Plus :size="16" /></template>新建用户组</n-button>
    </div>

    <div class="grid">
      <div v-for="g in groups" :key="g.id" class="card">
        <div class="card-head">
          <b class="ellipsis">{{ g.name }}</b>
          <n-tag v-if="settings.default_group_id === g.id" size="small" type="primary" :bordered="false">新用户默认</n-tag>
          <span class="spacer" />
          <span class="muted small">{{ g.members }} 人</span>
        </div>
        <div v-if="g.description" class="muted small">{{ g.description }}</div>
        <div class="kinds">
          <span v-for="k in KINDS" :key="k.key" class="kind" :class="{ off: !g.kinds.includes(k.key) }">
            <component :is="k.icon" :size="13" />{{ k.label }}
            <template v-if="g.kinds.includes(k.key) && g.models[k.key]?.length"> · {{ g.models[k.key].length }} 个模型</template>
          </span>
        </div>
        <div class="quotas">
          <span v-for="q in QUOTAS" :key="q.key" v-show="g.quotas[q.key]">{{ q.short }} {{ g.quotas[q.key] }}</span>
          <span v-if="!Object.keys(g.quotas).length" class="muted">不限用量</span>
        </div>
        <div class="row actions">
          <n-button size="small" secondary @click="edit(g)"><template #icon><Pencil :size="14" /></template>编辑</n-button>
          <n-button v-if="settings.default_group_id !== g.id" size="small" quaternary @click="setDefault(g.id)">设为新用户默认</n-button>
          <n-button v-else size="small" quaternary @click="setDefault(null)">取消默认</n-button>
          <span class="spacer" />
          <n-button size="small" quaternary type="error" @click="remove(g)"><template #icon><Trash2 :size="14" /></template></n-button>
        </div>
      </div>
    </div>
    <EmptyState v-if="loaded && !groups.length" :icon="UsersRound" title="还没有用户组" desc="例如创建「体验组」只开放对话和图像、每天 50 张图；把新注册的用户默认放进去。" />

    <n-modal v-model:show="show" preset="card" :title="form.id ? '编辑用户组' : '新建用户组'" style="width: min(720px, 96vw)" :segmented="{ content: true }">
      <n-form label-placement="top">
        <div class="row" style="gap: 12px; align-items: flex-start">
          <n-form-item label="名称" style="flex: 1"><n-input v-model:value="form.name" maxlength="64" placeholder="例如：体验组" /></n-form-item>
          <n-form-item label="说明" style="flex: 2"><n-input v-model:value="form.description" placeholder="可选" /></n-form-item>
        </div>
        <div class="field-label">能力与模型</div>
        <div class="muted small" style="margin-bottom: 8px">勾选允许使用的能力；可再限定只能使用哪些模型，留空表示该能力下的全部模型。</div>
        <div v-for="k in KINDS" :key="k.key" class="kind-row">
          <n-checkbox :checked="form.kinds.includes(k.key)" @update:checked="(v) => toggleKind(k.key, v)">
            <span class="kind-label"><component :is="k.icon" :size="14" />{{ k.label }}</span>
          </n-checkbox>
          <ModelSelect v-model="form.models[k.key]" :kind="k.key" multiple size="small" :placeholder="`全部${k.label}模型`" class="kind-models" :disabled="!form.kinds.includes(k.key)" />
        </div>
        <div class="field-label" style="margin-top: 14px">用量配额 <span class="muted small">留空或 0 表示不限制</span></div>
        <div class="quota-grid">
          <label v-for="q in QUOTAS" :key="q.key">
            <span>{{ q.label }}</span>
            <n-input-number v-model:value="form.quotas[q.key]" :min="0" :step="q.step" clearable size="small" placeholder="不限" />
          </label>
        </div>
      </n-form>
      <template #footer>
        <div class="row"><span class="spacer" /><n-button @click="show = false">取消</n-button><n-button type="primary" :disabled="!form.name.trim()" @click="save">保存</n-button></div>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { NButton, NCheckbox, NForm, NFormItem, NInput, NInputNumber, NModal, NTag } from 'naive-ui'
import { AudioLines, Film, Image as ImageIcon, MessageSquare, Pencil, Plus, Trash2, UsersRound } from 'lucide-vue-next'
import EmptyState from '../EmptyState.vue'
import ModelSelect from '../ModelSelect.vue'
import { api, confirmDialog, toast } from '../../api'
import { loadProviders, loadSettings, store } from '../../store'

const emit = defineEmits(['changed'])
const KINDS = [
  { key: 'chat', label: '对话', icon: MessageSquare },
  { key: 'image', label: '图像', icon: ImageIcon },
  { key: 'video', label: '视频', icon: Film },
  { key: 'tts', label: '语音', icon: AudioLines },
]
const QUOTAS = [
  { key: 'chat_daily', label: '每日对话条数', short: '对话/日', step: 10 },
  { key: 'image_daily', label: '每日图片张数', short: '图片/日', step: 10 },
  { key: 'video_daily', label: '每日视频个数', short: '视频/日', step: 1 },
  { key: 'tts_daily', label: '每日语音条数', short: '语音/日', step: 10 },
  { key: 'tokens_monthly', label: '每月 Token 数', short: 'Token/月', step: 100000 },
]

const groups = ref([])
const loaded = ref(false)
const show = ref(false)
const settings = reactive({ default_group_id: null })
const form = reactive({ id: null, name: '', description: '', kinds: [], models: {}, quotas: {} })

async function load() {
  groups.value = await api.get('/api/groups')
  loaded.value = true
  emit('changed', groups.value)
}

function edit(g) {
  Object.assign(form, g
    ? JSON.parse(JSON.stringify({ id: g.id, name: g.name, description: g.description, kinds: g.kinds, models: g.models, quotas: g.quotas }))
    : { id: null, name: '', description: '', kinds: ['chat', 'image', 'video', 'tts'], models: {}, quotas: {} })
  for (const k of KINDS) form.models[k.key] = form.models[k.key] || []
  show.value = true
}

function toggleKind(key, on) {
  form.kinds = on ? [...new Set([...form.kinds, key])] : form.kinds.filter((k) => k !== key)
}

async function save() {
  const quotas = Object.fromEntries(Object.entries(form.quotas).filter(([, v]) => v))
  const body = { name: form.name.trim(), description: form.description, kinds: form.kinds, models: form.models, quotas }
  if (form.id) await api.put(`/api/groups/${form.id}`, body)
  else await api.post('/api/groups', body)
  show.value = false
  toast('已保存', 'success')
  load()
}

async function remove(g) {
  if (!(await confirmDialog({ title: '删除用户组', content: `删除「${g.name}」后，组内 ${g.members} 名用户将不再受限制。`, positiveText: '删除' }))) return
  await api.del(`/api/groups/${g.id}`)
  if (settings.default_group_id === g.id) settings.default_group_id = null
  load()
}

async function setDefault(id) {
  store.settings = await api.put('/api/settings', { default_group_id: id })
  settings.default_group_id = id
  toast(id ? '新注册的用户将自动加入该组' : '已取消默认用户组', 'success')
}

onMounted(async () => {
  await loadProviders()
  const s = await loadSettings(true)
  settings.default_group_id = s.default_group_id ?? null
  load()
})
defineExpose({ load })
</script>

<style scoped>
.head { margin-bottom: 14px; align-items: flex-start; gap: 16px; }
.desc { font-size: 13px; line-height: 1.6; max-width: 720px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.card { padding: 14px 16px; border-radius: 14px; background: var(--panel); border: 1px solid var(--border); display: flex; flex-direction: column; gap: 10px; }
.card-head { display: flex; align-items: center; gap: 8px; min-width: 0; font-size: 15px; }
.small { font-size: 12.5px; }
.kinds { display: flex; flex-wrap: wrap; gap: 6px; }
.kind { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; padding: 3px 8px; border-radius: 8px; background: color-mix(in srgb, var(--primary) 10%, transparent); color: var(--primary); }
.kind.off { background: var(--panel-2); color: var(--muted); text-decoration: line-through; }
.quotas { display: flex; flex-wrap: wrap; gap: 6px 12px; font-size: 12.5px; color: var(--text-2); }
.actions { gap: 4px; }
.kind-row { display: grid; grid-template-columns: 110px minmax(0, 1fr); align-items: center; gap: 10px; margin-bottom: 8px; }
.kind-label { display: inline-flex; align-items: center; gap: 5px; }
.kind-models { min-width: 0; }
.quota-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px 14px; }
.quota-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; color: var(--text-2); }
</style>
