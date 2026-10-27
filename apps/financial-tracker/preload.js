const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Data
  saveData: (json) => ipcRenderer.invoke('save-data', json),
  createNewFile: (json) => ipcRenderer.invoke('create-new-file', json),
  loadFile: () => ipcRenderer.invoke('load-file'),
  importFile: () => ipcRenderer.invoke('import-file'),
  openBackupsFolder: () => ipcRenderer.invoke('open-backups-folder'),
  getAppInfo: () => ipcRenderer.invoke('get-app-info'),

  // Closing the window
  flushDone: () => ipcRenderer.invoke('flush-done'),

  // External links
  openExternal: (url) => ipcRenderer.invoke('open-external', url),

  // Messages pushed from the main process
  onInitialData: (callback) => ipcRenderer.on('initial-data', (event, data) => callback(data)),
  onLoadProblem: (callback) => ipcRenderer.on('load-problem', (event, data) => callback(data)),
  onFlushRequest: (callback) => ipcRenderer.on('flush-request', () => callback())
});