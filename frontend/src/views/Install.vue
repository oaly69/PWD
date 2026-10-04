<template>
  <div class="auth-wrap">
    <div class="card install">
      <div class="brand">
        <img src="/favicon.svg" alt="" />
        <div>
          <h1>欢迎使用 PWD</h1>
          <div class="muted">个人 AIGC 创作平台 · 首次安装向导 <span v-if="status.version">v{{ status.version }}</span></div>
        </div>
      </div>

      <ol class="steps">
        <li v-for="(s, i) in STEPS" :key="s" :class="{ active: step === i, done: step > i }">{{ s }}</li>
      </ol>

      <form v-if="step === 0" @submit.prevent="next">
        <label class="field" v-if="status.need_token">
          <span>安装令牌</span>
          <input v-model="form.install_token" required placeholder="容器环境变量 PWD_INSTALL_TOKEN 的值" />
        </label>
        <label class="field">
          <span>站点名称</span>
          <input v-model="form.site_name" required maxlength="64" />
        </label>
        <label class="field">
          <span>管理员用户名</span>
          <input v-model="form.admin_username" required minlength="2" maxlength="64" autocomplete="username" />
        </label>
        <div class="grid-2">
          <label class="field">
            <span>管理员密码</span>
            <input v-model="form.admin_password" type="password" required minlength="8" autocomplete="new-password" />
          </label>
          <label class="field">
            <span>确认密码</span>
            <input v-model="confirm" type="password" required minlength="8" autocomplete="new-password" />
          </label>
        </div>
        <div class="hint" style="margin-top: -6px; margin-bottom: 14px">数据目录：{{ status.data_dir }}（请确保已挂载为持久化卷）</div>
        <div class="row"><span class="spacer" /><button class="primary">下一步</button></div>
      </form>

      <div v-else-if="step === 1">
        <p class="muted" style="margin-top: 0">配置第一个模型服务（可跳过，稍后在「模型服务」中添加）。</p>
        <ProviderForm :form="provider" :test="testResult" ref="pform" />
        <div class="row">
          <button type="button" @click="step = 0">上一步</button>
          <span class="spacer" />
          <button type="button" :disabled="testing || !provider.base_url" @click="testProvider">{{ testing ? '测试中…' : '测试连接' }}</button>
          <button type="button" :disabled="submitting" @click="submit(false)">跳过</button>
          <button type="button" class="primary" :disabled="submitting || !provider.base_url" @click="submit(true)">完成安装</button>
        </div>
      </div>

      <div v-else class="done">
        <h2>🎉 安装完成</h2>
        <p class="muted">已使用管理员账号自动登录。</p>
        <button class="primary" @click="enter">进入创作台</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import ProviderForm from '../components/ProviderForm.vue'
import { api, loadSite, state, toast } from '../api'

const STEPS = ['站点与管理员', '模型服务', '完成']
const router = useRouter()
const step = ref(0)
const status = ref({})
const confirm = ref('')
const form = reactive({ site_name: 'PWD 创作台', admin_username: 'admin', admin_password: '', install_token: '' })
const provider = reactive({ name: '', kind: 'openai', base_url: '', api_key: '', chat_models: [], image_models: [], extra: {} })
const testResult = ref(null)
const testing = ref(false)
const submitting = ref(false)
const pform = ref(null)

onMounted(async () => {
  status.value = await api.get('/api/install/status')
  if (status.value.installed) router.replace('/')
})

function next() {
  if (form.admin_password !== confirm.value) return toast('两次输入的密码不一致', 'error')
  step.value = 1
}

async function testProvider() {
  testing.value = true
  try {
    testResult.value = await api.post('/api/install/test-provider', { install_token: form.install_token, provider })
  } finally {
    testing.value = false
  }
}

async function submit(withProvider) {
  if (withProvider && pform.value?.hasError()) return toast('请先修正工作流 JSON', 'error')
  submitting.value = true
  try {
    await api.post('/api/install', { ...form, provider: withProvider ? provider : null })
    await loadSite()
    state.user = await api.get('/api/auth/me')
    step.value = 2
  } finally {
    submitting.value = false
  }
}

function enter() {
  router.replace('/')
}
</script>

<style scoped>
.install { width: 100%; max-width: 640px; }
.brand { display: flex; gap: 14px; align-items: center; margin-bottom: 20px; }
.brand img { width: 48px; height: 48px; }
.brand h1 { margin: 0; }
.steps { display: flex; list-style: none; padding: 0; margin: 0 0 22px; gap: 8px; counter-reset: s; }
.steps li { flex: 1; padding: 8px 10px; border-radius: 8px; background: var(--panel-2); color: var(--muted); font-size: 13px; counter-increment: s; }
.steps li::before { content: counter(s) ". "; }
.steps li.active { background: var(--primary-soft); color: var(--primary); font-weight: 600; }
.steps li.done { color: var(--success); }
.done { text-align: center; padding: 20px 0; }
</style>
