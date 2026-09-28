const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('trainingApp', {
  loadData: () => ipcRenderer.invoke('training-load-data'),
  saveData: (data) => ipcRenderer.invoke('training-save-data', data),
  onInitialData: (callback) => ipcRenderer.on('initial-data-training', (event, data) => callback(data)),
  onDataUpdated: (callback) => ipcRenderer.on('fitness-data-updated', (event, data) => callback(data))
});