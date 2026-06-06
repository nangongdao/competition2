const { app, BrowserWindow, Menu, Tray, dialog, nativeImage, shell, session } = require('electron')
const path = require('node:path')

const APP_NAME = 'AI Interpreter'
const appUrl = process.env.AI_INTERPRETER_DESKTOP_URL
const launcherLogFile = process.env.AI_INTERPRETER_LOG_FILE

let mainWindow = null
let tray = null

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
  })

  void window.loadURL(url)
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

function createTray() {
  if (tray) {
    return
  }

  try {
    tray = new Tray(createAppIcon())
    tray.setToolTip(APP_NAME)
    tray.setContextMenu(Menu.buildFromTemplate([
      {
        label: 'Open AI Interpreter',
        click: showMainWindow,
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
    ]))
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

    configurePermissions(appUrl)
    createTray()
    createMainWindow(appUrl)
  })

  app.on('window-all-closed', () => {
    app.quit()
  })
}
