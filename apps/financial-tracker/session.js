// session.js - decides WHEN the Financial Tracker may save, and WHERE the data file is.
// Pure Node (no Electron). All real file work goes through datastore.js.
const fs = require('fs');
const ds = require('./datastore.js');

// ---- .env reading (same file ASSET reads, so there is ONE place for the path) ----
function parseDotEnv(text) {
  const out = {};
  if (typeof text !== 'string') return out;
  if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);
  for (let line of text.split(/\r?\n/)) {
    line = line.trim();
    if (!line || line.startsWith('#')) continue;
    if (line.startsWith('export ')) line = line.slice(7).trim();
    const eq = line.indexOf('=');
    if (eq < 1) continue;
    const key = line.slice(0, eq).trim();
    let val = line.slice(eq + 1).trim();
    if ((val.startsWith('"') && val.indexOf('"', 1) > 0) || (val.startsWith("'") && val.indexOf("'", 1) > 0)) {
      const q = val[0]; val = val.slice(1, val.indexOf(q, 1)); // quoted: keep everything inside, backslashes stay literal
    } else {
      const hash = val.search(/\s#/); if (hash >= 0) val = val.slice(0, hash).trim(); // inline comment
    }
    if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) out[key] = val;
  }
  return out;
}

function readDotEnvValue(envFilePath, key) {
  try { const v = parseDotEnv(fs.readFileSync(envFilePath, 'utf8'))[key]; return v ? v : null; }
  catch (e) { return null; }
}

// Priority: the .env file WINS over a system variable (a stale system variable once silently
// overrode a correct .env), then the system variable, then the fallback.
function pickDataPath(dotenvValue, env, fallback) {
  const d = typeof dotenvValue === 'string' ? dotenvValue.trim() : '';
  if (d) return d;
  return ds.resolveDataPath(env, fallback);
}

// ---- the session ----
class DataSession {
  constructor(filePath, saveOpts) {
    this.filePath = filePath || null;
    this.saveOpts = saveOpts || {};
    this.state = 'not_opened';   // ready | missing | corrupt | invalid | error | not_opened
    this.error = null;
    this.saveAllowed = false;
  }
  _apply(res, pathUsed) {
    this.filePath = pathUsed;
    this.state = res.status === 'ok' ? 'ready' : res.status;
    this.error = res.error || null;
    this.saveAllowed = res.status === 'ok';
  }
  // Load the configured file. Saving is allowed ONLY if this succeeds.
  open() {
    const res = ds.loadData(this.filePath);
    this._apply(res, this.filePath);
    return res;
  }
  // Switch to another file. A bad choice leaves the current session exactly as it was.
  openOther(newPath) {
    if (!newPath || typeof newPath !== 'string') return { status: 'error', error: 'no file chosen' };
    const res = ds.loadData(newPath);
    if (res.status === 'ok') this._apply(res, newPath);
    return res;
  }
  save(jsonString) {
    if (!this.saveAllowed) {
      return { ok: false, error: 'Saving is turned off because the data file was not loaded safely (' + this.state + ').' };
    }
    return ds.saveData(this.filePath, jsonString, this.saveOpts);
  }
  // Only when the file is genuinely missing: write a first empty file, then allow saving.
  createNew(jsonString) {
    if (this.state !== 'missing') return { ok: false, error: 'A new file can only be created when the data file is missing.' };
    if (ds.loadData(this.filePath).status !== 'missing') return { ok: false, error: 'The file appeared in the meantime; reopen instead of creating a new one.' };
    const res = ds.saveData(this.filePath, jsonString, { ...this.saveOpts, allowWipe: true });
    if (res.ok) { this.state = 'ready'; this.error = null; this.saveAllowed = true; }
    return res;
  }
  info() { return { path: this.filePath, state: this.state, error: this.error, saveAllowed: this.saveAllowed }; }
}

module.exports = { parseDotEnv, readDotEnvValue, pickDataPath, DataSession };