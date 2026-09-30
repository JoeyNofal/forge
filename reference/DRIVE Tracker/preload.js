const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('driveApp', {
  loadData: () => ipcRenderer.invoke('drive-load-data'),
  saveData: (data) => ipcRenderer.invoke('drive-save-data', data),
  uploadReport: (fileContent, fileType) => ipcRenderer.invoke('upload-report', fileContent, fileType),
  onInitialData: (callback) => ipcRenderer.on('initial-data', (event, data) => callback(data)),
  onDataUpdated: (callback) => ipcRenderer.on('vehicle-data-updated', (event, data) => callback(data))
});