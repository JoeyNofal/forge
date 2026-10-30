// Run:  node pagev2.test.js     (needs jsdom, like renderer.test.js)
// The REAL index.html in a simulated browser, given a v2 file: balances shown, migration row collapsed,
// and NOTHING is ever saved. A v1 file must still load and save exactly as before.
const fs = require('fs'), path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
const M = require('./migrate.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const rd = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
let html = rd('index.html');
for (const f of ['dates.js', 'bills.js', 'ledger.js', 'v2view.js']) html = html.replace('<script src="' + f + '"></script>', () => '<script>' + rd(f) + '</script>');
html = html.replace(/<script[^>]*\bsrc=[^>]*><\/script>/g, '');
const tick = () => new Promise(r => setImmediate(r));
const tx = (accountId, date, amount, balance, extra) => Object.assign({ id: accountId + '-' + date + '-' + amount, accountId, date, description: 'd ' + date, amount, balance, type: 'transaction' }, extra || {});
// old file: VAULT has a typed-balance typo (-> one migration adjustment), FREEDOM card owes 40
const old = { accounts: {}, settings: {}, paychecks: [], fixedExpenses: [], transactions: [
  tx('vault', '2026-03-01', 1000, 1000), tx('vault', '2026-03-02', -100, 950),
  tx('cc', '2026-03-03', 40, 40) ] };
const v2 = M.convert(old, { today: '2026-10-29' }).data;

function makePage() {
  const timers = new Map(); let tid = 1; const errors = [];
  const api = { saved: [], handlers: {}, saveData: async (j) => { api.saved.push(j); return { ok: true }; }, createNewFile: async () => ({ ok: true }), loadFile: async () => ({ ok: false, canceled: true }), importFile: async () => ({ ok: false }), openBackupsFolder: async () => '', getAppInfo: async () => ({}), openExternal: async () => {}, flushDone: () => Promise.resolve(),
    onInitialData: (cb) => { api.handlers.initial = cb; }, onLoadProblem: (cb) => { api.handlers.problem = cb; }, onFlushRequest: (cb) => { api.handlers.flush = cb; } };
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/', beforeParse(w) {
    w.electronAPI = api; w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {}; w.ExcelJS = {};
    w.setTimeout = (fn, ms) => { const id = tid++; timers.set(id, { fn, ms }); return id; }; w.clearTimeout = (id) => { timers.delete(id); };
    w.HTMLCanvasElement.prototype.getContext = () => null; } });
  const w = dom.window, App = w.eval('App'), Views = w.eval('Views');
  const toasts = []; App.showToast = (m) => { toasts.push(m); };
  return { w, App, Views, api, toasts, errors, timers, $: (id) => w.document.getElementById(id) };
}

(async () => {
  // L1 static
  check('L1 the page loads ledger.js and v2view.js, and the package ships v2view.js', rd('index.html').includes('<script src="ledger.js"></script>') && rd('index.html').includes('<script src="v2view.js"></script>') && /"v2view\.js"/.test(rd('package.json')));

  // L2/L3 a v2 file opens read-only with the right numbers
  const p = makePage(); await tick();
  p.api.handlers.initial({ path: 'C:\\x\\converted-v2.json', data: JSON.stringify(v2) }); await tick();
  const A = p.App.data.accounts;
  check('balances equal the old page: VAULT 950, FREEDOM owed 40', A.vault === 950 && A.cc === 40, JSON.stringify(A));
  check('v2 data is flagged read-only and the indicator says so', p.App.data._v2ReadOnly === true && /entries only/.test(p.$('save-indicator').textContent), p.$('save-indicator').textContent);
  check('migration entry is not in the normal transaction list', p.App.data.transactions.every(t => t.type !== 'migration_adjustment') && p.App.data.migrationEntries.length === 1);
  p.App.currentView = 'ledgers'; p.Views.ledgers.currentAccount = 'vault'; p.App.renderCurrentView();
  const body = () => p.$('view-container').textContent;
  check('Ledgers: a collapsed "Migration adjustment" row is shown, entry details hidden', /Migration adjustment/.test(body()) && /click to show/.test(body()) && !p.w.document.querySelector('.migration-entry'));
  check('Ledgers: the normal rows still show', /Mar 1|2026/.test(body()) && p.w.document.querySelectorAll('.txn-check').length === 2);
  p.$('migration-row').click(); await tick();
  check('clicking the row shows the entry; clicking again hides it', !!p.w.document.querySelector('.migration-entry') && /click to hide/.test(body()));
  p.$('migration-row').click(); await tick();
  check('hidden again', !p.w.document.querySelector('.migration-entry'));
  for (const v of ['dashboard', 'inputs', 'paychecks', 'forecast', 'groceries', 'credit', 'settings']) { p.App.currentView = v; try { p.App.renderCurrentView(); } catch (e) { check('view ' + v + ' renders on a v2 file', false, e.message); } }
  check('all other pages render without errors', p.errors.length === 0, p.errors.join(' | '));

  // L4/L5 nothing can ever be saved from a v2 file
  p.App.dirty = true; p.App.scheduleSave(); await p.App.saveFile(); await p.App.flushNow();
  for (const t of [...p.timers.values()]) await t.fn();
  check('edit, save, flush and every pending timer: nothing was written', p.api.saved.length === 0, 'saves: ' + p.api.saved.length);
  check('the user is told it is read-only', p.toasts.some(m => /not saved/i.test(m)));

  // L2 v1 file still loads and saves exactly as before
  const q = makePage(); await tick();
  q.api.handlers.initial({ path: 'C:\\x\\old.json', data: JSON.stringify(old) }); await tick();
  check('v1 file: not read-only, balances come from the typed balances', !q.App.data._v2ReadOnly && q.App.data.accounts.vault === 950 && q.App.data.accounts.cc === 40);
  q.App.scheduleSave(); await tick(); for (const t of [...q.timers.values()]) await t.fn();
  check('v1 file: saving still works (one save, no v2 flag in it)', q.api.saved.length === 1 && !/_v2ReadOnly|migrationEntries/.test(q.api.saved[0]));

  // L5 a v2 file with junk in it must not break the page
  const j = makePage(); await tick();
  const junk = Object.assign({}, v2, { transactions: v2.transactions.concat([null, 'x', { accountId: 'vault' }, { accountId: 'nope', date: '2026-01-01', amountCents: 5 }]) });
  let threw = false; try { j.api.handlers.initial({ path: 'C:\\x\\junk.json', data: JSON.stringify(junk) }); await tick(); } catch (e) { threw = true; }
  check('junk entries inside a v2 file do not break loading', !threw && j.App.data.accounts.vault === 950 && j.errors.length === 0, j.errors.join(' | '));
  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();