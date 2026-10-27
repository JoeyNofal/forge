const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const ds = require('./datastore.js');
const { DataSession, readDotEnvValue, pickDataPath } = require('./session.js');

let mainWindow = null;
let session = null;
let allowClose = false;

// ── Where is the data file? ──
// 0) a --data-file launch option (for testing on a copy)
// 1) FINANCIAL_DATA_PATH in the FORGE .env file (the same setting ASSET uses)
// 2) FINANCIAL_DATA_PATH as a Windows system variable
// 3) Documents\FinancialTracker\financial-tracker-data.json
// If the file is not there, the app says so. It never invents a new empty file by itself.
function defaultDataPath() {
  return path.join(app.getPath('documents'), 'FinancialTracker', 'financial-tracker-data.json');
}
// Launch option for testing: electron . --data-file "path-to-a-copy.json"   (beats everything else)
function dataPathFromArgs(argv) {
  for (let i = 0; i < argv.length; i++) {
    const a = String(argv[i]);
    if (a.startsWith('--data-file=') && a.length > 12) return a.slice(12);
    if (a === '--data-file' && argv[i + 1]) return String(argv[i + 1]);
  }
  return null;
}
function configuredDataPath() {
  const fromArg = dataPathFromArgs(process.argv);
  if (fromArg) return fromArg;
  const envFile = path.join(__dirname, '..', '..', '.env');
  return pickDataPath(readDotEnvValue(envFile, 'FINANCIAL_DATA_PATH'), process.env, defaultDataPath());
}

function sendLoadState() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const res = session.open();
  if (res.status === 'ok') {
    try { ds.maybeBackup(session.filePath, {}); } catch (e) { /* a failed backup must not block the app */ }
    mainWindow.webContents.send('initial-data', { path: session.filePath, data: res.text });
  } else {
    mainWindow.webContents.send('load-problem', { path: session.filePath, state: session.state, error: session.error });
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    frame: true,
    backgroundColor: '#0f0f11',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: path.join(__dirname, 'icon.png'),
    title: 'Vault — Financial Tracker'
  });

  mainWindow.loadFile('index.html');

  // Before closing, ask the page to write any pending edit (saves are delayed by 0.8 seconds).
  mainWindow.on('close', (e) => {
    if (allowClose) return;
    e.preventDefault();
    mainWindow.webContents.send('flush-request');
    setTimeout(() => {   // never get stuck: close anyway after 3 seconds
      allowClose = true;
      if (mainWindow && !mainWindow.isDestroyed()) mainWindow.close();
    }, 3000);
  });
  mainWindow.on('closed', () => { mainWindow = null; });
}

app.whenReady().then(() => {
  session = new DataSession(configuredDataPath());
  createWindow();
  mainWindow.webContents.on('did-finish-load', sendLoadState);
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) { allowClose = false; createWindow(); } });

// ── IPC: Save data (refused unless the file was loaded safely) ──
ipcMain.handle('save-data', async (event, jsonString) => session.save(jsonString));

// ── IPC: Create a first empty file (only when the data file is missing) ──
ipcMain.handle('create-new-file', async (event, jsonString) => session.createNew(jsonString));

// ── IPC: Load a different file (a bad file never replaces the current session) ──
ipcMain.handle('load-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Open Financial Tracker Data',
    filters: [{ name: 'JSON', extensions: ['json'] }],
    properties: ['openFile']
  });
  if (result.canceled || !result.filePaths[0]) return { ok: false, canceled: true };
  const res = session.openOther(result.filePaths[0]);
  if (res.status !== 'ok') {
    return { ok: false, problem: { state: res.status, error: res.error || res.status, path: result.filePaths[0] } };
  }
  try { ds.maybeBackup(session.filePath, {}); } catch (e) { /* ignore */ }
  return { ok: true, path: session.filePath, data: res.text };
});

// ── IPC: Import old app data ──
ipcMain.handle('import-file', async () => {
  try {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: 'Import Old App Data',
      filters: [{ name: 'JSON', extensions: ['json'] }],
      properties: ['openFile']
    });
    if (result.canceled || !result.filePaths[0]) return { ok: false };
    const loaded = ds.loadData(result.filePaths[0]);
    if (loaded.status !== 'ok') return { ok: false, error: loaded.error || loaded.status };
    return { ok: true, data: loaded.text };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

// ── IPC: Open the folder with the dated backups ──
ipcMain.handle('open-backups-folder', async () => {
  if (!session || !session.filePath) return 'no data file path set';
  const dir = path.dirname(session.filePath);
  const msg = await shell.openPath(path.join(dir, 'backups'));
  if (msg) return shell.openPath(dir); // no backups yet: open the data folder instead
  return '';
});

// ── IPC: The page has finished writing; the window may close now ──
ipcMain.handle('flush-done', async () => {
  allowClose = true;
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.close();
});

// ── IPC: Open external link (https only) ──
ipcMain.handle('open-external', async (event, url) => {
  if (typeof url === 'string' && /^https:\/\//i.test(url)) await shell.openExternal(url);
});

// ── IPC: Get app info ──
ipcMain.handle('get-app-info', () => ({ ...(session ? session.info() : {}), version: app.getVersion() }));