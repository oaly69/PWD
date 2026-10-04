import { computed, ref, watchEffect } from 'vue'
import { darkTheme } from 'naive-ui'

const KEY = 'pwd.theme'
const ACCENT_KEY = 'pwd.accent'

function load(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback
  } catch {
    return fallback
  }
}
function save(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* 隐私模式等情况下忽略 */
  }
}

export const ACCENTS = {
  violet: { name: '星紫', light: '#6d5dfc', dark: '#8b7dff' },
  blue: { name: '海蓝', light: '#2f6fed', dark: '#5b8ff9' },
  teal: { name: '青碧', light: '#0f9f8f', dark: '#2cc5b2' },
  rose: { name: '绯红', light: '#e0457b', dark: '#f06a98' },
  amber: { name: '琥珀', light: '#d97706', dark: '#f5a524' },
}

export const themeMode = ref(load(KEY, 'system')) // light / dark / system
export const accent = ref(load(ACCENT_KEY, 'violet'))

const media = window.matchMedia('(prefers-color-scheme: dark)')
const systemDark = ref(media.matches)
media.addEventListener?.('change', (e) => { systemDark.value = e.matches })

export const isDark = computed(() => (themeMode.value === 'system' ? systemDark.value : themeMode.value === 'dark'))

export function setThemeMode(mode) {
  themeMode.value = mode
  save(KEY, mode)
}
export function setAccent(name) {
  accent.value = name
  save(ACCENT_KEY, name)
}

function shade(hex, amount) {
  const n = parseInt(hex.slice(1), 16)
  const f = (c) => Math.max(0, Math.min(255, Math.round(c + (amount > 0 ? (255 - c) * amount : c * amount))))
  const r = f(n >> 16), g = f((n >> 8) & 255), b = f(n & 255)
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`
}

export const naiveTheme = computed(() => (isDark.value ? darkTheme : null))

export const themeOverrides = computed(() => {
  const a = ACCENTS[accent.value] || ACCENTS.violet
  const primary = isDark.value ? a.dark : a.light
  return {
    common: {
      primaryColor: primary,
      primaryColorHover: shade(primary, 0.12),
      primaryColorPressed: shade(primary, -0.12),
      primaryColorSuppl: shade(primary, 0.12),
      borderRadius: '8px',
      borderRadiusSmall: '6px',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
      ...(isDark.value
        ? { bodyColor: '#101014', cardColor: '#18181d', modalColor: '#1c1c22', popoverColor: '#222229', tableColor: '#18181d' }
        : { bodyColor: '#f6f6f9', cardColor: '#ffffff' }),
    },
    Card: { borderRadius: '12px' },
    Layout: isDark.value ? { siderColor: '#141418', headerColor: '#101014' } : { siderColor: '#ffffff', headerColor: '#f6f6f9' },
  }
})

// 同步到 CSS 变量，供自定义样式使用
watchEffect(() => {
  const root = document.documentElement
  const a = ACCENTS[accent.value] || ACCENTS.violet
  root.dataset.theme = isDark.value ? 'dark' : 'light'
  root.style.setProperty('--primary', isDark.value ? a.dark : a.light)
  root.style.colorScheme = isDark.value ? 'dark' : 'light'
})
