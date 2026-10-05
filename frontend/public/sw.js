// PWD Service Worker：只缓存前端静态资源，接口与媒体文件始终走网络（需要登录校验）。
const CACHE = 'pwd-shell-v1'

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(['/', '/favicon.svg', '/manifest.webmanifest'])).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== location.origin) return
  if (/^\/(api|media|thumbs)\//.test(url.pathname)) return

  // 带哈希的构建产物：缓存优先
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((resp) => {
        if (resp.ok) caches.open(CACHE).then((c) => c.put(req, resp.clone()))
        return resp
      })),
    )
    return
  }

  // 页面导航：网络优先，离线时回退到缓存的应用外壳
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then((resp) => {
        if (resp.ok) caches.open(CACHE).then((c) => c.put('/', resp.clone()))
        return resp
      }).catch(() => caches.match('/')),
    )
  }
})
