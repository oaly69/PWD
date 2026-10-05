<template>
  <div class="page settings">
    <div class="page-head"><div><h1>{{ admin ? '系统设置' : '个人设置' }}</h1><div class="sub">PWD v{{ store.site.version }}</div></div></div>

    <n-tabs v-model:value="tab" type="line" :placement="isMobile ? 'top' : 'left'" class="tabs">
      <n-tab-pane v-if="admin" name="general" tab="通用">
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

      <n-tab-pane v-if="admin" name="models" tab="默认模型">
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

      <n-tab-pane v-if="admin" name="security" tab="登录与服务">
        <section class="sec">
          <h3>故障切换</h3>
          <div class="switch-row">
            <div>
              <div>请求失败时自动切换服务</div>
              <p class="muted desc" style="margin: 2px 0 0">遇到网络错误、限流（429）或服务端错误（5xx）时，自动改用提供<b>同名模型</b>的其他已启用服务；按服务的「优先级」从高到低尝试。</p>
            </div>
            <n-switch v-model:value="sec.failover_enabled" />
          </div>
        </section>
        <section class="sec">
          <h3>单点登录（OIDC）</h3>
          <p class="muted desc">支持 Authentik、Keycloak、Logto、Casdoor、Authelia 等标准 OIDC 服务。在身份服务中创建应用时，回调地址填写：<code>{{ callbackUrl }}</code></p>
          <div class="switch-row"><div>启用单点登录</div><n-switch v-model:value="sec.oidc_enabled" /></div>
          <n-form label-placement="top" class="oidc-form" :disabled="!sec.oidc_enabled">
            <n-form-item label="Issuer 地址"><n-input v-model:value="sec.oidc_issuer" placeholder="https://auth.example.com/application/o/pwd/" /></n-form-item>
            <div class="row2">
              <n-form-item label="Client ID"><n-input v-model:value="sec.oidc_client_id" /></n-form-item>
              <n-form-item label="Client Secret">
                <n-input v-model:value="sec.oidc_client_secret" type="password" show-password-on="click" :placeholder="secretSet ? '已设置，留空保持不变' : '公开客户端可留空'" />
              </n-form-item>
            </div>
            <div class="row2">
              <n-form-item label="Scopes"><n-input v-model:value="sec.oidc_scopes" /></n-form-item>
              <n-form-item label="登录按钮文字"><n-input v-model:value="sec.oidc_button_text" /></n-form-item>
            </div>
            <n-form-item label="站点对外地址（可选）">
              <n-input v-model:value="sec.public_url" placeholder="例如 https://pwd.example.com，反向代理时用于生成正确的回调地址" />
            </n-form-item>
            <n-checkbox v-model:checked="sec.oidc_auto_create">首次单点登录时自动创建账号（是否需要审核沿用「用户管理」中的注册审核设置）</n-checkbox>
          </n-form>
        </section>
        <n-button type="primary" :loading="saving" @click="saveSecurity">保存</n-button>
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
          <p class="muted desc" style="margin-top: 12px">当前账号：{{ store.user?.username }}（{{ admin ? '管理员' : '普通用户' }}）。修改密码后，其他设备上的登录会立即失效。</p>
        </section>

        <section class="sec">
          <h3>两步验证 <n-tag v-if="store.user?.totp_enabled" size="small" type="success" :bordered="false">已开启</n-tag></h3>
          <template v-if="store.user?.totp_enabled">
            <p class="muted desc">登录时除密码外还需输入验证器 App 中的 6 位验证码。</p>
            <div class="row" style="max-width: 420px">
              <n-input v-model:value="disablePwd" type="password" show-password-on="click" placeholder="输入密码以关闭" />
              <n-button secondary type="error" :disabled="!disablePwd" @click="disable2fa">关闭两步验证</n-button>
            </div>
          </template>
          <template v-else-if="totp">
            <div class="totp">
              <img :src="totp.qr" alt="二维码" />
              <div class="totp-steps">
                <p>1. 用 Google Authenticator、Microsoft Authenticator、1Password 等 App 扫描二维码；无法扫码时手动输入密钥：</p>
                <code class="secret">{{ totp.secret }}</code>
                <p>2. 输入 App 中显示的 6 位验证码完成开启：</p>
                <div class="row">
                  <n-input v-model:value="totpCode" maxlength="6" placeholder="6 位验证码" style="width: 140px" @keydown.enter="enable2fa" />
                  <n-button type="primary" :disabled="totpCode.length !== 6" @click="enable2fa">开启</n-button>
                  <n-button quaternary @click="totp = null">取消</n-button>
                </div>
              </div>
            </div>
          </template>
          <template v-else>
            <p class="muted desc">开启后即使密码泄露，他人也无法登录你的账号。</p>
            <n-button secondary @click="setup2fa"><template #icon><ShieldCheck :size="16" /></template>设置两步验证</n-button>
          </template>
        </section>

        <section v-if="store.site.oidc_enabled" class="sec">
          <h3>单点登录 <n-tag v-if="store.user?.oidc_linked" size="small" type="success" :bordered="false">已绑定</n-tag></h3>
          <p class="muted desc">绑定后可直接使用「{{ store.site.oidc_button_text }}」登录本账号。</p>
          <n-button v-if="store.user?.oidc_linked" secondary @click="unlinkSso">解除绑定</n-button>
          <n-button v-else secondary tag="a" href="/api/auth/oidc/login?link=true">绑定单点登录账号</n-button>
        </section>
      </n-tab-pane>

      <n-tab-pane name="usage" tab="我的用量">
        <section v-if="usage" class="sec">
          <h3>今日用量</h3>
          <p class="muted desc">
            <template v-if="usage.group">所在用户组：<b>{{ usage.group.name }}</b>。</template>
            <template v-else>{{ admin ? '管理员不受用量限制。' : '你的账号不受用量限制。' }}</template>
            每日额度在当天 0 点重置。
          </p>
          <div class="usage-grid">
            <div v-for="k in USAGE_ITEMS" :key="k.key" class="usage-item" :class="{ off: usage.group && !usage.group.kinds.includes(k.kind) }">
              <div class="ui-head"><component :is="k.icon" :size="15" />{{ k.label }}<span class="spacer" /><span v-if="usage.group && !usage.group.kinds.includes(k.kind)" class="muted">无权限</span></div>
              <div class="ui-num">{{ k.used(usage) }}<span class="muted"> / {{ usage.quotas[k.key] ? usage.quotas[k.key].toLocaleString() : '不限' }}</span></div>
              <n-progress v-if="usage.quotas[k.key]" type="line" :percentage="Math.min(100, Math.round((k.used(usage) / usage.quotas[k.key]) * 100))" :show-indicator="false" :status="k.used(usage) >= usage.quotas[k.key] ? 'error' : 'default'" />
            </div>
          </div>
        </section>
      </n-tab-pane>

      <n-tab-pane v-if="admin" name="data" tab="数据与备份">
        <section class="sec">
          <h3>全站概览</h3>
          <div v-if="stats?.site" class="stat-grid">
            <div class="stat"><b>{{ stats.site.users }}</b><span>用户</span></div>
            <div class="stat"><b>{{ stats.site.assets }}</b><span>作品</span></div>
            <div class="stat"><b>{{ stats.site.messages }}</b><span>对话消息</span></div>
            <div class="stat"><b>{{ formatBytes(stats.site.storage_bytes) }}</b><span>媒体占用</span></div>
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
import { NButton, NCheckbox, NForm, NFormItem, NInput, NProgress, NSwitch, NTabPane, NTabs, NTag } from 'naive-ui'
import { AudioLines, Check, Coins, Download, Film, Image as ImageIcon, MessageSquare, ShieldCheck } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
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

const USAGE_ITEMS = [
  { key: 'chat_daily', kind: 'chat', label: '对话', icon: MessageSquare, used: (u) => u.usage.today.chat },
  { key: 'image_daily', kind: 'image', label: '图片', icon: ImageIcon, used: (u) => u.usage.today.image },
  { key: 'video_daily', kind: 'video', label: '视频', icon: Film, used: (u) => u.usage.today.video },
  { key: 'tts_daily', kind: 'tts', label: '语音', icon: AudioLines, used: (u) => u.usage.today.tts },
  { key: 'tokens_monthly', kind: 'chat', label: '本月 Token', icon: Coins, used: (u) => u.usage.tokens_month },
]
const SEC_KEYS = ['failover_enabled', 'oidc_enabled', 'oidc_issuer', 'oidc_client_id', 'oidc_scopes', 'oidc_button_text', 'oidc_auto_create', 'public_url']

const route = useRoute()
const router = useRouter()
const admin = computed(() => !!store.user?.is_admin)
const tab = ref(admin.value ? 'general' : 'appearance')
const sec = reactive({ failover_enabled: true, oidc_enabled: false, oidc_issuer: '', oidc_client_id: '', oidc_client_secret: '', oidc_scopes: '', oidc_button_text: '', oidc_auto_create: true, public_url: '' })
const secretSet = ref(false)
const callbackUrl = computed(() => `${(sec.public_url || location.origin).replace(/\/$/, '')}/api/auth/oidc/callback`)
const totp = ref(null)
const totpCode = ref('')
const disablePwd = ref('')
const usage = ref(null)
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
  for (const k of SEC_KEYS) sec[k] = data[k]
  sec.oidc_client_secret = ''
  secretSet.value = !!data.oidc_client_secret_set
}

async function saveSecurity() {
  const body = Object.fromEntries(SEC_KEYS.map((k) => [k, sec[k]]))
  if (sec.oidc_client_secret) body.oidc_client_secret = sec.oidc_client_secret
  if (sec.oidc_enabled && (!sec.oidc_issuer || !sec.oidc_client_id)) return toast('请填写 Issuer 地址和 Client ID', 'warning')
  saving.value = true
  try {
    store.settings = await api.put('/api/settings', body)
    secretSet.value = !!store.settings.oidc_client_secret_set
    sec.oidc_client_secret = ''
    await loadSite()
    toast('设置已保存', 'success')
  } finally {
    saving.value = false
  }
}

async function refreshMe() {
  store.user = await api.get('/api/auth/me')
}

async function setup2fa() {
  const r = await api.post('/api/auth/2fa/setup')
  const QRCode = await import('qrcode')
  totp.value = { ...r, qr: await QRCode.toDataURL(r.uri, { width: 200, margin: 1 }) }
  totpCode.value = ''
}

async function enable2fa() {
  if (totpCode.value.length !== 6) return
  await api.post('/api/auth/2fa/enable', { secret: totp.value.secret, code: totpCode.value })
  totp.value = null
  await refreshMe()
  toast('两步验证已开启', 'success')
}

async function disable2fa() {
  await api.post('/api/auth/2fa/disable', { password: disablePwd.value })
  disablePwd.value = ''
  await refreshMe()
  toast('两步验证已关闭', 'success')
}

async function unlinkSso() {
  await api.post('/api/auth/oidc/unlink')
  await refreshMe()
  toast('已解除绑定', 'success')
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
  if (route.query.sso) {
    tab.value = 'account'
    if (route.query.sso === 'linked') toast('单点登录账号已绑定', 'success')
    else if (route.query.sso === 'taken') toast('该单点登录账号已绑定了其他用户', 'error')
    router.replace('/settings')
    refreshMe()
  }
  api.get('/api/usage/me').then((u) => { usage.value = u }).catch(() => null)
  if (!admin.value) return
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
.switch-row { display: flex; align-items: center; justify-content: space-between; gap: 20px; max-width: 640px; padding: 10px 0; }
.oidc-form { max-width: 640px; margin-top: 6px; }
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }
.totp { display: flex; gap: 20px; align-items: flex-start; flex-wrap: wrap; }
.totp img { width: 180px; height: 180px; border-radius: 12px; border: 1px solid var(--border); background: #fff; padding: 6px; }
.totp-steps { flex: 1; min-width: 260px; font-size: 13.5px; }
.totp-steps p { margin: 0 0 8px; }
.secret { display: inline-block; margin-bottom: 14px; padding: 6px 10px; border-radius: 8px; background: var(--panel-2); letter-spacing: 1px; word-break: break-all; }
.usage-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; max-width: 820px; }
.usage-item { padding: 14px; border-radius: 12px; background: var(--panel); border: 1px solid var(--border); display: flex; flex-direction: column; gap: 6px; }
.usage-item.off { opacity: .55; }
.ui-head { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-2); }
.ui-num { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
.ui-num .muted { font-size: 13px; font-weight: 400; }
.about { display: flex; gap: 18px; align-items: center; }
.about img { width: 64px; height: 64px; }
@media (max-width: 760px) { .tabs :deep(.n-tab-pane) { padding-left: 0; padding-top: 12px; } }
</style>
