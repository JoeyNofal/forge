const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');

const FITNESS_DATA_PATH = 'D:\\Projects\\NEXUS SYSTEM\\data\\fitness.json';

function createWindow() {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  win.loadFile('index.html');
}

// Load fitness.json when opened standalone
ipcMain.handle('training-load-data', () => {
  try {
    if (!fs.existsSync(FITNESS_DATA_PATH)) {
      return { error: 'fitness.json not found. Make sure NEXUS SYSTEM is installed correctly.' };
    }
    const raw = fs.readFileSync(FITNESS_DATA_PATH, 'utf8');
    return JSON.parse(raw);
  } catch (err) {
    return { error: err.message };
  }
});

// Save fitness.json after any change
ipcMain.handle('training-save-data', (event, data) => {
  try {
    fs.writeFileSync(FITNESS_DATA_PATH, JSON.stringify(data, null, 2), 'utf8');
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});