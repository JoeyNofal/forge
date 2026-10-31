// Run:  node pagev2funds.test.js     (needs jsdom, like renderer.test.js)
// FUNDS is plain savings on a v2 file: the dashboard shows one balance (no Car Fund / Savings split)
// and the Settings page has no Car Fund boxes. v1 files keep the old split exactly as before.
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
const tx = (accountId, date, amount, balance, extra) => Object.assign({ id: accountId + '-' + date + '-' + amount, accountId, date, description: 'd ' + date + ' ' + amount, amount, balance, type: 'transaction' }, extra || {});
const mkOld = (funds) => ({ accounts: {}, settings: {}, paychecks: [], fixedExpenses: [], transactions: [ tx('vault', '2026-03-01', 1000, 1000), tx('funds', '2026-03-02', funds, funds) ] });
const mkV2 = (funds) => M.convert(mkOld(funds), { today: '2026-10-29' }).data;

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
  const $ = (id) => w.document.getElementById(id);
  const view = (v) => { App.currentView = v; App.renderCurrentView(); return $('view-container'); };
  const open = async (file) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(file) }); await tick(); };
  return { w, App, Views, api, toasts, errors, timers, $, view, open };
}
const shown = (p, id) => p.w.getComputedStyle(p.$(id)).display !== 'none';

(async () => {
  check('L1 the page hides the split only through App.v2Raw, and the settings save tolerates missing boxes', /funds-split[^>]*\$\{App\.v2Raw \? 'display:none'/.test(rd('index.html')) && /if \(document\.getElementById\('s-carmin'\)\)/.test(rd('index.html')) && /if \(document\.getElementById\('s-cartarget'\)\)/.test(rd('index.html')));

  // L2/L3 v2: one FUNDS balance
  const p = makePage(); await tick(); await p.open(mkV2(1234.56));
  let c = p.view('dashboard');
  check('v2 dashboard: FUNDS (Savings) shows its balance $1,234.56', /FUNDS \(Savings\)/.test(c.textContent) && /\$1,234\.56/.test(c.textContent));
  check('v2 dashboard: the Car Fund / Savings Fund split cards are not shown', !!p.$('funds-split') && !shown(p, 'funds-split'));
  check('v2 dashboard: no NaN or undefined anywhere', !/NaN|undefined/.test(c.textContent));
  const pn = makePage(); await tick(); await pn.open(mkV2(-50));
  c = pn.view('dashboard');
  check('v2 dashboard with a NEGATIVE FUNDS balance: shows it plainly, nothing odd (no Car Fund, no NaN)', /50\.00/.test(c.textContent) && !shown(pn, 'funds-split') && !/NaN|undefined/.test(c.textContent));
  const pz = makePage(); await tick(); await pz.open(mkV2(0));
  c = pz.view('dashboard'); check('v2 dashboard with FUNDS at 0 renders', !shown(pz, 'funds-split') && !/NaN|undefined/.test(c.textContent));

  // L2 v2 settings
  c = p.view('settings');
  check('v2 settings: no Car Fund Minimum / Target boxes, the other boxes are still there', !p.$('s-carmin') && !p.$('s-cartarget') && !/Car Fund/.test(c.textContent) && !!p.$('s-flexfloor') && !!p.$('s-carloan') && !!p.$('s-carloaninitial'));
  let threw = false; try { p.Views.settings.save(); } catch (e) { threw = e.message; }
  await tick(); for (const t of [...p.timers.values()]) await t.fn();
  check('v2 settings: Save does not crash and nothing is written to the file', threw === false && p.api.saved.length === 0, String(threw) + ' saves: ' + p.api.saved.length);
  check('v2: the Paycheck and Forecast pages (unchanged until B4) still render', (() => { try { p.view('paychecks'); p.view('forecast'); return true; } catch (e) { return false; } })());
  check('v2: no page errors', p.errors.length === 0 && pn.errors.length === 0 && pz.errors.length === 0, p.errors.concat(pn.errors, pz.errors).join(' | '));

  // L2 v1 unchanged
  const q = makePage(); await tick(); await q.open(mkOld(3200));
  c = q.view('dashboard');
  check('v1 dashboard: the Car Fund and Savings Fund cards are still shown', shown(q, 'funds-split') && /Car Fund/.test(c.textContent) && /Savings Fund/.test(c.textContent));
  c = q.view('settings');
  check('v1 settings: the Car Fund boxes are still there', !!q.$('s-carmin') && !!q.$('s-cartarget'));
  q.$('s-carmin').value = '1200'; q.$('s-cartarget').value = '2000';
  q.Views.settings.save(); await tick(); for (const t of [...q.timers.values()]) await t.fn();
  const s1 = q.api.saved.length ? JSON.parse(q.api.saved[0]) : null;
  check('v1 settings: Save still works and keeps the Car Fund values (once)', q.api.saved.length === 1 && s1.settings.carFundMinimum === 1200 && s1.settings.carFundTarget === 2000, JSON.stringify(s1 && s1.settings));
  check('v1: no page errors', q.errors.length === 0, q.errors.join(' | '));
  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();