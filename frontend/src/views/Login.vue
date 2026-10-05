<template>
  <AuthShell :name="store.site.site_name">
    <div class="box">
      <h2>{{ isRegister ? '创建账号' : '欢迎回来' }}</h2>
      <p class="muted">{{ isRegister ? `注册 ${store.site.site_name} 账号` : `登录到 ${store.site.site_name}` }}</p>

      <n-alert v-if="pendingMsg" type="success" :bordered="false" class="item" title="注册成功">{{ pendingMsg }}</n-alert>

      <!-- 两步验证 -->
      <n-form v-if="needTotp" @submit.prevent="submit">
        <n-form-item label="两步验证码" :show-feedback="false" class="item">
          <n-input ref="codeInput" v-model:value="code" size="large" maxlength="6" placeholder="验证器 App 中的 6 位数字" :input-props="{ autocomplete: 'one-time-code', inputmode: 'numeric' }" @keydown.enter="submit" />
        </n-form-item>
        <n-alert v-if="error" type="error" :bordered="false" class="item">{{ error }}</n-alert>
        <n-button type="primary" size="large" block :loading="loading" attr-type="submit" @click="submit">验证并登录</n-button>
        <n-button quaternary block style="margin-top: 8px" @click="needTotp = false; code = ''">返回</n-button>
      </n-form>

      <n-form v-else @submit.prevent="submit">
        <n-form-item label="用户名" :show-feedback="false" class="item">
          <n-input v-model:value="username" size="large" :placeholder="isRegister ? '2～32 位，字母、数字、下划线或中文' : '用户名'" :input-props="{ autocomplete: 'username' }" autofocus />
        </n-form-item>
        <n-form-item label="密码" :show-feedback="false" class="item">
          <n-input v-model:value="password" size="large" type="password" show-password-on="click" :placeholder="isRegister ? '至少 8 位' : '密码'" :input-props="{ autocomplete: isRegister ? 'new-password' : 'current-password' }" @keydown.enter="submit" />
        </n-form-item>
        <n-form-item v-if="isRegister" label="确认密码" :show-feedback="false" class="item">
          <n-input v-model:value="confirm" size="large" type="password" show-password-on="click" :input-props="{ autocomplete: 'new-password' }" @keydown.enter="submit" />
        </n-form-item>
        <n-alert v-if="error" type="error" :bordered="false" class="item">{{ error }}</n-alert>
        <n-button type="primary" size="large" block :loading="loading" attr-type="submit" @click="submit">{{ isRegister ? '注册' : '登录' }}</n-button>
      </n-form>

      <template v-if="store.site.oidc_enabled && !needTotp && !isRegister">
        <div class="divider"><span>或</span></div>
        <n-button size="large" block secondary tag="a" href="/api/auth/oidc/login"><template #icon><KeyRound :size="16" /></template>{{ store.site.oidc_button_text || '使用单点登录' }}</n-button>
      </template>

      <div v-if="store.site.allow_register && !needTotp" class="switch">
        <template v-if="isRegister">已有账号？<router-link to="/login">去登录</router-link></template>
        <template v-else>还没有账号？<router-link to="/register">注册一个</router-link></template>
      </div>
    </div>
  </AuthShell>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { KeyRound } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NForm, NFormItem, NInput } from 'naive-ui'
import AuthShell from './AuthShell.vue'
import { api } from '../api'
import { store } from '../store'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const pendingMsg = ref('')
const loading = ref(false)
const needTotp = ref(false)
const code = ref('')
const codeInput = ref(null)

const isRegister = computed(() => !!route.meta.register && store.site.allow_register)

watch(() => route.path, () => {
  error.value = ''
  pendingMsg.value = ''
  needTotp.value = false
})

onMounted(() => {
  // 单点登录回调带回的结果
  if (route.query.sso_error) error.value = String(route.query.sso_error)
  if (route.query.sso === 'pending') pendingMsg.value = '账号已创建，请等待管理员审核通过后再登录。'
  if (route.query.sso_error || route.query.sso) router.replace('/login')
})

async function enter() {
  store.providersLoaded = false
  store.settings = null
  store.user = await api.get('/api/auth/me')
  const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/'
  router.replace(next)
}

async function submit() {
  if (loading.value || !username.value || !password.value) return
  error.value = ''
  if (isRegister.value) {
    if (!/^[A-Za-z0-9_\-\u4e00-\u9fa5]{2,32}$/.test(username.value.trim())) {
      error.value = '用户名需为 2～32 位的字母、数字、下划线、短横线或中文'
      return
    }
    if (password.value.length < 8) {
      error.value = '密码至少 8 位'
      return
    }
    if (password.value !== confirm.value) {
      error.value = '两次输入的密码不一致'
      return
    }
  }
  loading.value = true
  try {
    if (isRegister.value) {
      const r = await api.post('/api/auth/register', { username: username.value.trim(), password: password.value }, { silent: true })
      if (r.status === 'pending') {
        password.value = ''
        confirm.value = ''
        await router.replace('/login')
        pendingMsg.value = '账号已提交，请等待管理员审核通过后再登录。'
        return
      }
      await enter()
    } else {
      const r = await api.post('/api/auth/login', { username: username.value, password: password.value, code: needTotp.value ? code.value : undefined }, { silent: true })
      if (r.need_totp) {
        needTotp.value = true
        await nextTick()
        codeInput.value?.focus()
        return
      }
      await enter()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.box { width: 100%; max-width: 380px; }
h2 { margin: 0; font-size: 26px; }
.muted { margin: 6px 0 28px; }
.item { margin-bottom: 18px; }
.divider { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 12px; margin: 18px 0; }
.divider::before, .divider::after { content: ''; flex: 1; height: 1px; background: var(--border); }
.switch { margin-top: 20px; text-align: center; font-size: 13px; color: var(--muted); }
</style>
