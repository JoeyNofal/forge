// Run:  node pagevaultstatus.test.js     (needs jsdom, like renderer.test.js)
// The dashboard VAULT card status. At or above YOUR target (months x monthly expenses + $1,500) it is always
// Safe, whatever the months setting is. Below the target the old ladder applies: under 2 months of expenses
// Critical, under 6 months Low, otherwise In Progress.
const fs = require('fs'), path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const rd = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
let html = rd('index.html');
for (const f of ['dates.js', 'bills.js', 'ledger.js', 'v2view.js', 'settingscheck.js', 'paycheckrec.js']) html = html.replace('<script src="' + f + '"></script>', () => '<script>' + rd(f) + '</script>');
html = html.replace(/<script[^>]*\bsrc=[^>]*><\/script>/g, '');
const tick = () => new Promise(r => setImmediate(r));
// expenses: rent 1000/month only, no groceries, so one month of expenses is exactly 1000
const file = (months) => ({ accounts: { vault: 5000, flex: 300, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 }, settings: { vaultBufferMonths: months },
  fixedExpenses: [{ id: 'f1', name: 'Rent', amount: 1000, frequency: 'monthly' }], groceries: {}, creditScores: [], paychecks: [],
  transactions: [{ id: 't1', accountId: 'vault', date: '2026-01-01', description: 'x', amount: 5000, balance: 5000, type: 'transaction' }] });

function makePage() {
  const errors = [];
  const api = { saved: [], handlers: {}, saveData: async (j) => { api.saved.push(j); return { ok: true }; }, createNewFile: async () => ({ ok: true }), loadFile: async () => ({ ok: false, canceled: true }), importFile: async () => ({ ok: false }), openBackupsFolder: async () => '', getAppInfo: async () => ({}), openExternal: async () => {}, flushDone: () => Promise.resolve(),
    onInitialData: (cb) => { api.handlers.initial = cb; }, onLoadProblem: (cb) => { api.handlers.problem = cb; }, onFlushRequest: (cb) => { api.handlers.flush = cb; } };
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/', beforeParse(w) {
    w.electronAPI = api; w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {}; w.ExcelJS = {};
    w.setTimeout = () => 1; w.clearTimeout = () => {}; w.HTMLCanvasElement.prototype.getContext = () => null; } });
  const w = dom.window, App = w.eval('App');
  App.showToast = () => {};
  const open = async (f) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(f) }); await tick(); App.currentView = 'dashboard'; App.renderCurrentView(); };
  return { w, App, errors, open };
}

(async () => {
  const p = makePage(); await tick();
  // L1 static
  const src = rd('index.html'), fn = src.slice(src.indexOf('vaultBufferStatus() {'), src.indexOf('flexAllowance() {'));
  check('L1 the Safe check comes first in vaultBufferStatus', fn.indexOf("'Safe'") > 0 && fn.indexOf("'Safe'") < fn.indexOf("'Critical'"));

  await p.open(file(7));
  const st = (vault, months) => { p.App.data.settings.vaultBufferMonths = months; p.App.data.accounts.vault = vault; return p.App.calc.vaultBufferStatus().status; };
  check('test setup: one month of expenses is exactly 1000, 7 months -> target 8500', p.App.calc.monthlyExpenses() === 1000 && (p.App.data.settings.vaultBufferMonths = 7, p.App.calc.vaultBufferTarget()) === 8500);

  // L2 default 7 months: behaviour unchanged (target 8500)
  const seven = [[0, 'Critical'], [500, 'Critical'], [1999.99, 'Critical'], [2000, 'Low'], [5999.99, 'Low'], [6000, 'In Progress'], [8499.99, 'In Progress'], [8500, 'Safe'], [20000, 'Safe']];
  for (const [v, want] of seven) check('7 months: VAULT ' + v + ' -> ' + want, st(v, 7) === want, st(v, 7));
  // L2 months 0 (target 1500): reaching it is Safe even though it is under 2 months of expenses
  for (const [v, want] of [[500, 'Critical'], [1499.99, 'Critical'], [1500, 'Safe'], [1999, 'Safe'], [3102.43, 'Safe']]) check('0 months: VAULT ' + v + ' -> ' + want, st(v, 0) === want, st(v, 0));
  // 1 month (target 2500)
  for (const [v, want] of [[1500, 'Critical'], [2000, 'Low'], [2499.99, 'Low'], [2500, 'Safe']]) check('1 month: VAULT ' + v + ' -> ' + want, st(v, 1) === want, st(v, 1));
  // a bigger target is respected too (12 months -> 13500)
  for (const [v, want] of [[8500, 'In Progress'], [13499.99, 'In Progress'], [13500, 'Safe']]) check('12 months: VAULT ' + v + ' -> ' + want, st(v, 12) === want, st(v, 12));
  check('negative VAULT is Critical', st(-50, 7) === 'Critical' && st(-50, 0) === 'Critical');

  // L3 the real dashboard card
  const card = async (months, vault) => { const q = makePage(); await tick(); const f = file(months); f.accounts.vault = vault; f.transactions[0].amount = vault; f.transactions[0].balance = vault; await q.open(f); return { q, text: [...q.w.document.querySelectorAll('.badge')].map(b => b.textContent.trim()) }; };
  let c = await card(0, 3102.43);
  check('dashboard, months 0, VAULT 3102.43: the VAULT badge says Safe (this was the reported bug)', c.text.includes('Safe') && !c.text.includes('Critical'), JSON.stringify(c.text));
  c = await card(7, 3102.43);
  check('dashboard, months 7, VAULT 3102.43: still Low (3102 is above 2 months, under 6)', c.text.includes('Low') && !c.text.includes('Safe'), JSON.stringify(c.text));
  c = await card(7, 900);
  check('dashboard, months 7, VAULT 900: Critical', c.text.includes('Critical'), JSON.stringify(c.text));
  check('no script errors', c.q.errors.length === 0, c.q.errors.join('|'));

  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();