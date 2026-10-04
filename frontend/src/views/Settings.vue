<template>
  <div class="page settings">
    <div class="page-head"><div><h1>系统设置</h1><div class="sub">PWD v{{ store.site.version }}</div></div></div>

    <n-tabs type="line" :placement="isMobile ? 'top' : 'left'" class="tabs" default-value="general">
      <n-tab-pane name="general" tab="通用">
        <section class="sec">
          <h3>站点</h3>
          <div class="field-label">站点名称</div>
          <n-input v-model:value="s.site_name" maxlength="64" style="max-width: 360px" />
        </section>
        <section class="sec">
          <h3>新对话默认角色设定</h3>
          <n-input v-model:value="s.default_system_prompt" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" placeholder="留空表示不设置" />
        </section>
        <n-button type="primary" :loading="saving" @click="save">保存</n-button>
      </n-tab-pane>

      <n-tab-pane name="models" tab="默认模型">
        <section class="sec">
          <h3>默认模型</h3>
          <p class="muted desc">新建对话和打开创作页时默认选中的模型。</p>
          <div class="model-rows">
            <div v-for="k in KINDS" :key="k.kind" class="model-row">
              <div class="mr-label"><component :is="k.icon" :size="16" />{{ k.label }}</div>
              <ModelSelect v-model="keys[k.kind]" :kind="k.kind" placeholder="不设置" />
            </div>
          </div>
        </section>
        <section class="sec">
          <h3>提示词优化模型</h3>
          <p class="muted desc">图像 / 视频页面「AI 优化」按钮使用的对话模型，留空则使用默认对话模型。</p>
          <ModelSelect v-model="keys.enhance" kind="chat" placeholder="使用默认对话模型" style="max-width: 420px" />
        </section>
        <n-button type="primary" :loading="saving" @click="save">保存</n-button>
      </n-tab-pane>

      <n-tab-pane name="appearance" tab="外观">
        <section class="sec">
          <h3>主题</h3>
          <div class="theme-cards">
            <button v-for="t in THEMES" :key="t.value" class="theme-card" :class="{ active: themeMode === t.value }" @click="setThemeMode(t.value)">
              <div class="preview" :class="t.value"><span /><span /><span /></div>
              <div>{{ t.label }}</div>
            </button>
          </div>
        </section>
        <section class="sec">
          <h3>主题色</h3>
          <div class="accents">
            <button v-for="(a, key) in ACCENTS" :key="key" class="accent" :class="{ active: accent === key }" :style="{ '--c': a.light }" @click="setAccent(key)">
              <span class="dot"><Check v-if="accent === key" :size="14" /></span>{{ a.name }}
            </button>
          </div>
          <p class="muted desc">外观设置保存在当前浏览器中。</p>
        </section>
      </n-tab-pane>

      <n-tab-pane name="account" tab="账号安全">
        <section class="sec">
          <h3>修改密码</h3>
          <n-form label-placement="top" style="max-width: 420px">
            <n-form-item label="原密码"><n-input v-model:value="pwd.old_password" type="password" show-password-on="click" /></n-form-item>
            <n-form-item label="新密码（至少 8 位）"><n-input v-model:value="pwd.new_password" type="password" show-password-on="click" /></n-form-item>
            <n-form-item label="确认新密码"><n-input v-model:value="pwd.confirm" type="password" show-password-on="click" /></n-form-item>
            <n-button type="primary" :disabled="!pwd.old_password || pwd.new_password.length < 8" @click="changePassword">修改密码</n-button>
          </n-form>
          <p class="muted desc">修改密码后，其他设备上的登录会立即失效。</p>
        </section>
      </n-tab-pane>

      <n-tab-pane name="data" tab="数据与备份">
        <section class="sec">
          <h3>存储概览</h3>
          <div v-if="stats" class="stat-grid">
            <div class="stat"><b>{{ stats.images }}</b><span>图片</span></div>
            <div class="stat"><b>{{ stats.videos }}</b><span>视频</span></div>
            <div class="stat"><b>{{ stats.audios }}</b><span>音频</span></div>
            <div class="stat"><b>{{ stats.conversations }}</b><span>对话</span></div>
            <div class="stat"><b>{{ formatBytes(stats.storage_bytes) }}</b><span>媒体占用</span></div>
          </div>
        </section>
        <section class="sec">
          <h3>备份</h3>
          <p class="muted desc">导出包含数据库快照、会话密钥与全部媒体文件的 zip。恢复时停止容器，把 zip 解压到数据目录（/data）后重新启动即可。</p>
          <div class="row">
            <n-button type="primary" @click="downloadUrl('/api/system/backup')"><template #icon><Download :size="16" /></template>完整备份</n-button>
            <n-button secondary @click="downloadUrl('/api/system/backup?include_media=false')">仅备份数据库</n-button>
          </div>
        </section>
      </n-tab-pane>

      <n-tab-pane name="about" tab="关于">
        <section class="sec about">
          <img src="/favicon.svg" alt="" />
          <div>
            <h3 style="margin: 0">PWD · 个人 AIGC 创作平台</h3>
            <p class="muted">版本 {{ store.site.version }}</p>
            <div class="row">
              <a href="https://github.com/oaly69/PWD" target="_blank">GitHub</a>
              <span class="muted">·</span>
              <a href="/api/docs" target="_blank">API 文档</a>
            </div>
          </div>
        </section>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { NButton, NForm, NFormItem, NInput, NTabPane, NTabs } from 'naive-ui'
import { AudioLines, Check, Download, Film, Image as ImageIcon, MessageSquare } from 'lucide-vue-next'
import ModelSelect from '../components/ModelSelect.vue'
import { api, loadSite, toast } from '../api'
import { loadSettings, splitModelKey, store } from '../store'
import { ACCENTS, accent, setAccent, setThemeMode, themeMode } from '../composables/theme'
import { downloadUrl, formatBytes } from '../utils/format'

const KINDS = [
  { kind: 'chat', label: '对话', icon: MessageSquare },
  { kind: 'image', label: '图像', icon: ImageIcon },
  { kind: 'video', label: '视频', icon: Film },
  { kind: 'tts', label: '语音', icon: AudioLines },
]
const THEMES = [
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
  { value: 'system', label: '跟随系统' },
]

const s = reactive({ site_name: '', default_system_prompt: '' })
const keys = reactive({ chat: '', image: '', video: '', tts: '', enhance: '' })
const pwd = reactive({ old_password: '', new_password: '', confirm: '' })
const stats = ref(null)
const saving = ref(false)
const width = ref(window.innerWidth)
const isMobile = computed(() => width.value < 760)
const onResize = () => { width.value = window.innerWidth }

const keyOf = (pid, model) => (pid && model ? `${pid}::${model}` : '')

async function load() {
  const data = await loadSettings(true)
  Object.assign(s, { site_name: data.site_name, default_system_prompt: data.default_system_prompt || '' })
  for (const k of KINDS) keys[k.kind] = keyOf(data[`default_${k.kind}_provider_id`], data[`default_${k.kind}_model`])
  keys.enhance = keyOf(data.enhance_provider_id, data.enhance_model)
}

async function save() {
  const body = { ...s }
  for (const k of KINDS) {
    const [pid, model] = splitModelKey(keys[k.kind])
    body[`default_${k.kind}_provider_id`] = pid
    body[`default_${k.kind}_model`] = model
  }
  const [epid, emodel] = splitModelKey(keys.enhance)
  body.enhance_provider_id = epid
  body.enhance_model = emodel
  saving.value = true
  try {
    store.settings = await api.put('/api/settings', body)
    await loadSite()
    toast('设置已保存', 'success')
  } finally {
    saving.value = false
  }
}

async function changePassword() {
  if (pwd.new_password !== pwd.confirm) return toast('两次输入的新密码不一致', 'error')
  await api.post('/api/auth/password', { old_password: pwd.old_password, new_password: pwd.new_password })
  Object.assign(pwd, { old_password: '', new_password: '', confirm: '' })
  toast('密码已修改', 'success')
}

onMounted(async () => {
  window.addEventListener('resize', onResize)
  await load()
  stats.value = await api.get('/api/stats')
})
onUnmounted(() => window.removeEventListener('resize', onResize))
</script>

<style scoped>
.settings { max-width: 1080px; }
.tabs :deep(.n-tabs-nav) { min-width: 150px; }
.tabs :deep(.n-tab-pane) { padding-left: 32px; }
.sec { margin-bottom: 28px; }
.sec h3 { margin: 0 0 12px; font-size: 16px; }
.desc { font-size: 13px; margin: -4px 0 12px; line-height: 1.6; }
.model-rows { display: flex; flex-direction: column; gap: 10px; max-width: 560px; }
.model-row { display: grid; grid-template-columns: 90px 1fr; align-items: center; gap: 12px; }
.mr-label { display: flex; align-items: center; gap: 8px; font-weight: 500; }
.theme-cards { display: flex; gap: 14px; flex-wrap: wrap; }
.theme-card { border: 2px solid var(--border); background: var(--panel); border-radius: 12px; padding: 8px 8px 10px; cursor: pointer; color: var(--text); font-size: 13px; display: flex; flex-direction: column; gap: 8px; align-items: center; }
.theme-card.active { border-color: var(--primary); }
.preview { width: 132px; height: 82px; border-radius: 8px; display: grid; grid-template-columns: 30px 1fr; grid-template-rows: 18px 1fr; gap: 4px; padding: 6px; }
.preview.light { background: #f3f3f7; }
.preview.dark { background: #16161b; }
.preview.system { background: linear-gradient(135deg, #f3f3f7 50%, #16161b 50%); }
.preview span { border-radius: 4px; background: color-mix(in srgb, var(--primary) 60%, #999); opacity: .55; }
.preview span:first-child { grid-row: span 2; }
.accents { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
.accent { display: flex; align-items: center; gap: 8px; padding: 6px 14px 6px 6px; border-radius: 20px; border: 1px solid var(--border); background: var(--panel); color: var(--text); cursor: pointer; }
.accent.active { border-color: var(--c); }
.dot { width: 22px; height: 22px; border-radius: 50%; background: var(--c); color: #fff; display: grid; place-items: center; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 10px; }
.stat { padding: 14px; border-radius: 12px; background: var(--panel); border: 1px solid var(--border); display: flex; flex-direction: column; gap: 2px; }
.stat b { font-size: 20px; }
.stat span { color: var(--muted); font-size: 12px; }
.about { display: flex; gap: 18px; align-items: center; }
.about img { width: 64px; height: 64px; }
@media (max-width: 760px) { .tabs :deep(.n-tab-pane) { padding-left: 0; padding-top: 12px; } }
</style>
