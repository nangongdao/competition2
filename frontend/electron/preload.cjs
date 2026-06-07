const { contextBridge, ipcRenderer } = require('electron')

const CHANNELS = {
  getState: 'desktop-overlay:get-state',
  setVisible: 'desktop-overlay:set-visible',
  state: 'desktop-overlay:state',
  sendSnapshot: 'desktop-overlay:send-snapshot',
  snapshot: 'desktop-overlay:snapshot',
}

contextBridge.exposeInMainWorld('aiInterpreterDesktop', {
  setOverlayVisible(visible) {
    ipcRenderer.send(CHANNELS.setVisible, Boolean(visible))
  },

  getOverlayState() {
    return ipcRenderer.invoke(CHANNELS.getState)
  },

  sendSubtitleSnapshot(snapshot) {
    ipcRenderer.send(CHANNELS.sendSnapshot, snapshot)
  },

  onOverlayStateChange(callback) {
    const listener = (_event, state) => {
      callback(state)
    }
    ipcRenderer.on(CHANNELS.state, listener)

    return () => {
      ipcRenderer.removeListener(CHANNELS.state, listener)
    }
  },

  onSubtitleSnapshot(callback) {
    const listener = (_event, snapshot) => {
      callback(snapshot)
    }
    ipcRenderer.on(CHANNELS.snapshot, listener)

    return () => {
      ipcRenderer.removeListener(CHANNELS.snapshot, listener)
    }
  },
})

