<template>
  <div class="auth">
    <aside class="brand-panel">
      <div class="brand"><img src="/favicon.svg" alt="" /><span>{{ name }}</span></div>
      <div class="pitch">
        <h1>你的个人<br /><span class="grad">AIGC 创作工作室</span></h1>
        <p>一个地方完成对话写作、图像、视频与语音创作，作品与提示词统一沉淀。</p>
        <ul>
          <li><MessageSquare :size="16" />多模型对话，支持识图与推理过程</li>
          <li><ImageIcon :size="16" />文生图 / 图生图，风格预设与 AI 提示词优化</li>
          <li><Film :size="16" />文生视频、首帧生视频，任务后台运行</li>
          <li><Plug :size="16" />接入任意 OpenAI 兼容接口与 ComfyUI</li>
        </ul>
      </div>
      <div class="foot">数据完全保存在你自己的服务器上</div>
    </aside>
    <main class="form-panel"><slot /></main>
  </div>
</template>

<script setup>
import { Film, Image as ImageIcon, MessageSquare, Plug } from 'lucide-vue-next'

defineProps({ name: { type: String, default: 'PWD 创作台' } })
</script>

<style scoped>
.auth { min-height: 100vh; display: grid; grid-template-columns: minmax(380px, 46%) 1fr; }
.brand-panel { position: relative; padding: 40px 48px; display: flex; flex-direction: column; color: #fff; overflow: hidden;
  background: radial-gradient(900px 500px at 10% 10%, #8b7dff 0%, transparent 60%), radial-gradient(700px 500px at 90% 90%, #ff7ac6 0%, transparent 55%), #1b1640; }
.brand-panel::after { content: ''; position: absolute; inset: 0; background-image: radial-gradient(rgba(255, 255, 255, .12) 1px, transparent 1px); background-size: 22px 22px; mask-image: linear-gradient(180deg, transparent, #000 40%, transparent); pointer-events: none; }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 18px; position: relative; z-index: 1; }
.brand img { width: 34px; height: 34px; }
.pitch { margin: auto 0; position: relative; z-index: 1; max-width: 480px; }
.pitch h1 { font-size: 38px; line-height: 1.25; margin: 0 0 16px; letter-spacing: -.02em; }
.grad { background: linear-gradient(90deg, #fff, #ffd1ec); -webkit-background-clip: text; background-clip: text; color: transparent; }
.pitch p { opacity: .85; line-height: 1.7; margin: 0 0 24px; }
.pitch ul { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 12px; }
.pitch li { display: flex; align-items: center; gap: 10px; opacity: .92; font-size: 14px; }
.pitch li svg { flex-shrink: 0; padding: 6px; box-sizing: content-box; border-radius: 8px; background: rgba(255, 255, 255, .14); }
.foot { font-size: 12px; opacity: .6; position: relative; z-index: 1; }
.form-panel { display: flex; align-items: center; justify-content: center; padding: 40px 24px; background: var(--bg); }
@media (max-width: 900px) {
  .auth { grid-template-columns: 1fr; }
  .brand-panel { padding: 22px 20px; }
  .pitch, .foot { display: none; }
}
</style>
