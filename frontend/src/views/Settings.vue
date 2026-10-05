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
          <h3>语音输入（语音识别）</h3>
          <p class="muted desc">对话输入框的麦克风按钮使用的模型（OpenAI 兼容 /audio/transcriptions，如 whisper-1、FunAudioLLM/SenseVoiceSmall）。留空则不显示语音输入。</p>
          <ModelSelect v-model="keys.stt" kind="stt" placeholder="不启用" style="max-width: 420px" />
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

      <n-tab-pane v-if="admin" name="tools" tab="搜索与工具">
        <section class="sec">
          <h3>联网搜索</h3>
          <p class="muted desc">对话中开启「联网」后，会先搜索再回答并标注来源；也作为模型可调用的工具。</p>
          <n-form label-placement="top" style="max-width: 640px">
            <n-form-item label="搜索引擎">
              <n-radio-group v-model:value="search.search_engine">
                <n-radio-button value="">不启用</n-radio-button>
                <n-radio-button value="searxng">SearXNG（自建，免费）</n-radio-button>
                <n-radio-button value="tavily">Tavily</n-radio-button>
                <n-radio-button value="bocha">博查（国内）</n-radio-button>
              </n-radio-group>
            </n-form-item>
            <n-form-item v-if="search.search_engine === 'searxng'" label="SearXNG 地址">
              <div style="width: 100%">
                <n-input v-model:value="search.search_url" placeholder="http://searxng:8080" />
                <div class="muted small-hint">需要在 SearXNG 的 settings.yml 中 search.formats 加入 json</div>
              </div>
            </n-form-item>
            <n-form-item v-if="search.search_engine && search.search_engine !== 'searxng'" label="API Key">
              <n-input v-model:value="search.search_api_key" type="password" show-password-on="click" :placeholder="searchKeySet ? '已设置，留空保持不变' : ''" />
            </n-form-item>
            <n-form-item v-if="search.search_engine" label="每次返回结果数">
              <n-input-number v-model:value="search.search_max_results" :min="1" :max="20" style="width: 140px" />
            </n-form-item>
          </n-form>
        </section>
        <section class="sec">
          <h3>MCP 服务</h3>
          <p class="muted desc">接入支持 Streamable HTTP 的 MCP 服务后，其工具会出现在对话的「工具」列表中供模型调用（需要模型支持 Function Calling）。</p>
          <div v-for="(m, i) in mcp" :key="i" class="mcp-row">
            <n-switch v-model:value="m.enabled" size="small" />
            <n-input v-model:value="m.name" size="small" placeholder="名称" style="width: 140px" />
            <n-input v-model:value="m.url" size="small" placeholder="https://example.com/mcp" style="flex: 1" />
            <n-input v-model:value="m.headersText" size="small" placeholder='请求头 JSON，如 {"Authorization": "Bearer …"}' style="flex: 1" />
            <n-button size="small" secondary :loading="m.testing" @click="testMcp(m)">测试</n-button>
            <n-button size="small" quaternary type="error" @click="mcp.splice(i, 1)"><template #icon><Trash2 :size="14" /></template></n-button>
            <div v-if="m.result" class="mcp-result" :class="m.result.ok ? 'ok' : 'err'">
              {{ m.result.message }}<template v-if="m.result.tools?.length">：{{ m.result.tools.map((t) => t.name).join('、') }}</template>
            </div>
          </div>
          <n-button size="small" secondary @click="addMcp"><template #icon><Plus :size="14" /></template>添加 MCP 服务</n-button>
        </section>
        <n-button type="primary" :loading="saving" @click="saveTools">保存</n-button>
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
        <section v-if="storage" class="sec">
          <h3>媒体存储</h3>
          <template v-if="storage.backend === 's3'">
            <p class="muted desc">
              已启用对象存储：<code>{{ storage.endpoint }}/{{ storage.bucket }}/{{ storage.prefix }}</code>。新文件会在后台上传，本地保留 {{ storage.cache_days || '∞' }} 天缓存。
              <template v-if="storage.pending_uploads">当前有 {{ storage.pending_uploads }} 个文件正在上传。</template>
            </p>
            <n-button secondary :loading="syncing" @click="syncStorage">把本地已有文件同步到对象存储</n-button>
          </template>
          <p v-else class="muted desc">当前使用本地磁盘（数据目录下的 media）。如需使用 S3 / MinIO / R2 等对象存储，请设置 PWD_S3_* 环境变量后重启，详见 README。</p>
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
import { NButton, NCheckbox, NForm, NFormItem, NInput, NInputNumber, NProgress, NRadioButton, NRadioGroup, NSwitch, NTabPane, NTabs, NTag } from 'naive-ui'
import { AudioLines, Check, Coins, Download, Film, Image as ImageIcon, MessageSquare, Plus, ShieldCheck, Trash2 } from 'lucide-vue-next'
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
const storage = ref(null)
const syncing = ref(false)

async function syncStorage() {
  syncing.value = true
  try {
    const r = await api.post('/api/system/storage/sync')
    toast(`同步完成：上传 ${r.uploaded} 个，已存在 ${r.skipped} 个${r.failed ? `，失败 ${r.failed} 个` : ''}`, r.failed ? 'warning' : 'success')
  } finally {
    syncing.value = false
  }
}
const s = reactive({ site_name: '', default_system_prompt: '' })
const keys = reactive({ chat: '', image: '', video: '', tts: '', enhance: '', stt: '' })
const search = reactive({ search_engine: '', search_url: '', search_api_key: '', search_max_results: 5 })
const searchKeySet = ref(false)
const mcp = ref([])
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
  keys.stt = keyOf(data.stt_provider_id, data.stt_model)
  Object.assign(search, { search_engine: data.search_engine || '', search_url: data.search_url || '', search_api_key: '', search_max_results: data.search_max_results || 5 })
  searchKeySet.value = !!data.search_api_key_set
  mcp.value = (data.mcp_servers || []).map((m) => ({ ...m, headersText: Object.keys(m.headers || {}).length ? JSON.stringify(m.headers) : '', result: null, testing: false }))
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

function parseHeaders(m) {
  if (!m.headersText?.trim()) return {}
  const h = JSON.parse(m.headersText)
  if (typeof h !== 'object' || Array.isArray(h)) throw new Error('请求头必须是 JSON 对象')
  return h
}

function addMcp() {
  mcp.value.push({ id: Math.random().toString(36).slice(2, 8), name: '', url: '', headersText: '', enabled: true, result: null, testing: false })
}

async function testMcp(m) {
  let headers
  try { headers = parseHeaders(m) } catch (e) { return toast(`「${m.name || m.url}」${e.message}`, 'error') }
  m.testing = true
  try {
    m.result = await api.post('/api/tools/mcp/test', { url: m.url, headers })
  } finally {
    m.testing = false
  }
}

async function saveTools() {
  const servers = []
  for (const m of mcp.value) {
    if (!m.url.trim()) continue
    let headers
    try { headers = parseHeaders(m) } catch (e) { return toast(`「${m.name || m.url}」${e.message}`, 'error') }
    servers.push({ id: m.id, name: m.name.trim() || m.url, url: m.url.trim(), headers, enabled: m.enabled })
  }
  const body = { search_engine: search.search_engine, search_url: search.search_url, search_max_results: search.search_max_results, mcp_servers: servers }
  if (search.search_api_key) body.search_api_key = search.search_api_key
  saving.value = true
  try {
    store.settings = await api.put('/api/settings', body)
    searchKeySet.value = !!store.settings.search_api_key_set
    search.search_api_key = ''
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
  const [spid, smodel] = splitModelKey(keys.stt)
  body.stt_provider_id = spid
  body.stt_model = smodel
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
  storage.value = await api.get('/api/system/storage').catch(() => null)
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
.small-hint { font-size: 12px; margin-top: 4px; }
.mcp-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 10px; max-width: 900px; }
.mcp-result { width: 100%; font-size: 12.5px; padding: 4px 10px; border-radius: 6px; }
.mcp-result.ok { color: var(--success); background: color-mix(in srgb, var(--success) 10%, transparent); }
.mcp-result.err { color: var(--danger); background: color-mix(in srgb, var(--danger) 8%, transparent); }
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
