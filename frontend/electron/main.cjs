const {
  app,
  BrowserWindow,
  Menu,
  Tray,
  dialog,
  ipcMain,
  nativeImage,
  screen,
  shell,
  session,
} = require('electron')
const path = require('node:path')

const APP_NAME = 'AI Interpreter'
const appUrl = process.env.AI_INTERPRETER_DESKTOP_URL
const launcherLogFile = process.env.AI_INTERPRETER_LOG_FILE
const preloadScript = path.join(__dirname, 'preload.cjs')

const OVERLAY_CHANNELS = {
  getState: 'desktop-overlay:get-state',
  setVisible: 'desktop-overlay:set-visible',
  state: 'desktop-overlay:state',
  sendSnapshot: 'desktop-overlay:send-snapshot',
  snapshot: 'desktop-overlay:snapshot',
}

let mainWindow = null
let overlayWindow = null
let tray = null
let isOverlayVisible = true
let latestSubtitleSnapshot = null

const fallbackIconSvg = `
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#101722"/>
  <path d="M18 42V22h6v20h-6Zm11 0 8-20h6l8 20h-6l-1.4-4h-7.3l-1.4 4H29Zm8.9-9h4.1l-2-5.9-2.1 5.9Z" fill="#63d2ff"/>
</svg>`

const singleInstanceLock = app.requestSingleInstanceLock()

if (!singleInstanceLock) {
  app.quit()
}

function createMainWindow(url) {
  const icon = createAppIcon()

  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    title: APP_NAME,
    backgroundColor: '#101722',
    autoHideMenuBar: true,
    icon,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: preloadScript,
      sandbox: true,
      webSecurity: true,
    },
  })

  mainWindow = window
  window.setMenuBarVisibility(false)

  window.webContents.setWindowOpenHandler(({ url: targetUrl }) => {
    shell.openExternal(targetUrl)
    return { action: 'deny' }
  })

  window.webContents.on('will-navigate', (event, targetUrl) => {
    if (targetUrl !== url && !targetUrl.startsWith(url)) {
      event.preventDefault()
      shell.openExternal(targetUrl)
    }
  })

  window.on('minimize', (event) => {
    if (!tray) {
      return
    }

    event.preventDefault()
    window.hide()
  })

  window.on('closed', () => {
    mainWindow = null
    if (overlayWindow && !overlayWindow.isDestroyed()) {
      overlayWindow.close()
    }
  })

  void window.loadURL(url)
  createOverlayWindow(url)
}

function createOverlayWindow(url) {
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    return
  }

  const bounds = screen.getPrimaryDisplay().workArea
  const window = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    minWidth: 320,
    minHeight: 180,
    title: `${APP_NAME} Floating Subtitles`,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: false,
    resizable: false,
    movable: false,
    fullscreenable: false,
    hasShadow: false,
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: preloadScript,
      sandbox: true,
      webSecurity: true,
    },
  })

  overlayWindow = window
  window.setIgnoreMouseEvents(true)
  window.setAlwaysOnTop(true, 'screen-saver')
  window.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })

  window.on('closed', () => {
    overlayWindow = null
    publishOverlayState()
    refreshTrayMenu()
  })

  window.webContents.on('did-finish-load', () => {
    if (latestSubtitleSnapshot) {
      window.webContents.send(OVERLAY_CHANNELS.snapshot, latestSubtitleSnapshot)
    }
    publishOverlayState()
  })

  void window.loadURL(createOverlayUrl(url))
  applyOverlayVisibility()
  publishOverlayState()
  refreshTrayMenu()
}

function createOverlayUrl(url) {
  const parsedUrl = new URL(url)
  parsedUrl.searchParams.set('surface', 'overlay')
  return parsedUrl.toString()
}

function positionOverlayWindow() {
  if (!overlayWindow || overlayWindow.isDestroyed()) {
    return
  }

  const bounds = screen.getPrimaryDisplay().workArea
  overlayWindow.setBounds(bounds, false)
}

function applyOverlayVisibility() {
  if (!overlayWindow || overlayWindow.isDestroyed()) {
    return
  }

  if (isOverlayVisible) {
    positionOverlayWindow()
    overlayWindow.showInactive()
    overlayWindow.setAlwaysOnTop(true, 'screen-saver')
    return
  }

  overlayWindow.hide()
}

function setOverlayVisible(visible) {
  isOverlayVisible = Boolean(visible)
  applyOverlayVisibility()
  publishOverlayState()
  refreshTrayMenu()
}

function getOverlayState() {
  const isAvailable = Boolean(overlayWindow && !overlayWindow.isDestroyed())
  const isVisible = Boolean(isAvailable && isOverlayVisible && overlayWindow.isVisible())

  return {
    available: isAvailable,
    visible: isVisible,
  }
}

function publishOverlayState() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return
  }

  mainWindow.webContents.send(OVERLAY_CHANNELS.state, getOverlayState())
}

function forwardSubtitleSnapshot(snapshot) {
  latestSubtitleSnapshot = snapshot

  if (!overlayWindow || overlayWindow.isDestroyed()) {
    return
  }

  overlayWindow.webContents.send(OVERLAY_CHANNELS.snapshot, snapshot)
}

function createAppIcon() {
  const iconPath = path.join(__dirname, '..', 'public', 'app-icon.svg')
  const fileIcon = nativeImage.createFromPath(iconPath)

  if (!fileIcon.isEmpty()) {
    return fileIcon
  }

  return nativeImage.createFromDataURL(
    `data:image/svg+xml;charset=utf-8,${encodeURIComponent(fallbackIconSvg)}`,
  )
}

function showMainWindow() {
  if (!mainWindow) {
    if (appUrl) {
      createMainWindow(appUrl)
    }
    return
  }

  if (mainWindow.isMinimized()) {
    mainWindow.restore()
  }
  mainWindow.show()
  mainWindow.focus()
}

function buildTrayMenu() {
  return Menu.buildFromTemplate([
    {
      label: 'Open AI Interpreter',
      click: showMainWindow,
    },
    {
      label: isOverlayVisible ? 'Hide floating subtitles' : 'Show floating subtitles',
      enabled: Boolean(overlayWindow && !overlayWindow.isDestroyed()),
      click: () => {
        setOverlayVisible(!isOverlayVisible)
      },
    },
    {
      label: 'Open startup log',
      enabled: Boolean(launcherLogFile),
      click: () => {
        if (launcherLogFile) {
          void shell.openPath(launcherLogFile)
        }
      },
    },
    {
      label: 'Reload window',
      click: () => {
        mainWindow?.reload()
      },
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        app.quit()
      },
    },
  ])
}

function refreshTrayMenu() {
  if (!tray) {
    return
  }

  tray.setContextMenu(buildTrayMenu())
}

function createTray() {
  if (tray) {
    return
  }

  try {
    tray = new Tray(createAppIcon())
    tray.setToolTip(APP_NAME)
    refreshTrayMenu()
    tray.on('click', showMainWindow)
  } catch (error) {
    tray = null
    console.error('[Electron] failed to create tray', error)
  }
}

function configurePermissions(url) {
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    const requesterUrl = webContents.getURL()
    const isAppPage = requesterUrl === url || requesterUrl.startsWith(url)
    const isMediaPermission = permission === 'media' || permission === 'display-capture'
    callback(isAppPage && isMediaPermission)
  })
}

function registerOverlayIpc() {
  ipcMain.handle(OVERLAY_CHANNELS.getState, () => getOverlayState())
  ipcMain.on(OVERLAY_CHANNELS.setVisible, (_event, visible) => {
    setOverlayVisible(Boolean(visible))
  })
  ipcMain.on(OVERLAY_CHANNELS.sendSnapshot, (_event, snapshot) => {
    forwardSubtitleSnapshot(snapshot)
  })
}

if (singleInstanceLock) {
  app.setName(APP_NAME)

  if (process.platform === 'win32') {
    app.setAppUserModelId('competition2.ai-interpreter')
  }

  app.on('second-instance', showMainWindow)

  app.whenReady().then(() => {
    if (!appUrl) {
      dialog.showErrorBox(APP_NAME, 'Missing AI_INTERPRETER_DESKTOP_URL for desktop startup.')
      app.quit()
      return
    }

    registerOverlayIpc()
    screen.on('display-metrics-changed', positionOverlayWindow)
    screen.on('display-added', positionOverlayWindow)
    screen.on('display-removed', positionOverlayWindow)
    configurePermissions(appUrl)
    createTray()
    createMainWindow(appUrl)
  })

  app.on('window-all-closed', () => {
    app.quit()
  })
}
