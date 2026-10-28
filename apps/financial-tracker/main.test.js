// Run:  node main.test.js     (from apps/financial-tracker)
// Runs the REAL main.js against a fake "electron", inside a temporary copy of the app folder,
// so it can never touch your real data file or your real .env.
const fs = require('fs'), os = require('os'), path = require('path'), Module = require('module');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const here = __dirname;
const rd = (f) => fs.readFileSync(path.join(here, f), 'utf8');

// ---------- L1 static ----------
const mainSrc = rd('main.js'), preSrc = rd('preload.js'), html = rd('index.html');
check('L1 main.js: no Claude/Anthropic API code', !/anthropic|claude-api|api\.anthropic|x-api-key/i.test(mainSrc));
check('L1 main.js: no raw https requests', !/require\('https'\)|https\.request/.test(mainSrc));
check('L1 main.js: DevTools not opened', !/openDevTools/.test(mainSrc));
check('L1 main.js: no hardcoded drive path', !/[A-Z]:\\\\/.test(mainSrc) && !/\b[A-Z]:\//.test(mainSrc));
check('L1 main.js: never writes files itself (only via session/datastore)', !/writeFileSync|createWriteStream|appendFile/.test(mainSrc));
check('L1 main.js: no secrets words', !/sk-ant|AIza|apiKey/i.test(mainSrc));
check('L1 preload.js: no claudeAPI', !/claude/i.test(preSrc));
check('L1 index.html: no claudeAPI / anthropicApiKey', !/claudeAPI|anthropicApiKey/.test(html));
for (const ch of ['save-data', 'create-new-file', 'load-file', 'import-file', 'open-backups-folder', 'flush-done', 'open-external', 'get-app-info'])
  check('L1 channel "' + ch + '" is the same in main.js and preload.js', mainSrc.includes("'" + ch + "'") && preSrc.includes("'" + ch + "'"));
for (const ch of ['initial-data', 'load-problem', 'flush-request'])
  check('L1 pushed message "' + ch + '" is sent by main.js and heard by preload.js', mainSrc.includes("'" + ch + "'") && preSrc.includes("'" + ch + "'"));
for (const id of ['load-problem', 'lp-title', 'lp-msg', 'lp-path', 'lp-choose', 'lp-create', 'lp-backups'])
  check('L1 index.html has #' + id, html.includes('id="' + id + '"'));

check('L1 index.html loads no scripts from the internet', !/<script[^>]*\bsrc=["']https?:/i.test(html));
check('L1 index.html loads nothing from the internet (no http/https src or href at all)', !/(?:src|href)=["']https?:/i.test(html));
const fontUrls = [...html.matchAll(/url\("(vendor\/fonts\/[^"]+)"\)/g)].map(m => m[1]);
check('L1 index.html declares 8 local fonts and every font file exists', fontUrls.length === 8 && fontUrls.every(u => fs.existsSync(path.join(here, u)) && fs.statSync(path.join(here, u)).size > 5000));
check('L1 the three font license files are included', ['dm-sans', 'dm-serif-display', 'dm-mono'].every(n => fs.existsSync(path.join(here, 'vendor', 'fonts', 'LICENSE-' + n + '.txt'))));
check('L1 index.html loads dates.js and uses it for fmtDate and fmtDateInput', html.includes('<script src="dates.js"></script>') && html.includes('FTDates.fmtDate(d)') && html.includes('FTDates.fmtDateInput(d)'));
check('L1 package.json packages dates.js', /"dates\.js"/.test(rd('package.json')));
check('L1 package.json packages vendor subfolders too', /vendor\/\*\*\/\*/.test(rd('package.json')));
for (const f of ['vendor/chart.umd.js', 'vendor/exceljs.min.js'])
  check('L1 ' + f + ' exists and is not tiny', fs.existsSync(path.join(here, f)) && fs.statSync(path.join(here, f)).size > 100000);
check('L1 package.json packages the vendor folder', /vendor\//.test(rd('package.json')));

// ---------- harness: a temp copy of the app + a fake electron ----------
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ft-main-'));
let caseN = 0;
function setupCase(opts) {
  opts = opts || {};
  const base = path.join(root, 'k' + (caseN++));
  const appDir = path.join(base, 'apps', 'financial-tracker');
  fs.mkdirSync(appDir, { recursive: true });
  for (const f of ['main.js', 'datastore.js', 'session.js']) fs.copyFileSync(path.join(here, f), path.join(appDir, f));
  const docs = path.join(base, 'Documents'); fs.mkdirSync(docs);
  if (opts.envLine !== undefined) fs.writeFileSync(path.join(base, '.env'), opts.envLine);
  if (opts.sharedEnvLine !== undefined) { fs.mkdirSync(path.join(base, 'shared')); fs.writeFileSync(path.join(base, 'shared', '.env'), opts.sharedEnvLine); }
  const sent = [], winHandlers = {}, wcHandlers = {}, ipc = {}, timers = [], opened = [];
  let closeCalls = 0, closedNow = 0;
  const electron = {
    app: { getPath: () => docs, getVersion: () => '9.9.9', whenReady: () => Promise.resolve(), on() {}, quit() {} },
    BrowserWindow: class {
      constructor(o) { this.opts = o; this.webContents = { send: (c, p) => sent.push([c, p]), on: (e, cb) => { wcHandlers[e] = cb; } }; BrowserWindow.last = this; }
      loadFile() {}
      on(e, cb) { winHandlers[e] = cb; }
      isDestroyed() { return false; }
      close() { closeCalls++; const ev = { prevented: false, preventDefault() { this.prevented = true; } }; winHandlers.close && winHandlers.close(ev); if (!ev.prevented) closedNow++; }
      static getAllWindows() { return [BrowserWindow.last]; }
    },
    ipcMain: { handle: (n, fn) => { ipc[n] = fn; } },
    dialog: { showOpenDialog: async () => electron._dialog },
    shell: { openPath: async (p) => { opened.push(p); return electron._openPathResult || ''; }, openExternal: async (u) => { opened.push('EXT ' + u); } },
    _dialog: { canceled: true, filePaths: [] }, _openPathResult: ''
  };
  const BrowserWindow = electron.BrowserWindow;
  const realSetTimeout = global.setTimeout;
  const origLoad = Module._load;
  Module._load = function (req, parent, isMain) { return req === 'electron' ? electron : origLoad.call(this, req, parent, isMain); };
  global.setTimeout = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
  const argvBackup = process.argv; process.argv = ['electron', '.'].concat(opts.argv || []);
  const envBackup = process.env.FINANCIAL_DATA_PATH; if (opts.sysEnv !== undefined) process.env.FINANCIAL_DATA_PATH = opts.sysEnv; else delete process.env.FINANCIAL_DATA_PATH;
  const restoreEnv = () => { process.argv = argvBackup; if (envBackup === undefined) delete process.env.FINANCIAL_DATA_PATH; else process.env.FINANCIAL_DATA_PATH = envBackup; };
  try { require(path.join(appDir, 'main.js')); } finally { Module._load = origLoad; }  // the fake setTimeout stays installed so we can see the 3-second close fallback
  return { restoreEnv, base, docs, sent, ipc, timers, opened, electron, winHandlers, wcHandlers, closes: () => ({ closeCalls, closedNow }) };
}
const tick = () => new Promise(r => setImmediate(r));
const good = (k) => JSON.stringify({ accounts: { vault: 1 }, transactions: Array.from({ length: k === undefined ? 3 : k }, (_, i) => ({ id: 'a' + i, amount: i })), settings: {} });
async function start(c) { await tick(); await tick(); c.restoreEnv(); c.wcHandlers['did-finish-load'](); }
const last = (c, ch) => { const m = c.sent.filter(x => x[0] === ch); return m.length ? m[m.length - 1][1] : null; };

(async () => {
  // ---------- L2: normal start ----------
  let data = path.join(root, 'real1.json'); fs.writeFileSync(data, good(4));
  let c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + data + '\n' });
  await start(c);
  let m = last(c, 'initial-data');
  check('L2 good file: initial-data sent with the file text', m && m.path === data && JSON.parse(m.data).transactions.length === 4);
  check('L2 good file: no load-problem sent', last(c, 'load-problem') === null);
  check('L2 good file: a startup backup was made', fs.existsSync(path.join(path.dirname(data), 'backups')) && fs.readdirSync(path.join(path.dirname(data), 'backups')).length === 1);
  check('L2 window opened with context isolation, no node integration', c.electron.BrowserWindow.last.opts.webPreferences.contextIsolation === true && c.electron.BrowserWindow.last.opts.webPreferences.nodeIntegration === false);
  let r = await c.ipc['save-data']({}, good(5));
  check('L2 save-data writes the file', r.ok === true && JSON.parse(fs.readFileSync(data, 'utf8')).transactions.length === 5);
  r = await c.ipc['save-data']({}, '');
  check('L2 save-data refuses empty text, file intact', r.ok === false && JSON.parse(fs.readFileSync(data, 'utf8')).transactions.length === 5);
  r = await c.ipc['save-data']({}, JSON.stringify({ transactions: [] }));
  check('L2 save-data refuses to erase all transactions', r.ok === false && /erase/.test(r.error));
  r = await c.ipc['get-app-info']();
  check('L2 get-app-info reports path, state, version', r.path === data && r.state === 'ready' && r.version === '9.9.9');

  // ---------- L2: corrupt file ----------
  fs.mkdirSync(path.join(root, 'badd')); const bad = path.join(root, 'badd', 'bad.json'); fs.writeFileSync(bad, '{"transactions": [ {"id":');
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + bad + '\n' });
  await start(c);
  m = last(c, 'load-problem');
  check('L2 corrupt file: load-problem sent, no initial-data', m && m.state === 'corrupt' && m.path === bad && last(c, 'initial-data') === null);
  r = await c.ipc['save-data']({}, good(9));
  check('L2 corrupt file: save refused and file byte-identical', r.ok === false && fs.readFileSync(bad, 'utf8') === '{"transactions": [ {"id":');
  r = await c.ipc['create-new-file']({}, good(0));
  check('L2 corrupt file: create-new-file refused', r.ok === false && fs.readFileSync(bad, 'utf8') === '{"transactions": [ {"id":');
  check('L2 corrupt file: no backup folder invented', !fs.existsSync(path.join(root, 'badd', 'backups')));

  // ---------- L2: missing file ----------
  const gone = path.join(root, 'nothing-here', 'f.json');
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + gone + '\n' });
  await start(c);
  m = last(c, 'load-problem');
  check('L2 missing file: load-problem(missing) sent, NOTHING created', m && m.state === 'missing' && !fs.existsSync(gone) && !fs.existsSync(path.dirname(gone)));
  r = await c.ipc['save-data']({}, good(1));
  check('L2 missing file: save refused, still nothing created', r.ok === false && !fs.existsSync(gone));
  r = await c.ipc['create-new-file']({}, good(0));
  check('L2 missing file: create-new-file makes it, then saving works', r.ok === true && (await c.ipc['save-data']({}, good(2))).ok === true && JSON.parse(fs.readFileSync(gone, 'utf8')).transactions.length === 2);

  // ---------- L2: where the path comes from ----------
  c = setupCase({});
  await start(c);
  m = last(c, 'load-problem');
  check('L2 no .env, no variable: falls back to Documents folder, reports missing, creates nothing', m && m.state === 'missing' && m.path === path.join(c.docs, 'FinancialTracker', 'financial-tracker-data.json') && !fs.existsSync(path.join(c.docs, 'FinancialTracker')));
  const stale = path.join(root, 'stale.json'); fs.writeFileSync(stale, good(1));
  data = path.join(root, 'right.json'); fs.writeFileSync(data, good(6));
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + data + '\n', sysEnv: stale });
  await start(c);
  check('L2 .env beats a stale Windows variable (lesson 12)', last(c, 'initial-data').path === data);
  c = setupCase({ sysEnv: stale });
  await start(c);
  check('L2 Windows variable used when .env has none', last(c, 'initial-data').path === stale);

  // ---------- L2: FORGE keeps its settings in shared\.env ----------
  const sh = path.join(root, 'sh.json'); fs.writeFileSync(sh, good(11));
  c = setupCase({ sharedEnvLine: 'ANTHROPIC_API_KEY=abc\nFINANCIAL_DATA_PATH=' + sh + '\n' });
  await start(c);
  check('L2 shared\\.env is read (where ASSET keeps FINANCIAL_DATA_PATH)', last(c, 'initial-data') && last(c, 'initial-data').path === sh);
  c = setupCase({ sharedEnvLine: 'FINANCIAL_DATA_PATH=' + sh + '\n', envLine: 'FINANCIAL_DATA_PATH=' + data + '\n' });
  await start(c);
  check('L2 shared\\.env wins over a root .env', last(c, 'initial-data').path === sh);
  c = setupCase({ sharedEnvLine: 'GEMINI_API_KEY=x\n', envLine: 'FINANCIAL_DATA_PATH=' + data + '\n' });
  await start(c);
  check('L2 shared\\.env without the setting -> root .env is used', last(c, 'initial-data').path === data);
  c = setupCase({ sharedEnvLine: 'FINANCIAL_DATA_PATH=' + sh + '\n', sysEnv: stale });
  await start(c);
  check('L2 shared\\.env beats a stale Windows variable', last(c, 'initial-data').path === sh);

  // ---------- L2: --data-file launch option ----------
  const viaArg = path.join(root, 'viaarg.json'); fs.writeFileSync(viaArg, good(7));
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + data + '\n', argv: ['--data-file', viaArg] });
  await start(c);
  check('L2 --data-file <path> beats .env', last(c, 'initial-data').path === viaArg);
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + data + '\n', argv: ['--data-file=' + viaArg] });
  await start(c);
  check('L2 --data-file=<path> form works', last(c, 'initial-data').path === viaArg);
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + data + '\n', argv: ['--data-file'] });
  await start(c);
  check('L2 --data-file with no value is ignored (falls back to .env)', last(c, 'initial-data').path === data);
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + data + '\n', argv: ['--data-file=', '--other'] });
  await start(c);
  check('L2 empty --data-file= is ignored', last(c, 'initial-data').path === data);
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + data + '\n', argv: ['--data-file', path.join(root, 'no', 'such.json')] });
  await start(c);
  check('L2 --data-file pointing at a missing file -> missing screen, the .env file is NOT used instead', last(c, 'load-problem') && last(c, 'load-problem').state === 'missing' && last(c, 'initial-data') === null);

  // ---------- L2: choosing another file ----------
  data = path.join(root, 'cur.json'); fs.writeFileSync(data, good(2));
  const other = path.join(root, 'other.json'); fs.writeFileSync(other, good(8));
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + data + '\n' });
  await start(c);
  c.electron._dialog = { canceled: true, filePaths: [] };
  r = await c.ipc['load-file']();
  check('L2 load-file cancelled -> canceled, session unchanged', r.ok === false && r.canceled === true && (await c.ipc['save-data']({}, good(3))).ok === true);
  c.electron._dialog = { canceled: false, filePaths: [bad] };
  r = await c.ipc['load-file']();
  check('L2 load-file with a corrupt file -> problem, old session still saves to the OLD file', r.ok === false && r.problem && r.problem.state === 'corrupt' && (await c.ipc['save-data']({}, good(4))).ok === true && JSON.parse(fs.readFileSync(data, 'utf8')).transactions.length === 4 && fs.readFileSync(bad, 'utf8') === '{"transactions": [ {"id":');
  c.electron._dialog = { canceled: false, filePaths: [other] };
  r = await c.ipc['load-file']();
  check('L2 load-file with a good file switches, saves go to the new file only', r.ok === true && JSON.parse(r.data).transactions.length === 8 && (await c.ipc['save-data']({}, good(9))).ok && JSON.parse(fs.readFileSync(other, 'utf8')).transactions.length === 9 && JSON.parse(fs.readFileSync(data, 'utf8')).transactions.length === 4);
  // recovery from a problem start
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + bad + '\n' });
  await start(c);
  c.electron._dialog = { canceled: false, filePaths: [other] };
  r = await c.ipc['load-file']();
  check('L2 problem start recovers by choosing a good file', r.ok === true && (await c.ipc['save-data']({}, good(10))).ok === true);

  // ---------- L2: import, external, backups folder ----------
  c.electron._dialog = { canceled: false, filePaths: [bad] };
  r = await c.ipc['import-file']();
  check('L2 import-file of a corrupt file -> ok:false, no throw', r.ok === false && typeof r.error === 'string');
  c.electron._dialog = { canceled: false, filePaths: [other] };
  r = await c.ipc['import-file']();
  check('L2 import-file of a good file returns its text', r.ok === true && JSON.parse(r.data).transactions.length === 10);
  c.electron._dialog = { canceled: true, filePaths: [] };
  check('L2 import-file cancelled', (await c.ipc['import-file']()).ok === false);
  await c.ipc['open-external']({}, 'https://example.com'); await c.ipc['open-external']({}, 'file:///C:/Windows/system32/calc.exe'); await c.ipc['open-external']({}, 'javascript:alert(1)'); await c.ipc['open-external']({}, undefined); await c.ipc['open-external']({}, { toString() { return 'https://x' } });
  check('L2 open-external opens https only', c.opened.filter(x => x.startsWith('EXT')).join('|') === 'EXT https://example.com');
  c.opened.length = 0;
  check('L2 open-backups-folder opens the backups folder', (await c.ipc['open-backups-folder']()) === '' && c.opened[0] === path.join(path.dirname(other), 'backups'));
  c.opened.length = 0; c.electron._openPathResult = 'Failed to open';
  await c.ipc['open-backups-folder']();
  check('L2 no backups folder yet -> opens the data folder instead', c.opened.length === 2 && c.opened[1] === path.dirname(other));

  // ---------- L2: closing the window ----------
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + data + '\n' });
  await start(c);
  const win = c.electron.BrowserWindow.last;
  win.close();
  check('L2 closing is held back and the page is asked to save first', c.closes().closedNow === 0 && c.sent.some(x => x[0] === 'flush-request'));
  await c.ipc['flush-done']();
  check('L2 once the page says it is done, the window really closes', c.closes().closedNow === 1);
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + data + '\n' });
  await start(c);
  c.electron.BrowserWindow.last.close();
  const fallback = c.timers.find(t => t.ms === 3000);
  check('L2 a 3-second fallback timer exists (never stuck open)', !!fallback);
  fallback.fn();
  check('L2 fallback closes the window if the page never answers', c.closes().closedNow === 1);

  // ---------- L4 sustained ----------
  data = path.join(root, 'sust.json'); fs.writeFileSync(data, good(1));
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + data + '\n' });
  await start(c);
  let ok = 0; for (let i = 0; i < 200; i++) { if ((await c.ipc['save-data']({}, good(i + 1))).ok) ok++; }
  check('L4 200 saves through the real handler all ok', ok === 200 && JSON.parse(fs.readFileSync(data, 'utf8')).transactions.length === 200);
  const all = await Promise.all(Array.from({ length: 50 }, (_, i) => c.ipc['save-data']({}, good(300 + i))));
  check('L4 50 saves fired at once: all ok, file valid', all.every(x => x.ok) && JSON.parse(fs.readFileSync(data, 'utf8')).transactions.length >= 300);
  check('L4 backups stay capped', fs.readdirSync(path.join(path.dirname(data), 'backups')).length <= 30);
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + bad + '\n' });
  await start(c);
  let refused = 0; for (let i = 0; i < 200; i++) { if (!(await c.ipc['save-data']({}, good(i + 1))).ok) refused++; }
  check('L4 200 saves against a corrupt file all refused, file untouched', refused === 200 && fs.readFileSync(bad, 'utf8') === '{"transactions": [ {"id":');

  // ---------- L5 extreme ----------
  c = setupCase({ envLine: 'FINANCIAL_DATA_PATH=' + data + '\n' });
  for (const h of ['save-data', 'create-new-file', 'load-file', 'import-file', 'open-backups-folder', 'get-app-info', 'open-external']) check('L5 handler ' + h + ' registered before the window loads', typeof c.ipc[h] === 'function' || h === 'flush-done');
  await tick(); await tick(); c.restoreEnv();
  for (const badArg of [undefined, null, 5, {}, [], '   ', 'undefined', 'null']) {
    const x = await c.ipc['save-data']({}, badArg);
    check('L5 save-data(' + JSON.stringify(badArg) + ') refused without throwing', x.ok === false);
  }
  r = await c.ipc['save-data']({}, good(2));
  check('L5 save before the page finished loading is refused (session not opened), nothing written', r.ok === false);
  const before = fs.readFileSync(data, 'utf8');
  check('L5 data file unchanged by all of that', before.length > 10 && JSON.parse(before).transactions.length >= 300);
  c.wcHandlers['did-finish-load'](); c.wcHandlers['did-finish-load']();
  check('L5 page reloading twice just re-sends the data', c.sent.filter(x => x[0] === 'initial-data').length === 2);
  const win2 = c.electron.BrowserWindow.last;
  for (let i = 0; i < 20; i++) win2.close();
  check('L5 20 rapid close attempts never close before the page answers', c.closes().closedNow === 0);

  console.log(failed === 0 ? passed + '/' + passed + ' passed' : passed + '/' + (passed + failed) + ' passed, ' + failed + ' FAILED');
  fs.rmSync(root, { recursive: true, force: true });
  process.exit(failed === 0 ? 0 : 1);
})().catch(e => { console.log('TEST CRASHED: ' + e.stack); process.exit(2); });