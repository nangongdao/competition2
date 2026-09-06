/**
 * Service Worker —— 离线模式骨架（ROADMAP V5.4）。
 *
 * 策略：
 * - 预缓存（precache）：应用壳（index.html / 已构建的 assets）在首次访问时
 *   缓存，离线时仍可加载 UI。
 * - 运行时缓存（runtime cache）：首次请求后放入缓存，二次访问离线可用。
 * - 离线兜底：网络失败时回退到缓存，再失败则显示离线提示页。
 * - 版本管理：CACHE_VERSION 变化时自动清理旧缓存。
 *
 * 说明：本地开发时 Vite dev server 的模块路径带 /@fs/ 前缀且内容会变化，
 * 此处只缓存生产构建产物（/assets/ 与根 index.html），不缓存 dev 模块，
 * 避免开发热更新被 SW 污染。
 */

const CACHE_VERSION = 'ai-interpreter-v1'
const APP_SHELL_CACHE = `${CACHE_VERSION}-app-shell`
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`

// 预缓存清单：生产构建产物（vite 会注入 hash 文件名，这里只缓存固定入口；
// 实际 assets 由 runtime 缓存策略在首次请求后补录）。
const APP_SHELL_URLS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './app-icon.svg',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(APP_SHELL_CACHE)
      .then((cache) => cache.addAll(APP_SHELL_URLS))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => !key.startsWith(CACHE_VERSION))
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request

  // 只处理 GET；忽略非同源请求（后端 API/WebSocket 不走 SW）。
  if (request.method !== 'GET') {
    return
  }
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) {
    return
  }

  // API 与 WebSocket 始终走网络（实时翻译依赖实时连接）。
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) {
    return
  }

  // 生产 assets（带 hash）与页面导航：缓存优先 + 网络回退。
  const isAsset = url.pathname.startsWith('/assets/')
  const isNavigation = request.mode === 'navigate'

  if (isAsset) {
    event.respondWith(cacheFirst(request))
    return
  }

  if (isNavigation) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone()
          void caches.open(APP_SHELL_CACHE).then((cache) => cache.put(request, copy))
          return response
        })
        .catch(() =>
          caches
            .match(request)
            .then((cached) => cached || caches.match('./index.html')),
        ),
    )
    return
  }

  // 其它静态资源：网络优先 + 运行时缓存回退。
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone()
          void caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy))
        }
        return response
      })
      .catch(() => caches.match(request)),
  )
})

/**
 * 缓存优先策略：先查缓存，未命中再请求并写入缓存。
 */
async function cacheFirst(request) {
  const cached = await caches.match(request)
  if (cached) {
    return cached
  }
  try {
    const response = await fetch(request)
    if (response.ok) {
      const copy = response.clone()
      void caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy))
    }
    return response
  } catch {
    return new Response('Offline', { status: 503, statusText: 'Service Unavailable' })
  }
}
