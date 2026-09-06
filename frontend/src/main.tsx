import React from 'react'
import ReactDOM from 'react-dom/client'

import App from './App'
import { DesktopSubtitleOverlay } from './desktop/DesktopSubtitleOverlay'
import './index.css'


const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Root element #root not found')
}

const surface = getSurface()
document.documentElement.dataset.surface = surface

// 离线模式（ROADMAP V5.4）：生产环境注册 Service Worker。
// 仅注册应用主界面（避免悬浮字幕窗重复注册）；开发环境跳过，
// 防止 SW 缓存干扰 Vite HMR。
if (surface === 'app' && import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').catch((error: unknown) => {
      console.warn('[PWA] service worker registration failed', error)
    })
  })
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    {surface === 'subtitle-overlay' ? <DesktopSubtitleOverlay /> : <App />}
  </React.StrictMode>,
)


function getSurface(): 'app' | 'subtitle-overlay' {
  const params = new URLSearchParams(window.location.search)
  return params.get('surface') === 'overlay' ? 'subtitle-overlay' : 'app'
}
