// datastore.js - safe load/save for the Financial Tracker data file.
// Pure Node (no Electron) so it can be tested on its own.
// Rules: never overwrite good data with bad data, never half-write the file,
// keep dated backups, and never silently invent a new empty file.
const fs = require('fs');
const path = require('path');

const DEFAULT_BACKUP_KEEP = 30;
const DEFAULT_BACKUP_MIN_INTERVAL_MS = 10 * 60 * 1000;

function sleepMs(ms) { Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms); }

// Where is the data file? Environment variable first, then the fallback given.
function resolveDataPath(env, fallbackPath) {
  const fromEnv = env && typeof env.FINANCIAL_DATA_PATH === 'string' ? env.FINANCIAL_DATA_PATH.trim() : '';
  return fromEnv || fallbackPath || null;
}

// Is this parsed JSON shaped like a tracker file? Returns an error string or null.
function shapeProblem(obj) {
  if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) return 'top level is not a JSON object';
  if ('transactions' in obj && !Array.isArray(obj.transactions)) return '"transactions" is not a list';
  if ('paychecks' in obj && !Array.isArray(obj.paychecks)) return '"paychecks" is not a list';
  if ('fixedExpenses' in obj && !Array.isArray(obj.fixedExpenses)) return '"fixedExpenses" is not a list';
  if ('settings' in obj && (obj.settings === null || typeof obj.settings !== 'object' || Array.isArray(obj.settings))) return '"settings" is not an object';
  return null;
}

// status: ok | missing | corrupt | invalid | error. Never throws, never creates anything.
function loadData(filePath) {
  if (!filePath) return { status: 'error', error: 'no data file path set' };
  let text;
  try {
    if (!fs.existsSync(filePath)) return { status: 'missing' };
    text = fs.readFileSync(filePath, 'utf8');
  } catch (e) { return { status: 'error', error: e.message }; }
  if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1); // tolerate a BOM
  let data;
  try { data = JSON.parse(text); }
  catch (e) { return { status: 'corrupt', error: e.message }; }
  const problem = shapeProblem(data);
  if (problem) return { status: 'invalid', error: problem };
  return { status: 'ok', text, data };
}

function stamp(d) {
  const p = n => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + '_' + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()) + String(d.getMilliseconds()).padStart(3, '0');
}

function listBackups(backupDir, baseName) {
  try {
    return fs.readdirSync(backupDir)
      .filter(n => n.startsWith(baseName + '.') && n.endsWith('.json'))
      .sort(); // stamps sort oldest -> newest
  } catch (e) { return []; }
}

// When was this backup made? Read it from its NAME, not from the file's modified time:
// on Windows a copied file keeps the OLD modified time of the original.
function backupTime(fileName, baseName) {
  const m = fileName.slice(baseName.length + 1).match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})(\d{3})\.json$/);
  if (!m) return 0; // unreadable name: treat as very old
  return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6], +m[7]).getTime();
}

// Copy the current file into backups/ unless a recent backup already exists.
function maybeBackup(filePath, opts) {
  const backupDir = opts.backupDir || path.join(path.dirname(filePath), 'backups');
  const keep = opts.keep || DEFAULT_BACKUP_KEEP;
  const minGap = opts.minIntervalMs === undefined ? DEFAULT_BACKUP_MIN_INTERVAL_MS : opts.minIntervalMs;
  if (!fs.existsSync(filePath)) return null;
  const base = path.basename(filePath, '.json');
  fs.mkdirSync(backupDir, { recursive: true });
  const existing = listBackups(backupDir, base);
  if (existing.length && minGap > 0) {
    const newestTime = backupTime(existing[existing.length - 1], base);
    if (Date.now() - newestTime < minGap) return null;
  }
  const dest = path.join(backupDir, base + '.' + stamp(new Date()) + '.json');
  fs.copyFileSync(filePath, dest);
  const all = listBackups(backupDir, base);
  for (const old of all.slice(0, Math.max(0, all.length - keep))) {
    try { fs.unlinkSync(path.join(backupDir, old)); } catch (e) { /* ignore */ }
  }
  return dest;
}

function atomicWrite(filePath, text) {
  const tmp = filePath + '.tmp';
  const fd = fs.openSync(tmp, 'w');
  try { fs.writeSync(fd, text, 0, 'utf8'); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  let lastErr;
  for (let i = 0; i < 6; i++) { // a reader (e.g. ASSET) may hold the file for a moment on Windows
    try { fs.renameSync(tmp, filePath); return; } catch (e) { lastErr = e; sleepMs(50 * (i + 1)); }
  }
  try { fs.unlinkSync(tmp); } catch (e) { /* ignore */ }
  throw lastErr;
}

// Save. Returns {ok:true, backup} or {ok:false, error}. Never throws.
function saveData(filePath, jsonString, opts) {
  opts = opts || {};
  if (!filePath) return { ok: false, error: 'no data file path set' };
  if (typeof jsonString !== 'string' || !jsonString.trim()) return { ok: false, error: 'refusing to save empty data' };
  let incoming;
  try { incoming = JSON.parse(jsonString); } catch (e) { return { ok: false, error: 'refusing to save: data is not valid JSON' }; }
  const problem = shapeProblem(incoming);
  if (problem) return { ok: false, error: 'refusing to save: ' + problem };

  // Wipe guard: never replace a file that has transactions with one that has none.
  const current = loadData(filePath);
  if (current.status === 'corrupt' || current.status === 'invalid') {
    // keep the unreadable original for rescue before anything touches it
    try { fs.copyFileSync(filePath, filePath + '.unreadable-' + stamp(new Date())); } catch (e) { /* ignore */ }
  }
  if (current.status === 'ok' && !opts.allowWipe) {
    const had = Array.isArray(current.data.transactions) ? current.data.transactions.length : 0;
    const has = Array.isArray(incoming.transactions) ? incoming.transactions.length : 0;
    if (had > 0 && has === 0) return { ok: false, error: 'refusing to save: this would erase all ' + had + ' transactions' };
  }
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    const backup = maybeBackup(filePath, opts);
    atomicWrite(filePath, jsonString);
    return { ok: true, backup };
  } catch (e) { return { ok: false, error: e.message }; }
}

module.exports = { resolveDataPath, shapeProblem, loadData, saveData, maybeBackup, listBackups };