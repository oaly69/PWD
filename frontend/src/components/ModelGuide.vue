<template>
  <section class="guide">
    <div class="guide-head">
      <BookOpen :size="18" />
      <h2>接入指南</h2>
      <span class="muted small">常用平台的接入方式，以及各类模型的特点与擅长领域。模型更新很快，模型 ID 以「获取模型列表」结果和平台文档为准。</span>
    </div>

    <n-tabs v-model:value="tab" type="segment" size="small" class="tabs" animated>
      <n-tab-pane name="platforms" tab="平台接入">
        <div class="cards">
          <div v-for="p in PLATFORMS" :key="p.name" class="card">
            <div class="card-top">
              <b class="ellipsis">{{ p.name }}</b>
              <span class="spacer" />
              <n-button v-if="p.preset" size="tiny" secondary type="primary" @click="emit('use-preset', p.preset)">
                <template #icon><Plus :size="13" /></template>用此预设添加
              </n-button>
            </div>
            <div class="desc">{{ p.desc }}</div>
            <div class="kv">
              <span class="k">接口地址</span>
              <code class="v copy" title="点击复制" @click="copy(p.base_url)">{{ p.base_url }}</code>
            </div>
            <div class="kv">
              <span class="k">获取 Key</span>
              <a class="v link ellipsis" :href="p.key_url" target="_blank" rel="noopener">{{ p.key_url.replace(/^https?:\/\//, '') }} <ExternalLink :size="11" /></a>
            </div>
            <div class="chips"><span v-for="c in p.caps" :key="c" class="chip">{{ c }}</span></div>
            <ul class="tips"><li v-for="t in p.tips" :key="t">{{ t }}</li></ul>
          </div>
        </div>
      </n-tab-pane>

      <n-tab-pane v-for="k in MODEL_KINDS" :key="k.key" :name="k.key" :tab="k.label">
        <ol class="steps">
          <li v-for="s in k.steps" :key="s">{{ s }}</li>
        </ol>
        <div class="cards">
          <div v-for="m in k.models" :key="m.name" class="card">
            <div class="card-top">
              <b class="ellipsis">{{ m.name }}</b>
              <span class="muted small vendor">{{ m.vendor }}</span>
            </div>
            <div class="chips strong"><span v-for="t in m.tags" :key="t" class="chip">{{ t }}</span></div>
            <div class="desc">{{ m.desc }}</div>
            <div class="kv">
              <span class="k">模型 ID</span>
              <span class="v ids">
                <code v-for="id in m.ids" :key="id" :class="{ copy: !id.startsWith('（') }" :title="id.startsWith('（') ? '' : '点击复制'" @click="!id.startsWith('（') && copy(id)">{{ id }}</code>
              </span>
            </div>
            <div class="kv">
              <span class="k">接入平台</span>
              <span class="v">{{ m.where.join('、') }}</span>
            </div>
          </div>
        </div>
      </n-tab-pane>
    </n-tabs>
  </section>
</template>

<script setup>
import { NButton, NTabPane, NTabs } from 'naive-ui'
import { BookOpen, ExternalLink, Plus } from 'lucide-vue-next'
import { toast } from '../api'
import { useLocalRef } from '../composables/localRef'
import { MODEL_KINDS, PLATFORMS } from '../data/modelGuide'
import { copyText } from '../utils/format'

const emit = defineEmits(['use-preset'])
const tab = useLocalRef('pwd.guide.tab', 'platforms')

async function copy(text) {
  if (await copyText(text)) toast(`已复制 ${text}`, 'success')
}
</script>

<style scoped>
.guide { margin-top: 28px; padding: 18px 20px 20px; border-radius: 14px; background: var(--panel); border: 1px solid var(--border); }
.guide-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; color: var(--primary); margin-bottom: 14px; }
.guide-head h2 { margin: 0; font-size: 16px; color: var(--text); }
.small { font-size: 12.5px; }
.tabs :deep(.n-tabs-rail) { max-width: 760px; }
.steps { margin: 14px 0 16px; padding: 12px 14px 12px 34px; border-radius: 10px; background: var(--panel-2); font-size: 13px; line-height: 1.8; color: var(--text-2); }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; margin-top: 14px; }
.steps + .cards { margin-top: 0; }
.card { display: flex; flex-direction: column; gap: 8px; padding: 14px; border-radius: 12px; border: 1px solid var(--border); background: var(--bg, var(--panel)); min-width: 0; }
.card-top { display: flex; align-items: center; gap: 8px; min-width: 0; }
.card-top b { font-size: 14.5px; }
.vendor { margin-left: auto; white-space: nowrap; }
.desc { font-size: 13px; line-height: 1.65; color: var(--text-2); }
.kv { display: flex; gap: 8px; font-size: 12.5px; align-items: baseline; min-width: 0; }
.k { color: var(--muted); flex-shrink: 0; width: 56px; }
.v { min-width: 0; color: var(--text-2); }
.ids { display: flex; flex-wrap: wrap; gap: 4px; }
code { font-size: 12px; padding: 1px 6px; border-radius: 5px; background: var(--panel-2); word-break: break-all; }
code.copy { cursor: pointer; }
code.copy:hover { color: var(--primary); }
.link { color: var(--primary); text-decoration: none; display: inline-flex; align-items: center; gap: 3px; }
.link:hover { text-decoration: underline; }
.chips { display: flex; flex-wrap: wrap; gap: 4px; }
.chip { font-size: 11.5px; padding: 1px 8px; border-radius: 10px; background: var(--panel-2); color: var(--text-2); }
.chips.strong .chip { background: color-mix(in srgb, var(--primary) 12%, transparent); color: var(--primary); font-weight: 500; }
.tips { margin: 0; padding-left: 18px; font-size: 12.5px; line-height: 1.7; color: var(--muted); }
@media (max-width: 640px) { .guide { padding: 14px; } .cards { grid-template-columns: 1fr; } }
</style>
