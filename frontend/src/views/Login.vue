<template>
  <div class="auth-wrap">
    <form class="card login" @submit.prevent="submit">
      <div class="brand">
        <img src="/favicon.svg" alt="" />
        <h1>{{ state.site.site_name }}</h1>
      </div>
      <label class="field">
        <span>用户名</span>
        <input v-model="username" required autocomplete="username" autofocus />
      </label>
      <label class="field">
        <span>密码</span>
        <input v-model="password" type="password" required autocomplete="current-password" />
      </label>
      <div v-if="error" class="error">{{ error }}</div>
      <button class="primary" style="width: 100%" :disabled="loading">{{ loading ? '登录中…' : '登录' }}</button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, state } from '../api'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await api.post('/api/auth/login', { username: username.value, password: password.value }, { silent: true })
    state.user = await api.get('/api/auth/me')
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
.login { width: 100%; max-width: 380px; }
.brand { display: flex; gap: 12px; align-items: center; margin-bottom: 20px; }
.brand img { width: 40px; height: 40px; }
.brand h1 { margin: 0; font-size: 20px; }
.error { color: var(--danger); margin-bottom: 12px; font-size: 13px; }
</style>
