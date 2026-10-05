// 全站统一使用 UTC+8（北京时间），与浏览器所在时区无关
export const TIME_ZONE = 'Asia/Shanghai'
const OFFSET = 8 * 3600_000
const DAY = 86400_000

/** UTC+8 下的日期分量（年、月、日、时），月份从 1 开始。 */
export function cnParts(d = new Date()) {
  const t = new Date(new Date(d).getTime() + OFFSET)
  return { year: t.getUTCFullYear(), month: t.getUTCMonth() + 1, day: t.getUTCDate(), hour: t.getUTCHours() }
}

/** UTC+8 下的日期键 YYYY-MM-DD，daysAgo 可往前推。 */
export function cnDateKey(d = new Date(), daysAgo = 0) {
  const p = cnParts(new Date(d).getTime() - daysAgo * DAY)
  return `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`
}

/** UTC+8 当天 0 点的时间戳。 */
export function cnDayStart(d = Date.now()) {
  return Math.floor((new Date(d).getTime() + OFFSET) / DAY) * DAY - OFFSET
}

export function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN', { hour12: false, timeZone: TIME_ZONE })
}

export function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('zh-CN', { timeZone: TIME_ZONE })
}

export function relativeTime(iso) {
  if (!iso) return ''
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`
  return formatDate(iso)
}

export function formatBytes(n) {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)))
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`
}

/** 按「置顶 / 今天 / 昨天 / 7 天内 / 30 天内 / 更早」分组。 */
export function groupByDate(items, key = 'updated_at') {
  const start = cnDayStart()
  const day = DAY
  const groups = [
    { label: '置顶', items: [] },
    { label: '今天', items: [] },
    { label: '昨天', items: [] },
    { label: '7 天内', items: [] },
    { label: '30 天内', items: [] },
    { label: '更早', items: [] },
  ]
  for (const it of items) {
    if (it.pinned) {
      groups[0].items.push(it)
      continue
    }
    const t = new Date(it[key]).getTime()
    if (t >= start) groups[1].items.push(it)
    else if (t >= start - day) groups[2].items.push(it)
    else if (t >= start - 7 * day) groups[3].items.push(it)
    else if (t >= start - 30 * day) groups[4].items.push(it)
    else groups[5].items.push(it)
  }
  return groups.filter((g) => g.items.length)
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok
  }
}

export function downloadUrl(url, filename) {
  const a = document.createElement('a')
  a.href = url
  if (filename) a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}
