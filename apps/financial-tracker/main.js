const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const https = require('https');

let mainWindow;
let dataFilePath = null;

// ── Find or create default data file ──
function getDefaultDataPath() {
  const userDocs = app.getPath('documents');
  const appFolder = path.join(userDocs, 'FinancialTracker');
  if (!fs.existsSync(appFolder)) fs.mkdirSync(appFolder, { recursive: true });
  return path.join(appFolder, 'financial-tracker-data.json');
}

// ── Auto-load: try the known JSON path first ──
const HARDCODED_DATA_PATH = 'D:\\Projects\\Financial Tracker\\FinancialTracker\\financial-tracker-data.json';

function tryAutoLoad() {
  if (fs.existsSync(HARDCODED_DATA_PATH)) {
    dataFilePath = HARDCODED_DATA_PATH;
    return fs.readFileSync(HARDCODED_DATA_PATH, 'utf8');
  }
  return null;
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
  mainWindow.webContents.openDevTools({ mode: 'detach' }); // remove this line once chat works
}

app.whenReady().then(() => {
  createWindow();

  // Send data to renderer once the window has finished loading
  mainWindow.webContents.on('did-finish-load', () => {

    // First, try to load from the hardcoded known path
    const autoData = tryAutoLoad();

    if (autoData) {
      // Found the real file — send it straight to the app
      mainWindow.webContents.send('initial-data', { path: HARDCODED_DATA_PATH, data: autoData });
    } else {
      // Couldn't find the real file — fall back to the Documents default
      const defaultPath = getDefaultDataPath();
      dataFilePath = defaultPath;
      if (!fs.existsSync(defaultPath)) {
        fs.writeFileSync(defaultPath, JSON.stringify({
          accounts: { vault: 0, flex: 0, funds: 0, cc: 0, car_loan: 0 },
          fundsSubAccounts: { carFund: 0, savingsFund: 0 },
          transactions: [], paychecks: [], fixedExpenses: [],
          groceries: {}, creditScores: [], conversations: [],
          settings: {
            regularRate: 35.21, overtimeMultiplier: 1.5, nightshiftMultiplier: 1.13,
            benefitsDeduction: 30.92, otherDeductions: 54.49, retirementPercent: 4,
            flexFloor: 500, ccTargetMin: 50, ccTargetMax: 100, ccLimit: 1800,
            ccPaymentDueDay: 21, ccStatementDay: 24, carLoanInitial: 18500,
            carLoanMonthlyTarget: 1500, carFundTarget: 1500, carFundMinimum: 1000,
            vaultBufferMonths: 7, alternatingSundayStart: '2026-03-13',
            groceryStartYear: 2024, groceryStartMonth: 9
          }
        }, null, 2));
      }
      const data = fs.readFileSync(defaultPath, 'utf8');
      mainWindow.webContents.send('initial-data', { path: defaultPath, data });
    }
  });
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });

// ── IPC: Save data ──
ipcMain.handle('save-data', async (event, jsonString) => {
  try {
    fs.writeFileSync(dataFilePath, jsonString, 'utf8');
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

// ── IPC: Load file (change file) ──
ipcMain.handle('load-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Open Financial Tracker Data',
    filters: [{ name: 'JSON', extensions: ['json'] }],
    properties: ['openFile']
  });
  if (result.canceled || !result.filePaths[0]) return { ok: false };
  dataFilePath = result.filePaths[0];
  const data = fs.readFileSync(dataFilePath, 'utf8');
  return { ok: true, path: dataFilePath, data };
});

// ── IPC: Import old app data ──
ipcMain.handle('import-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Import Old App Data',
    filters: [{ name: 'JSON', extensions: ['json'] }],
    properties: ['openFile']
  });
  if (result.canceled || !result.filePaths[0]) return { ok: false };
  const data = fs.readFileSync(result.filePaths[0], 'utf8');
  return { ok: true, data };
});

// ── IPC: Claude API call (native HTTPS, no CORS) ──
ipcMain.handle('claude-api', async (event, { systemPrompt, messages, apiKey }) => {
  // Use env var first, fall back to key passed from settings
  const key = process.env.ANTHROPIC_API_KEY || apiKey || '';
  if (!key) return { ok: false, error: 'No API key set. Go to Settings → AI Chatbot and paste your Anthropic API key.' };

  const body = JSON.stringify({
    model: 'claude-sonnet-4-20250514',
    max_tokens: 1500,
    system: systemPrompt,
    messages
  });

  return new Promise((resolve) => {
    const req = https.request({
      hostname: 'api.anthropic.com',
      path: '/v1/messages',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': key,
        'anthropic-version': '2023-06-01',
        'Content-Length': Buffer.byteLength(body)
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (parsed.error) return resolve({ ok: false, error: parsed.error.message });
          const text = (parsed.content || []).filter(b => b.type === 'text').map(b => b.text).join('\n');
          resolve({ ok: true, text });
        } catch (e) {
          resolve({ ok: false, error: 'Failed to parse response: ' + e.message });
        }
      });
    });
    req.on('error', (e) => resolve({ ok: false, error: e.message }));
    req.write(body);
    req.end();
  });
});

// ── IPC: Open external link ──
ipcMain.handle('open-external', async (event, url) => {
  await shell.openExternal(url);
});

// ── IPC: Get app info ──
ipcMain.handle('get-app-info', () => ({
  dataFilePath,
  version: app.getVersion(),
  hasApiKey: !!(process.env.ANTHROPIC_API_KEY)
}));
