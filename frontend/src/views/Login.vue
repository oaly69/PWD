<template>
  <AuthShell :name="store.site.site_name">
    <div class="box">
      <h2>欢迎回来</h2>
      <p class="muted">登录到 {{ store.site.site_name }}</p>
      <n-form @submit.prevent="submit">
        <n-form-item label="用户名" :show-feedback="false" class="item">
          <n-input v-model:value="username" size="large" placeholder="用户名" :input-props="{ autocomplete: 'username' }" autofocus />
        </n-form-item>
        <n-form-item label="密码" :show-feedback="false" class="item">
          <n-input v-model:value="password" size="large" type="password" show-password-on="click" placeholder="密码" :input-props="{ autocomplete: 'current-password' }" @keydown.enter="submit" />
        </n-form-item>
        <n-alert v-if="error" type="error" :bordered="false" class="item">{{ error }}</n-alert>
        <n-button type="primary" size="large" block :loading="loading" attr-type="submit" @click="submit">登录</n-button>
      </n-form>
    </div>
  </AuthShell>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NForm, NFormItem, NInput } from 'naive-ui'
import AuthShell from './AuthShell.vue'
import { api } from '../api'
import { store } from '../store'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  if (loading.value || !username.value || !password.value) return
  loading.value = true
  error.value = ''
  try {
    await api.post('/api/auth/login', { username: username.value, password: password.value }, { silent: true })
    store.user = await api.get('/api/auth/me')
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/'
    router.replace(next)
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
</style>
