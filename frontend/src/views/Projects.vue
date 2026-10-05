<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1>短片项目</h1>
        <div class="sub">从一句话创意到成片：AI 写剧本 → 设计角色与场景 → 拆分镜 → 生成关键帧、视频与配音 → 一键合成</div>
      </div>
      <span class="spacer" />
      <n-button type="primary" @click="showNew = true"><template #icon><Plus :size="16" /></template>新建项目</n-button>
    </div>

    <div class="steps">
      <div v-for="(s, i) in STEPS" :key="s.title" class="step">
        <span class="step-no">{{ i + 1 }}</span>
        <component :is="s.icon" :size="18" />
        <div><b>{{ s.title }}</b><div class="muted">{{ s.desc }}</div></div>
      </div>
    </div>

    <div class="grid">
      <div v-for="p in projects" :key="p.id" class="card" @click="$router.push(`/projects/${p.id}`)">
        <div class="cover" :class="`a${p.aspect.replace(':', '-')}`">
          <img v-if="p.cover" :src="p.cover.thumb_url" />
          <Clapperboard v-else :size="36" :stroke-width="1.4" />
          <span v-if="p.output" class="badge"><Film :size="12" /> 已出片</span>
        </div>
        <div class="info">
          <div class="name ellipsis">{{ p.name }}</div>
          <div class="muted small ellipsis">{{ p.synopsis || '还没有故事梗概' }}</div>
          <div class="muted small">{{ p.aspect }} · {{ p.shot_count }} 个镜头 · {{ relativeTime(p.updated_at) }}</div>
        </div>
      </div>
    </div>
    <EmptyState v-if="loaded && !projects.length" :icon="Clapperboard" title="还没有短片项目" desc="写下一句创意，让 AI 帮你完成剧本、分镜和成片。">
      <n-button type="primary" @click="showNew = true">新建项目</n-button>
    </EmptyState>

    <n-modal v-model:show="showNew" preset="card" title="新建短片项目" style="width: min(560px, 94vw)">
      <n-form label-placement="top">
        <n-form-item label="项目名称"><n-input v-model:value="form.name" maxlength="128" placeholder="例如：小橘的午后" /></n-form-item>
        <n-form-item label="故事梗概（可选，下一步可让 AI 扩写成剧本）">
          <n-input v-model:value="form.synopsis" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="一只橘猫在午后的窗台上，被一只蝴蝶吸引……" />
        </n-form-item>
        <n-form-item label="画幅">
          <n-radio-group v-model:value="form.aspect">
            <n-radio-button v-for="a in ['16:9', '9:16', '1:1', '4:3', '3:4']" :key="a" :value="a">{{ a }}{{ a === '16:9' ? ' 横屏' : a === '9:16' ? ' 竖屏' : '' }}</n-radio-button>
          </n-radio-group>
        </n-form-item>
        <n-form-item label="视觉风格（会追加到每个镜头的画面提示词）">
          <n-input v-model:value="form.style" placeholder="例如：宫崎骏动画风格，柔和水彩，温暖色调" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="row"><span class="spacer" /><n-button @click="showNew = false">取消</n-button><n-button type="primary" :disabled="!form.name.trim()" @click="create">创建</n-button></div>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NForm, NFormItem, NInput, NModal, NRadioButton, NRadioGroup } from 'naive-ui'
import { Clapperboard, Film, LayoutList, PenLine, Plus, Users, Wand2 } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import { api } from '../api'
import { relativeTime } from '../utils/format'

const STEPS = [
  { title: '剧本', desc: '一句话创意，AI 扩写成剧本', icon: PenLine },
  { title: '角色与场景', desc: '固定外观与参考图，保持一致', icon: Users },
  { title: '分镜', desc: 'AI 拆分镜头，批量生成画面', icon: LayoutList },
  { title: '成片', desc: '配音、字幕、一键合成导出', icon: Wand2 },
]
const router = useRouter()
const projects = ref([])
const loaded = ref(false)
const showNew = ref(false)
const form = reactive({ name: '', synopsis: '', aspect: '16:9', style: '' })

async function create() {
  const p = await api.post('/api/projects', { ...form, name: form.name.trim() })
  showNew.value = false
  router.push(`/projects/${p.id}`)
}

onMounted(async () => {
  projects.value = await api.get('/api/projects')
  loaded.value = true
})
</script>

<style scoped>
.steps { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 20px; }
.step { display: flex; gap: 10px; align-items: center; padding: 12px 14px; border-radius: 12px; background: var(--panel); border: 1px solid var(--border); font-size: 13px; color: var(--primary); }
.step b { color: var(--text); }
.step .muted { font-size: 12px; }
.step-no { width: 22px; height: 22px; border-radius: 50%; background: color-mix(in srgb, var(--primary) 14%, transparent); display: grid; place-items: center; font-weight: 700; font-size: 12px; flex-shrink: 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.card { border-radius: 14px; overflow: hidden; background: var(--panel); border: 1px solid var(--border); cursor: pointer; transition: all .15s; }
.card:hover { box-shadow: var(--shadow); transform: translateY(-2px); }
.cover { position: relative; aspect-ratio: 16 / 9; background: var(--panel-2); display: grid; place-items: center; color: var(--muted); overflow: hidden; }
.cover img { width: 100%; height: 100%; object-fit: cover; }
.badge { position: absolute; left: 8px; top: 8px; display: inline-flex; align-items: center; gap: 4px; font-size: 11.5px; padding: 2px 8px; border-radius: 10px; background: rgba(0, 0, 0, .6); color: #fff; }
.info { padding: 10px 14px 12px; display: flex; flex-direction: column; gap: 3px; }
.name { font-weight: 600; font-size: 15px; }
.small { font-size: 12.5px; }
@media (max-width: 860px) { .steps { grid-template-columns: repeat(2, 1fr); } }
</style>
