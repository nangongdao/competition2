const { app, BrowserWindow, dialog, nativeImage, shell, session } = require('electron')
const path = require('node:path')

const APP_NAME = 'AI Interpreter'
const appUrl = process.env.AI_INTERPRETER_DESKTOP_URL

function createMainWindow(url) {
  const iconPath = path.join(__dirname, '..', 'public', 'app-icon.svg')
  const icon = nativeImage.createFromPath(iconPath)

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

  void window.loadURL(url)
}

function configurePermissions(url) {
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    const requesterUrl = webContents.getURL()
    const isAppPage = requesterUrl === url || requesterUrl.startsWith(url)
    const isMediaPermission = permission === 'media' || permission === 'display-capture'
    callback(isAppPage && isMediaPermission)
  })
}

app.setName(APP_NAME)

app.whenReady().then(() => {
  if (!appUrl) {
    dialog.showErrorBox(APP_NAME, 'Missing AI_INTERPRETER_DESKTOP_URL for desktop startup.')
    app.quit()
    return
  }

  configurePermissions(appUrl)
  createMainWindow(appUrl)
})

app.on('window-all-closed', () => {
  app.quit()
})
