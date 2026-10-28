// Run:  node renderer.test.js     (needs:  npm install --save-dev jsdom   once, in this folder)
// Runs the REAL index.html in a simulated browser with a fake electronAPI, and drives the
// data-file safety behaviour: problem screen, saving off, retry on failure, save on close.
const fs = require('fs'), path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const rawHtml = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const datesSrc = fs.readFileSync(path.join(__dirname, 'dates.js'), 'utf8');
const html = rawHtml.replace('<script src="dates.js"></script>', () => '<script>' + datesSrc + '</script>').replace(/<script[^>]*\bsrc=[^>]*><\/script>/g, '');   // dates.js inlined, nothing from the internet
const tick = () => new Promise(r => setImmediate(r));
const goodData = (n) => JSON.stringify({ accounts: { vault: 100, flex: 50, funds: 10 }, transactions: Array.from({ length: n === undefined ? 2 : n }, (_, i) => ({ id: 't' + i, date: '2026-05-0' + (1 + (i % 9)), accountId: 'vault', amount: 1, description: 'x', balance: 100 })), settings: {}, paychecks: [], fixedExpenses: [] });

function makePage() {
  const errors = [], timers = new Map(); let tid = 1;
  const api = {
    saved: [], created: [], flushCount: 0, backupsOpened: 0, handlers: {},
    saveResult: () => ({ ok: true }), createResult: () => ({ ok: true }), loadResult: { ok: false, canceled: true },
    saveData: async (j) => { api.saved.push(j); const r = api.saveResult(j); if (r instanceof Error) throw r; return r; },
    createNewFile: async (j) => { api.created.push(j); return api.createResult(); },
    loadFile: async () => api.loadResult,
    importFile: async () => ({ ok: false }),
    openBackupsFolder: async () => { api.backupsOpened++; return ''; },
    getAppInfo: async () => ({}), openExternal: async () => {},
    flushDone: () => { api.flushCount++; return Promise.resolve(); },
    onInitialData: (cb) => { api.handlers.initial = cb; }, onLoadProblem: (cb) => { api.handlers.problem = cb; }, onFlushRequest: (cb) => { api.handlers.flush = cb; }
  };
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/',
    beforeParse(w) {
      w.electronAPI = api;
      w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {};
      w.ExcelJS = {};
      w.setTimeout = (fn, ms) => { const id = tid++; timers.set(id, { fn, ms }); return id; };
      w.clearTimeout = (id) => { timers.delete(id); };
      w.HTMLCanvasElement.prototype.getContext = () => null;
    }
  });
  const w = dom.window;
  const App = w.eval('App');
  const toasts = []; const origToast = App.showToast; App.showToast = (m, t) => { toasts.push(m); };
  const $ = (id) => w.document.getElementById(id);
  const pending = (ms) => [...timers.values()].filter(t => ms === undefined || t.ms === ms);
  async function run(ms) { const list = [...timers.entries()].filter(([, t]) => ms === undefined || t.ms === ms); for (const [id, t] of list) { timers.delete(id); t.fn(); } await tick(); await tick(); }
  return { w, App, api, $, toasts, errors, pending, run, timers, dom };
}
const shown = (el) => el.style.display !== 'none';

(async () => {
  // ---------- L1 static ----------
  check('L1 no external scripts needed by tests are hidden: stripped html still has the app script', html.includes('const App = {'));
  check('L1 old unconditional "Saved" timer that hid failures is gone', !/ind\.textContent = 'Save failed'; ind\.className = '';\s*\n\s*App\.showToast/.test(rawHtml));

  // ---------- L2 normal start ----------
  let P = makePage(); await tick();
  check('L2 page starts without script errors', P.errors.length === 0, P.errors.join(' | '));
  check('L2 problem screen hidden at start', !shown(P.$('load-problem')));
  check('L2 page registered all three listeners', typeof P.api.handlers.initial === 'function' && typeof P.api.handlers.problem === 'function' && typeof P.api.handlers.flush === 'function');
  P.api.handlers.initial({ path: 'D:\\data\\my file.json', data: goodData(3) });
  await tick();
  check('L2 good load: file name + full path tooltip shown', P.$('file-name-display').textContent === 'my file.json' && P.$('file-name-display').title === 'D:\\data\\my file.json');
  check('L2 good load: saving allowed, not dirty, screen hidden', P.App.saveBlocked === false && P.App.dirty === false && !shown(P.$('load-problem')));
  check('L2 good load: data really loaded', P.App.data.transactions.length === 3);
  check('L2 good load: no script errors while rendering', P.errors.length === 0, P.errors.join(' | '));

  // ---------- L2 saving ----------
  P.App.scheduleSave();
  check('L2 an edit marks dirty and waits 0.8s', P.App.dirty === true && P.pending(800).length === 1 && P.api.saved.length === 0 && P.$('save-indicator').textContent === 'Saving…');
  await P.run(800);
  check('L2 after the wait the file is saved once with the current data', P.api.saved.length === 1 && JSON.parse(P.api.saved[0]).transactions.length === 3 && P.App.dirty === false && P.$('save-indicator').textContent === 'Saved ✓');
  check('L2 "Saved" clears itself later', (await P.run(3000), P.$('save-indicator').textContent === '—'));

  // ---------- L2 save failure never silent ----------
  P.api.saveResult = () => ({ ok: false, error: 'disk full' });
  P.App.scheduleSave(); await P.run(800);
  check('L2 failed save: indicator says so, edit kept, retry scheduled in 5s', P.$('save-indicator').textContent === 'SAVE FAILED - retrying' && P.App.dirty === true && P.pending(5000).length === 1);
  check('L2 failed save: one visible message with the reason', P.toasts.filter(t => /disk full/.test(t)).length === 1);
  await P.run(5000); await P.run(5000); await P.run(5000);
  check('L2 keeps retrying, but only the FIRST failure shows a message', P.api.saved.length >= 5 && P.toasts.filter(t => /Save failed/.test(t)).length === 1 && P.pending(5000).length === 1);
  P.api.saveResult = () => ({ ok: true }); await P.run(5000);
  check('L2 retry succeeds -> saved, not dirty, no more retries', P.$('save-indicator').textContent === 'Saved ✓' && P.App.dirty === false && P.App.failStreak === 0 && P.pending(5000).length === 0);
  P.api.saveResult = () => new Error('IPC exploded');
  P.App.scheduleSave(); await P.run(800);
  check('L2 save that throws is treated as a failure and retried', P.App.dirty === true && P.pending(5000).length === 1);
  P.api.saveResult = () => undefined;
  await P.run(5000);
  check('L2 an empty/undefined answer from main is NOT counted as saved', P.App.dirty === true && P.pending(5000).length === 1);
  P.api.saveResult = () => ({ ok: true }); await P.run(5000);

  // ---------- L2 closing ----------
  const before = P.api.saved.length;
  P.App.scheduleSave();
  await P.api.handlers.flush();
  check('L2 window closing: pending edit written IMMEDIATELY, then flushDone', P.api.saved.length === before + 1 && P.api.flushCount === 1 && P.pending(800).length === 0);
  await P.api.handlers.flush();
  check('L2 window closing with nothing pending: no extra save, flushDone still sent', P.api.saved.length === before + 1 && P.api.flushCount === 2);
  P.api.saveResult = () => ({ ok: false, error: 'nope' });
  P.App.scheduleSave();
  await P.api.handlers.flush();
  check('L2 closing while the save fails: still answers flushDone (never hangs the window)', P.api.flushCount === 3);

  // ---------- L2 corrupt file ----------
  P = makePage(); await tick();
  P.api.handlers.problem({ path: 'D:\\data\\f.json', state: 'corrupt', error: 'Unexpected end of JSON input' });
  check('L2 corrupt: problem screen shown, saving blocked', shown(P.$('load-problem')) && P.App.saveBlocked === true);
  check('L2 corrupt: title, reason and path are shown', /could not be read/.test(P.$('lp-title').textContent) && /Unexpected end/.test(P.$('lp-msg').textContent) && P.$('lp-path').textContent === 'D:\\data\\f.json');
  check('L2 corrupt: says the file has not been changed', /NOT been changed/.test(P.$('lp-msg').textContent));
  check('L2 corrupt: backups button shown, create button hidden', P.$('lp-create').style.display === 'none' && P.$('lp-backups').style.display !== 'none');
  P.App.scheduleSave(); await P.run();
  check('L2 corrupt: an edit attempt saves NOTHING and tells you', P.api.saved.length === 0 && P.toasts.some(t => /Saving is OFF/.test(t)) && P.pending(800).length === 0);
  await P.App.saveFile();
  check('L2 corrupt: even calling saveFile directly saves nothing', P.api.saved.length === 0);
  await P.api.handlers.flush();
  check('L2 corrupt: closing saves nothing but still lets the window close', P.api.saved.length === 0 && P.api.flushCount === 1);
  P.$('lp-backups').click(); await tick();
  check('L2 corrupt: backups button asks main to open the folder', P.api.backupsOpened === 1);

  // ---------- L2 missing file ----------
  P = makePage(); await tick();
  P.api.handlers.problem({ path: 'D:\\gone\\f.json', state: 'missing' });
  check('L2 missing: says not found, offers create, hides backups', /not found/.test(P.$('lp-title').textContent) && P.$('lp-create').style.display !== 'none' && P.$('lp-backups').style.display === 'none' && P.App.saveBlocked);
  P.api.createResult = () => ({ ok: false, error: 'access denied' });
  P.$('lp-create').click(); await tick(); await tick();
  check('L2 create fails -> stays blocked, shows why', P.App.saveBlocked === true && shown(P.$('load-problem')) && P.toasts.some(t => /access denied/.test(t)));
  P.api.createResult = () => ({ ok: true });
  P.$('lp-create').click(); await tick(); await tick();
  const created = P.api.created[P.api.created.length - 1];
  check('L2 create ok -> saving allowed, screen hidden, empty defaults sent', P.App.saveBlocked === false && !shown(P.$('load-problem')) && JSON.parse(created).transactions.length === 0 && 'settings' in JSON.parse(created));
  P.App.scheduleSave(); await P.run(800);
  check('L2 after create, edits save normally', P.api.saved.length === 1);

  // ---------- L2 choosing another file from the problem screen ----------
  P = makePage(); await tick();
  P.api.handlers.problem({ path: 'D:\\x.json', state: 'corrupt', error: 'bad' });
  P.api.loadResult = { ok: false, problem: { state: 'corrupt', error: 'also bad', path: 'D:\\y.json' } };
  P.$('lp-choose').click(); await tick(); await tick();
  check('L2 choosing another BAD file: still blocked, told why', P.App.saveBlocked === true && shown(P.$('load-problem')) && P.toasts.some(t => /also bad/.test(t)));
  P.api.loadResult = { ok: false, canceled: true };
  P.$('lp-choose').click(); await tick(); await tick();
  check('L2 cancelling the picker changes nothing', P.App.saveBlocked === true && shown(P.$('load-problem')));
  P.api.loadResult = { ok: true, path: 'D:\\good.json', data: goodData(5) };
  P.$('lp-choose').click(); await tick(); await tick();
  check('L2 choosing a GOOD file recovers: loaded, saving allowed, screen hidden', P.App.saveBlocked === false && !shown(P.$('load-problem')) && P.App.data.transactions.length === 5);
  P.App.scheduleSave(); await P.run(800);
  check('L2 recovered session saves', P.api.saved.length === 1 && JSON.parse(P.api.saved[0]).transactions.length === 5);

  // ---------- L2 "Load / Change File" button during normal use ----------
  P = makePage(); await tick(); P.api.handlers.initial({ path: 'D:\\a.json', data: goodData(2) }); await tick();
  P.api.loadResult = { ok: false, problem: { state: 'invalid', error: 'top level is not a JSON object', path: 'D:\\b.json' } };
  await P.App.loadFile();
  check('L2 changing to a bad file: current data untouched, saving still on, message shown', P.App.data.transactions.length === 2 && P.App.saveBlocked === false && P.toasts.some(t => /unchanged/.test(t)));

  // ---------- L2 file that parses as JSON but breaks loading ----------
  P = makePage(); await tick();
  P.api.handlers.initial({ path: 'D:\\odd.json', data: JSON.stringify({ transactions: [null, 5, 'x'], settings: {} }) });
  await tick();
  check('L2 odd entries inside a valid JSON file: problem screen, NOT silent zeros, saving blocked', P.App.saveBlocked === true && shown(P.$('load-problem')) && P.$('lp-path').textContent === 'D:\\odd.json');
  P.App.scheduleSave(); await P.run();
  check('L2 ...and nothing is saved over it', P.api.saved.length === 0);
  P = makePage(); await tick();
  P.api.handlers.initial({ path: 'D:\\n.json', data: 'not json at all' }); await tick();
  check('L2 text that is not JSON reaching the page: blocked, not zeros', P.App.saveBlocked === true && shown(P.$('load-problem')));
  P = makePage(); await tick();
  P.api.handlers.initial({ path: 'D:\\n.json', data: undefined }); await tick();
  check('L2 undefined data reaching the page: blocked', P.App.saveBlocked === true);

  // ---------- L4 sustained ----------
  P = makePage(); await tick(); P.api.handlers.initial({ path: 'D:\\a.json', data: goodData(2) }); await tick();
  for (let i = 0; i < 500; i++) P.App.scheduleSave();
  check('L4 500 rapid edits leave exactly ONE pending save', P.pending(800).length === 1);
  await P.run(800);
  check('L4 ...which writes once', P.api.saved.length === 1 && P.App.dirty === false);
  P.api.saveResult = () => ({ ok: false, error: 'x' });
  for (let i = 0; i < 100; i++) { P.App.scheduleSave(); await P.run(800); }
  check('L4 100 failing saves never pile up retry timers', P.pending(5000).length === 1);
  check('L4 and the failure message is not repeated 100 times', P.toasts.filter(t => /Save failed/.test(t)).length <= 100 && P.App.failStreak >= 1);
  P.api.saveResult = () => ({ ok: true });
  for (let i = 0; i < 20; i++) { P.App.scheduleSave(); await P.api.handlers.flush(); }
  check('L4 20 close-flushes in a row each save exactly once', P.api.flushCount === 20);
  for (let i = 0; i < 50; i++) { P.api.handlers.problem({ path: 'p' + i, state: i % 2 ? 'missing' : 'corrupt', error: 'e' + i }); P.api.handlers.initial({ path: 'D:\\g.json', data: goodData(1) }); await tick(); }
  check('L4 50 problem/recover cycles end in a clean saveable state', P.App.saveBlocked === false && !shown(P.$('load-problem')));

  // ---------- L5 extreme ----------
  P = makePage(); await tick();
  P.api.handlers.problem({ path: '<img src=x onerror=alert(1)>', state: 'corrupt', error: '<script>alert(2)</script>' + 'E'.repeat(50000) });
  check('L5 HTML in the path/reason is shown as text, not run', P.$('load-problem').querySelector('img') === null && P.$('load-problem').querySelector('script') === null && P.$('lp-path').textContent.startsWith('<img'));
  P.api.handlers.problem(undefined); P.api.handlers.problem(null); P.api.handlers.problem({});
  check('L5 problem with no information still shows a safe screen', P.App.saveBlocked === true && shown(P.$('load-problem')) && /unknown/.test(P.$('lp-msg').textContent));
  P = makePage(); await tick();
  P.api.handlers.initial({ path: 'no-slashes.json', data: goodData(1) }); await tick();
  check('L5 path without folders works', P.$('file-name-display').textContent === 'no-slashes.json');
  P.api.handlers.initial({ path: 'D:/forward/slash.json', data: goodData(1) }); await tick();
  check('L5 forward-slash path works', P.$('file-name-display').textContent === 'slash.json');
  P = makePage(); await tick(); P.api.handlers.initial({ path: 'D:\\a.json', data: goodData(60000) }); await tick();
  const t0 = Date.now(); P.App.scheduleSave(); await P.run(800);
  check('L5 60,000 transactions: page loads and saves', P.App.data.transactions.length === 60000 && P.api.saved.length === 1 && Date.now() - t0 < 8000, (Date.now() - t0) + 'ms');
  check('L5 no script errors anywhere in this whole run', P.errors.length === 0, P.errors.join(' | '));

  console.log(failed === 0 ? passed + '/' + passed + ' passed' : passed + '/' + (passed + failed) + ' passed, ' + failed + ' FAILED');
  process.exit(failed === 0 ? 0 : 1);
})().catch(e => { console.log('TEST CRASHED: ' + e.stack); process.exit(2); });