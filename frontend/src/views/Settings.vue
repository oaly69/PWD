<template>
  <div class="page narrow">
    <h1>系统设置</h1>

    <form v-if="s" class="card section" @submit.prevent="save">
      <h2>站点</h2>
      <label class="field"><span>站点名称</span><input v-model="s.site_name" maxlength="64" required /></label>

      <h2>默认模型</h2>
      <div class="grid-2">
        <label class="field">
          <span>默认对话模型</span>
          <select v-model="chatKey">
            <option value="">不设置</option>
            <optgroup v-for="p in providers.filter((x) => x.chat_models.length)" :key="p.id" :label="p.name">
              <option v-for="m in p.chat_models" :key="m" :value="`${p.id}::${m}`">{{ m }}</option>
            </optgroup>
          </select>
        </label>
        <label class="field">
          <span>默认图像模型</span>
          <select v-model="imageKey">
            <option value="">不设置</option>
            <optgroup v-for="p in providers.filter((x) => x.image_models.length)" :key="p.id" :label="p.name">
              <option v-for="m in p.image_models" :key="m" :value="`${p.id}::${m}`">{{ m }}</option>
            </optgroup>
          </select>
        </label>
      </div>
      <label class="field">
        <span>新对话默认系统提示词</span>
        <textarea v-model="s.default_system_prompt" rows="3" />
      </label>
      <div class="row"><span class="spacer" /><button class="primary">保存设置</button></div>
    </form>

    <form class="card section" @submit.prevent="changePassword">
      <h2>修改密码</h2>
      <label class="field"><span>原密码</span><input v-model="pwd.old_password" type="password" required autocomplete="current-password" /></label>
      <div class="grid-2">
        <label class="field"><span>新密码</span><input v-model="pwd.new_password" type="password" minlength="8" required autocomplete="new-password" /></label>
        <label class="field"><span>确认新密码</span><input v-model="pwd.confirm" type="password" minlength="8" required autocomplete="new-password" /></label>
      </div>
      <div class="row"><span class="spacer" /><button class="primary">修改密码</button></div>
    </form>

    <div class="card section">
      <h2>关于</h2>
      <p class="muted">PWD 个人 AIGC 创作平台 v{{ state.site.version }} · <a href="/api/docs" target="_blank">API 文档</a></p>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, loadSite, state, toast } from '../api'

const s = ref(null)
const providers = ref([])
const pwd = reactive({ old_password: '', new_password: '', confirm: '' })

function keyOf(pid, model) {
  return pid && model ? `${pid}::${model}` : ''
}
function splitKey(v) {
  if (!v) return [null, '']
  const [pid, ...rest] = v.split('::')
  return [Number(pid), rest.join('::')]
}

const chatKey = computed({
  get: () => keyOf(s.value.default_chat_provider_id, s.value.default_chat_model),
  set: (v) => { [s.value.default_chat_provider_id, s.value.default_chat_model] = splitKey(v) },
})
const imageKey = computed({
  get: () => keyOf(s.value.default_image_provider_id, s.value.default_image_model),
  set: (v) => { [s.value.default_image_provider_id, s.value.default_image_model] = splitKey(v) },
})

async function save() {
  s.value = await api.put('/api/settings', s.value)
  await loadSite()
  toast('设置已保存', 'success')
}

async function changePassword() {
  if (pwd.new_password !== pwd.confirm) return toast('两次输入的新密码不一致', 'error')
  await api.post('/api/auth/password', { old_password: pwd.old_password, new_password: pwd.new_password })
  Object.assign(pwd, { old_password: '', new_password: '', confirm: '' })
  toast('密码已修改，其他设备上的登录已失效', 'success')
}

onMounted(async () => {
  ;[s.value, providers.value] = await Promise.all([api.get('/api/settings'), api.get('/api/providers')])
})
</script>

<style scoped>
.narrow { max-width: 760px; }
.section { margin-bottom: 16px; }
.section h2 { margin-top: 6px; }
</style>
