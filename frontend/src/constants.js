/** 风格预设（参考 Fooocus styles），选中后追加到提示词末尾。 */
export const STYLE_PRESETS = [
  { name: '电影感', prompt: '电影剧照，电影级布光，宽银幕构图，浅景深，胶片颗粒，高级调色', negative: '卡通, 插画' },
  { name: '写实摄影', prompt: '专业摄影，超写实，自然光，细节丰富，85mm 镜头，8k 画质', negative: '绘画, 卡通, 3D 渲染' },
  { name: '日系动漫', prompt: '日系动漫风格，精致线稿，明亮色彩，赛璐璐上色，高质量插画', negative: '写实, 照片' },
  { name: '国风水墨', prompt: '中国水墨画风格，留白，写意笔触，宣纸质感，淡雅设色', negative: '照片, 3D' },
  { name: '赛博朋克', prompt: '赛博朋克风格，霓虹灯光，未来都市，高对比，蓝紫色调', negative: '' },
  { name: '3D 渲染', prompt: '3D 渲染，C4D，Octane 渲染，柔和全局光照，干净背景，高精度材质', negative: '平面, 草图' },
  { name: '水彩', prompt: '水彩画风格，晕染效果，柔和笔触，纸张纹理，清新色彩', negative: '照片, 3D' },
  { name: '油画', prompt: '古典油画风格，厚涂笔触，丰富色彩层次，画布纹理', negative: '照片' },
  { name: '像素风', prompt: '像素艺术，8-bit 复古游戏风格，有限调色板，清晰像素边缘', negative: '模糊, 写实' },
  { name: '极简扁平', prompt: '极简扁平插画，几何形状，大面积纯色，干净构图，矢量风格', negative: '复杂细节, 写实' },
  { name: '皮克斯', prompt: '皮克斯动画风格，可爱角色，夸张表情，柔和光照，3D 卡通', negative: '恐怖, 写实' },
  { name: '蒸汽波', prompt: '蒸汽波美学，粉紫渐变，复古 80 年代，希腊雕塑，网格地平线', negative: '' },
]

/** 常用画幅比例，值为传给接口的 size。 */
export const ASPECTS = [
  { label: '1:1', w: 1, h: 1, size: '1024x1024' },
  { label: '4:3', w: 4, h: 3, size: '1152x864' },
  { label: '3:4', w: 3, h: 4, size: '864x1152' },
  { label: '16:9', w: 16, h: 9, size: '1344x768' },
  { label: '9:16', w: 9, h: 16, size: '768x1344' },
  { label: '3:2', w: 3, h: 2, size: '1216x832' },
  { label: '2:3', w: 2, h: 3, size: '832x1216' },
  { label: '21:9', w: 21, h: 9, size: '1536x640' },
]

export const VIDEO_SIZES = [
  { label: '横屏 16:9', value: '1280x720' },
  { label: '竖屏 9:16', value: '720x1280' },
  { label: '方形 1:1', value: '960x960' },
  { label: '横屏 1080p', value: '1920x1080' },
  { label: '竖屏 1080p', value: '1080x1920' },
]

/** 常见 TTS 音色（OpenAI 及兼容服务）。也可直接输入任意音色名称。 */
export const VOICES = [
  { label: 'alloy（中性）', value: 'alloy' },
  { label: 'ash', value: 'ash' },
  { label: 'ballad', value: 'ballad' },
  { label: 'coral', value: 'coral' },
  { label: 'echo（男声）', value: 'echo' },
  { label: 'fable', value: 'fable' },
  { label: 'nova（女声）', value: 'nova' },
  { label: 'onyx（低沉男声）', value: 'onyx' },
  { label: 'sage', value: 'sage' },
  { label: 'shimmer（女声）', value: 'shimmer' },
  { label: 'verse', value: 'verse' },
  { label: '硅基流动 CosyVoice · alex', value: 'FunAudioLLM/CosyVoice2-0.5B:alex' },
  { label: '硅基流动 CosyVoice · anna', value: 'FunAudioLLM/CosyVoice2-0.5B:anna' },
  { label: '硅基流动 CosyVoice · bella', value: 'FunAudioLLM/CosyVoice2-0.5B:bella' },
  { label: '硅基流动 CosyVoice · benjamin', value: 'FunAudioLLM/CosyVoice2-0.5B:benjamin' },
  { label: '硅基流动 CosyVoice · charles', value: 'FunAudioLLM/CosyVoice2-0.5B:charles' },
  { label: '硅基流动 CosyVoice · claire', value: 'FunAudioLLM/CosyVoice2-0.5B:claire' },
  { label: '硅基流动 CosyVoice · david', value: 'FunAudioLLM/CosyVoice2-0.5B:david' },
  { label: '硅基流动 CosyVoice · diana', value: 'FunAudioLLM/CosyVoice2-0.5B:diana' },
]

export const PROVIDER_PRESETS = [
  { name: 'OpenAI', kind: 'openai', base_url: 'https://api.openai.com/v1', extra: { image_edit_mode: 'edits', video_api: 'openai' } },
  { name: 'DeepSeek', kind: 'openai', base_url: 'https://api.deepseek.com/v1', extra: {} },
  { name: '硅基流动', kind: 'openai', base_url: 'https://api.siliconflow.cn/v1', extra: { image_edit_mode: 'field', video_api: 'siliconflow' } },
  { name: '阿里百炼', kind: 'openai', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', extra: {} },
  { name: '火山方舟', kind: 'openai', base_url: 'https://ark.cn-beijing.volces.com/api/v3', extra: {} },
  { name: 'OpenRouter', kind: 'openai', base_url: 'https://openrouter.ai/api/v1', extra: {} },
  { name: 'Ollama', kind: 'openai', base_url: 'http://host.docker.internal:11434/v1', extra: {} },
  { name: 'ComfyUI', kind: 'comfyui', base_url: 'http://host.docker.internal:8188', extra: {} },
]

export const STATUS_TEXT = { pending: '排队中', running: '生成中', succeeded: '已完成', failed: '失败', cancelled: '已取消' }
export const STATUS_TYPE = { pending: 'default', running: 'info', succeeded: 'success', failed: 'error', cancelled: 'warning' }
