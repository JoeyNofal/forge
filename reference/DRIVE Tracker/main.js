const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');

const VEHICLE_DATA_PATH = 'D:\\Projects\\NEXUS SYSTEM\\data\\vehicle.json';
const BACKEND_URL = 'http://127.0.0.1:8000';

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

// Load vehicle.json on startup
ipcMain.handle('load-data', () => {
  try {
    if (!fs.existsSync(VEHICLE_DATA_PATH)) {
      return { error: 'vehicle.json not found. Make sure NEXUS SYSTEM is installed correctly.' };
    }
    const raw = fs.readFileSync(VEHICLE_DATA_PATH, 'utf8');
    return JSON.parse(raw);
  } catch (err) {
    return { error: err.message };
  }
});

// Save vehicle.json after any change
ipcMain.handle('save-data', (event, data) => {
  try {
    fs.writeFileSync(VEHICLE_DATA_PATH, JSON.stringify(data, null, 2), 'utf8');
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// Send uploaded report to DRIVE agent via NEXUS backend for parsing
ipcMain.handle('upload-report', async (event, fileContent, fileType) => {
  try {
    const http = require('http');

    const body = JSON.stringify({
      agent_name: 'drive',
      message: 'I am uploading a service history report for you to read and extract all maintenance entries from. Here is the full content:\n\n' + fileContent,
      conversation_history: [],
      latitude: null,
      longitude: null,
      location_name: null
    });

    return new Promise((resolve) => {
      const options = {
        hostname: '127.0.0.1',
        port: 8000,
        path: '/chat/drive',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body)
        }
      };

      let responseData = '';

      const req = http.request(options, (res) => {
        res.on('data', (chunk) => {
          responseData += chunk.toString();
        });
        res.on('end', () => {
          resolve({ ok: true, response: responseData });
        });
      });

      req.on('error', (err) => {
        resolve({ ok: false, error: 'Could not reach NEXUS backend. Make sure the system is running.' });
      });

      req.write(body);
      req.end();
    });

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