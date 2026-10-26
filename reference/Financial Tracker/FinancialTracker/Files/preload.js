const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Data
  saveData: (json) => ipcRenderer.invoke('save-data', json),
  loadFile: () => ipcRenderer.invoke('load-file'),
  importFile: () => ipcRenderer.invoke('import-file'),
  getAppInfo: () => ipcRenderer.invoke('get-app-info'),

  // Claude API (native, no CORS)
  claudeAPI: (payload) => ipcRenderer.invoke('claude-api', payload),

  // External links
  openExternal: (url) => ipcRenderer.invoke('open-external', url),

  // Listen for initial data push from main process
  onInitialData: (callback) => ipcRenderer.on('initial-data', (event, data) => callback(data))
});
