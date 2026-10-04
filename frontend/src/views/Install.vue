<template>
  <AuthShell>
    <div class="box">
      <h2>初始化安装</h2>
      <p class="muted">只需一分钟完成设置 <span v-if="status.version">· v{{ status.version }}</span></p>
      <n-steps :current="step + 1" size="small" class="steps">
        <n-step title="站点与管理员" />
        <n-step title="模型服务" />
        <n-step title="完成" />
      </n-steps>

      <n-form v-if="step === 0" label-placement="top" @submit.prevent="next">
        <n-form-item v-if="status.need_token" label="安装令牌">
          <n-input v-model:value="form.install_token" placeholder="容器环境变量 PWD_INSTALL_TOKEN 的值" />
        </n-form-item>
        <n-form-item label="站点名称"><n-input v-model:value="form.site_name" maxlength="64" /></n-form-item>
        <n-form-item label="管理员用户名"><n-input v-model:value="form.admin_username" maxlength="64" :input-props="{ autocomplete: 'username' }" /></n-form-item>
        <div class="grid2">
          <n-form-item label="密码（至少 8 位）"><n-input v-model:value="form.admin_password" type="password" show-password-on="click" :input-props="{ autocomplete: 'new-password' }" /></n-form-item>
          <n-form-item label="确认密码"><n-input v-model:value="confirm" type="password" show-password-on="click" :input-props="{ autocomplete: 'new-password' }" @keydown.enter="next" /></n-form-item>
        </div>
        <n-alert type="info" :bordered="false" class="tip">数据将保存在 <code>{{ status.data_dir }}</code>，请确认该目录已挂载为持久化卷。</n-alert>
        <n-button type="primary" size="large" block @click="next">下一步</n-button>
      </n-form>

      <div v-else-if="step === 1">
        <p class="muted small">配置第一个模型服务，可以跳过，稍后在「模型服务」中添加。</p>
        <div class="provider-box">
          <ProviderForm ref="pform" :form="provider" :tester="tester" />
        </div>
        <div class="row actions">
          <n-button @click="step = 0">上一步</n-button>
          <span class="spacer" />
          <n-button :loading="submitting" @click="submit(false)">跳过</n-button>
          <n-button type="primary" :loading="submitting" :disabled="!provider.base_url" @click="submit(true)">完成安装</n-button>
        </div>
      </div>

      <div v-else class="done">
        <div class="done-icon"><Check :size="34" /></div>
        <h3>安装完成</h3>
        <p class="muted">已使用管理员账号自动登录，并预置了几个常用的对话角色和提示词模板。</p>
        <n-button type="primary" size="large" @click="router.replace('/')">进入创作台</n-button>
      </div>
    </div>
  </AuthShell>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NAlert, NButton, NForm, NFormItem, NInput, NStep, NSteps } from 'naive-ui'
import { Check } from 'lucide-vue-next'
import AuthShell from './AuthShell.vue'
import ProviderForm from '../components/ProviderForm.vue'
import { api, loadSite, toast } from '../api'
import { store } from '../store'

const router = useRouter()
const step = ref(0)
const status = ref({})
const confirm = ref('')
const form = reactive({ site_name: 'PWD 创作台', admin_username: 'admin', admin_password: '', install_token: '' })
const provider = reactive({ name: '', kind: 'openai', base_url: '', api_key: '', chat_models: [], image_models: [], video_models: [], tts_models: [], extra: {} })
const submitting = ref(false)
const pform = ref(null)

const tester = (payload) => api.post('/api/install/test-provider', { install_token: form.install_token, provider: payload })

onMounted(async () => {
  status.value = await api.get('/api/install/status')
  if (status.value.installed) router.replace('/')
})

function next() {
  if (status.value.need_token && !form.install_token.trim()) return toast('请输入安装令牌', 'error')
  if (form.admin_username.trim().length < 2) return toast('用户名至少 2 个字符', 'error')
  if (form.admin_password.length < 8) return toast('密码至少 8 位', 'error')
  if (form.admin_password !== confirm.value) return toast('两次输入的密码不一致', 'error')
  step.value = 1
}

async function submit(withProvider) {
  if (withProvider) {
    const err = pform.value?.validate()
    if (err) return toast(err, 'error')
  }
  submitting.value = true
  try {
    await api.post('/api/install', { ...form, provider: withProvider ? provider : null })
    await loadSite()
    store.user = await api.get('/api/auth/me')
    step.value = 2
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.box { width: 100%; max-width: 640px; }
h2 { margin: 0; font-size: 26px; }
.muted { margin: 6px 0 22px; }
.small { font-size: 13px; margin-top: 0; }
.steps { margin-bottom: 26px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }
.tip { margin-bottom: 18px; font-size: 13px; }
.provider-box { max-height: calc(100vh - 330px); overflow: auto; padding-right: 4px; }
.actions { margin-top: 18px; }
.done { text-align: center; padding: 20px 0; }
.done-icon { width: 72px; height: 72px; border-radius: 50%; display: grid; place-items: center; margin: 0 auto 16px; background: color-mix(in srgb, var(--success) 14%, transparent); color: var(--success); }
.done h3 { margin: 0; font-size: 20px; }
@media (max-width: 560px) { .grid2 { grid-template-columns: 1fr; } }
</style>
