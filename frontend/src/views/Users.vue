<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>用户管理</h1>
        <div class="sub">共 {{ users.length }} 个用户<template v-if="pendingCount"> · <b class="pending">{{ pendingCount }} 个待审核</b></template></div>
      </div>
      <span class="spacer" />
      <n-input v-model:value="q" clearable placeholder="搜索用户名" style="width: 200px">
        <template #prefix><Search :size="14" /></template>
      </n-input>
      <n-button type="primary" @click="openCreate"><template #icon><UserPlus :size="16" /></template>添加用户</n-button>
    </div>

    <div class="reg-card">
      <div class="reg-item">
        <div>
          <div class="reg-title">开放注册</div>
          <div class="muted reg-desc">开启后登录页会出现「注册」入口，任何人都可以自行注册账号</div>
        </div>
        <n-switch :value="reg.allow_register" @update:value="(v) => saveReg({ allow_register: v })" />
      </div>
      <div class="reg-item" :class="{ disabled: !reg.allow_register }">
        <div>
          <div class="reg-title">注册需要审核</div>
          <div class="muted reg-desc">新注册的用户需要管理员在此页面通过审核后才能登录</div>
        </div>
        <n-switch :value="reg.register_need_approval" :disabled="!reg.allow_register" @update:value="(v) => saveReg({ register_need_approval: v })" />
      </div>
    </div>

    <n-data-table :columns="columns" :data="filtered" :loading="loading" :bordered="false" :row-key="(r) => r.id" :scroll-x="900" class="table" />

    <n-modal v-model:show="showCreate" preset="card" title="添加用户" style="width: min(440px, 94vw)">
      <n-form label-placement="top">
        <n-form-item label="用户名"><n-input v-model:value="form.username" placeholder="2～32 位，字母、数字、下划线或中文" /></n-form-item>
        <n-form-item label="初始密码"><n-input v-model:value="form.password" type="password" show-password-on="click" placeholder="至少 8 位" /></n-form-item>
        <n-form-item label="角色">
          <n-radio-group v-model:value="form.role">
            <n-radio-button value="user">普通用户</n-radio-button>
            <n-radio-button value="admin">管理员</n-radio-button>
          </n-radio-group>
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="row"><span class="spacer" /><n-button @click="showCreate = false">取消</n-button><n-button type="primary" :disabled="!form.username || form.password.length < 8" @click="create">创建</n-button></div>
      </template>
    </n-modal>

    <n-modal v-model:show="showReset" preset="card" :title="`重置 ${resetUser?.username} 的密码`" style="width: min(420px, 94vw)">
      <n-input v-model:value="newPassword" type="password" show-password-on="click" placeholder="新密码，至少 8 位" />
      <div class="muted hint">重置后该用户在所有设备上的登录都会失效。</div>
      <template #footer>
        <div class="row"><span class="spacer" /><n-button @click="showReset = false">取消</n-button><n-button type="primary" :disabled="newPassword.length < 8" @click="doReset">确定重置</n-button></div>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, h, onMounted, reactive, ref } from 'vue'
import { NButton, NDataTable, NDropdown, NForm, NFormItem, NInput, NModal, NRadioButton, NRadioGroup, NSwitch, NTag } from 'naive-ui'
import { Ellipsis, Search, UserPlus } from 'lucide-vue-next'
import { api, confirmDialog, toast } from '../api'
import { loadSettings, store } from '../store'
import { formatBytes, relativeTime } from '../utils/format'

const STATUS = { active: ['正常', 'success'], pending: ['待审核', 'warning'], disabled: ['已禁用', 'error'] }

const users = ref([])
const loading = ref(false)
const q = ref('')
const reg = reactive({ allow_register: false, register_need_approval: true })
const showCreate = ref(false)
const form = reactive({ username: '', password: '', role: 'user' })
const showReset = ref(false)
const resetUser = ref(null)
const newPassword = ref('')

const pendingCount = computed(() => users.value.filter((u) => u.status === 'pending').length)
const filtered = computed(() => {
  const k = q.value.trim().toLowerCase()
  // 待审核的用户排在最前
  return users.value
    .filter((u) => !k || u.username.toLowerCase().includes(k))
    .sort((a, b) => (a.status === 'pending' ? -1 : 0) - (b.status === 'pending' ? -1 : 0) || a.id - b.id)
})

const columns = [
  {
    title: '用户',
    key: 'username',
    minWidth: 180,
    render: (u) => h('div', { class: 'user-cell' }, [
      h('span', { class: 'avatar' }, u.username.slice(0, 1).toUpperCase()),
      h('div', [
        h('div', { class: 'uname' }, [u.username, u.id === store.user?.id ? h('span', { class: 'me' }, '（我）') : null]),
        h('div', { class: 'muted small' }, `注册于 ${new Date(u.created_at).toLocaleDateString('zh-CN')}`),
      ]),
    ]),
  },
  {
    title: '角色',
    key: 'role',
    width: 100,
    render: (u) => h(NTag, { size: 'small', bordered: false, type: u.is_admin ? 'primary' : 'default' }, () => (u.is_admin ? '管理员' : '普通用户')),
  },
  {
    title: '状态',
    key: 'status',
    width: 90,
    render: (u) => h(NTag, { size: 'small', bordered: false, type: STATUS[u.status][1] }, () => STATUS[u.status][0]),
  },
  { title: '对话', key: 'conversations', width: 70 },
  { title: '作品', key: 'assets', width: 70 },
  { title: '存储', key: 'storage_bytes', width: 90, render: (u) => formatBytes(u.storage_bytes) },
  { title: '最近登录', key: 'last_login_at', width: 110, render: (u) => (u.last_login_at ? relativeTime(u.last_login_at) : '从未') },
  {
    title: '操作',
    key: 'actions',
    width: 170,
    render: (u) => h('div', { class: 'ops' }, [
      u.status === 'pending'
        ? h(NButton, { size: 'small', type: 'primary', secondary: true, onClick: () => patch(u, { status: 'active' }, '已通过审核') }, () => '通过')
        : null,
      h(NDropdown, { trigger: 'click', options: menu(u), onSelect: (k) => onMenu(k, u) }, () =>
        h(NButton, { size: 'small', quaternary: true }, { icon: () => h(Ellipsis, { size: 16 }) })),
    ]),
  },
]

function menu(u) {
  const self = u.id === store.user?.id
  return [
    { label: u.is_admin ? '设为普通用户' : '设为管理员', key: 'role', disabled: self },
    u.status === 'disabled'
      ? { label: '启用账号', key: 'enable' }
      : { label: '禁用账号', key: 'disable', disabled: self },
    { label: '重置密码', key: 'reset' },
    { type: 'divider', key: 'd' },
    { label: '删除用户', key: 'delete', disabled: self },
  ]
}

async function onMenu(key, u) {
  if (key === 'role') await patch(u, { role: u.is_admin ? 'user' : 'admin' }, '角色已更新')
  else if (key === 'enable') await patch(u, { status: 'active' }, '已启用')
  else if (key === 'disable') {
    if (await confirmDialog({ title: '禁用账号', content: `禁用后「${u.username}」将无法登录，已登录的会话会立即失效。`, positiveText: '禁用' })) {
      await patch(u, { status: 'disabled' }, '已禁用')
    }
  } else if (key === 'reset') {
    resetUser.value = u
    newPassword.value = ''
    showReset.value = true
  } else if (key === 'delete') {
    const ok = await confirmDialog({
      title: '删除用户',
      content: `将永久删除「${u.username}」以及其全部对话、作品文件和个人提示词（${u.assets} 个作品，${formatBytes(u.storage_bytes)}），无法恢复。`,
      positiveText: '永久删除',
      type: 'error',
    })
    if (!ok) return
    await api.del(`/api/users/${u.id}`)
    toast('已删除', 'success')
    load()
  }
}

async function patch(u, body, msg) {
  await api.patch(`/api/users/${u.id}`, body)
  toast(msg, 'success')
  load()
}

async function doReset() {
  await api.patch(`/api/users/${resetUser.value.id}`, { password: newPassword.value })
  showReset.value = false
  toast('密码已重置', 'success')
}

function openCreate() {
  Object.assign(form, { username: '', password: '', role: 'user' })
  showCreate.value = true
}

async function create() {
  await api.post('/api/users', { ...form })
  showCreate.value = false
  toast('用户已创建', 'success')
  load()
}

async function saveReg(patchBody) {
  store.settings = await api.put('/api/settings', patchBody)
  Object.assign(reg, { allow_register: store.settings.allow_register, register_need_approval: store.settings.register_need_approval })
  toast('已保存', 'success')
}

async function load() {
  loading.value = true
  try {
    users.value = await api.get('/api/users')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const s = await loadSettings(true)
  Object.assign(reg, { allow_register: !!s.allow_register, register_need_approval: s.register_need_approval !== false })
  load()
})
</script>

<style scoped>
.pending { color: var(--warning); }
.reg-card { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; margin-bottom: 18px; }
.reg-item { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 18px; background: var(--panel); }
.reg-item.disabled { opacity: .55; }
.reg-title { font-weight: 600; }
.reg-desc { font-size: 12.5px; margin-top: 2px; }
.table { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }
.table :deep(.user-cell) { display: flex; align-items: center; gap: 10px; }
.table :deep(.avatar) { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: linear-gradient(135deg, var(--primary), color-mix(in srgb, var(--primary) 55%, #ff7ac6)); color: #fff; font-weight: 700; font-size: 13px; flex-shrink: 0; }
.table :deep(.uname) { font-weight: 600; }
.table :deep(.me) { color: var(--muted); font-weight: 400; font-size: 12px; }
.table :deep(.small) { font-size: 12px; }
.table :deep(.ops) { display: flex; gap: 6px; align-items: center; }
.hint { font-size: 12px; margin-top: 8px; }
@media (max-width: 760px) { .reg-card { grid-template-columns: 1fr; } }
</style>
