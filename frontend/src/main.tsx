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

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    {surface === 'subtitle-overlay' ? <DesktopSubtitleOverlay /> : <App />}
  </React.StrictMode>,
)


function getSurface(): 'app' | 'subtitle-overlay' {
  const params = new URLSearchParams(window.location.search)
  return params.get('surface') === 'overlay' ? 'subtitle-overlay' : 'app'
}
