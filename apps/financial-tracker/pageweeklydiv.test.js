// Run:  node pageweeklydiv.test.js     (needs jsdom, like renderer.test.js)
// Turning a MONTH into weeks: the owner's rule is a month = 4 weeks when dividing (4.33 only when multiplying weeks up
// to a month). This checks the three places that divide: the weekly fixed cost in the Forecast, the FLEX allowance's
// grocery share, and the weekly car-loan payment on old (v1) files. Plus the Forecast's own grocery line.
const fs = require('fs'), path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
const M = require('./migrate.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const near = (a, b) => Math.abs(a - b) < 1e-9;
const rd = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
let html = rd('index.html');
for (const f of ['dates.js', 'bills.js', 'ledger.js', 'v2view.js', 'settingscheck.js', 'paycheckrec.js']) html = html.replace('<script src="' + f + '"></script>', () => '<script>' + rd(f) + '</script>');
html = html.replace(/<script[^>]*\bsrc=[^>]*><\/script>/g, '');
const tick = () => new Promise(r => setImmediate(r));
const ACC = (o) => Object.assign({ vault: 5000, flex: 300, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 }, o || {});
const old = (fixed, o) => { o = o || {}; const acc = ACC(o.acc); return { accounts: acc, settings: Object.assign({ vaultBufferMonths: 7 }, o.settings), fixedExpenses: fixed, groceries: o.groceries || {}, creditScores: [], paychecks: [],
  transactions: [{ id: 't1', accountId: 'vault', date: '2026-01-01', description: 'x', amount: acc.vault, balance: acc.vault, type: 'transaction' }].concat(acc.car_loan ? [{ id: 't2', accountId: 'car_loan', date: '2026-01-02', description: 'loan', amount: acc.car_loan, balance: acc.car_loan, type: 'transaction' }] : []).concat(acc.cc ? [{ id: 't3', accountId: 'cc', date: '2026-01-02', description: 'card', amount: acc.cc, balance: acc.cc, type: 'transaction' }] : []) }; };

function makePage() {
  const errors = [];
  const api = { handlers: {}, saveData: async () => ({ ok: true }), createNewFile: async () => ({ ok: true }), loadFile: async () => ({ ok: false, canceled: true }), importFile: async () => ({ ok: false }), openBackupsFolder: async () => '', getAppInfo: async () => ({}), openExternal: async () => {}, flushDone: () => Promise.resolve(),
    onInitialData: (cb) => { api.handlers.initial = cb; }, onLoadProblem: (cb) => { api.handlers.problem = cb; }, onFlushRequest: (cb) => { api.handlers.flush = cb; } };
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/', beforeParse(w) {
    w.electronAPI = api; w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {}; w.ExcelJS = {};
    w.setTimeout = () => 1; w.clearTimeout = () => {}; w.HTMLCanvasElement.prototype.getContext = () => null; } });
  const w = dom.window, App = w.eval('App'), Views = w.eval('Views');
  App.showToast = () => {};
  const open = async (f) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(f) }); await tick(); App.currentView = 'dashboard'; App.renderCurrentView(); };
  return { w, App, Views, errors, open };
}
const E = (id, name, amount, frequency, extra) => Object.assign({ id, name, amount, frequency }, extra || {});

(async () => {
  const src = rd('index.html');
  check('L1 no 4.33 is left in the page code (weeks per month is 4 when dividing)', !/4\.33/.test(src));

  // ---- weekly fixed cost (Forecast) ----
  let p = makePage(); await tick();
  await p.open(old([E('a', 'Rent', 1000, 'monthly')]));
  check('a monthly 1,000 expense costs 250 a week (1,000 / 4, not 230.95)', near(p.App.calc.weeklyFixedExpenses(), 250), String(p.App.calc.weeklyFixedExpenses()));
  p = makePage(); await tick();
  await p.open(old([E('a', 'Rent', 1000, 'monthly'), E('b', 'Phone', 120, 'biweekly'), E('c', 'Gym', 40, 'weekly'), E('d', 'Water', 1200, 'quarterly', { startDate: '2020-01-01' }), E('e', 'Ins', 4800, 'yearly', { startDate: '2020-01-01' })]));
  check('every frequency in one week: 250 + 60 + 40 + 100 + 100 = 550', near(p.App.calc.weeklyFixedExpenses(), 550), String(p.App.calc.weeklyFixedExpenses()));
  p = makePage(); await tick();
  await p.open(old([E('a', 'Rent', 1000, 'monthly', { endDate: '2020-01-01' }), E('b', 'Later', 800, 'monthly', { startDate: '2099-01-01' }), E('c', 'Gym', 40, 'weekly')]));
  check('ended and not-yet-started expenses are still left out of the weekly Forecast cost', near(p.App.calc.weeklyFixedExpenses(), 40), String(p.App.calc.weeklyFixedExpenses()));

  // ---- FLEX allowance ----
  const flex = async (groceries, extra, acc) => { const q = makePage(); await tick(); await q.open(old([E('f', 'Fuel', 40, 'weekly'), E('n', 'Fun', 20, 'weekly')].concat(extra || []), { groceries, acc })); return q.App.calc.flexAllowance(); };
  check('FLEX allowance: groceries 430 / 4 = 107.50 + 40 + 20 = 167.50 -> rounded up to 170 (was 160 with 4.33)', await flex({ '2026-01': 430, '2026-02': 430 }) === 170);
  check('FLEX allowance: groceries 400 / 4 = 100 + 60 = 160 exactly stays 160', await flex({ '2026-01': 400 }) === 160);
  check('FLEX allowance: card balances owed are still added (160 + 55.50 -> 220)', await flex({ '2026-01': 400 }, [], { cc: 55.5 }) === 220);
  check('FLEX allowance: no groceries recorded -> 60 -> 60', await flex({}) === 60);

  // ---- Forecast: groceries and fixed costs per week, car loan on v1 ----
  p = makePage(); await tick();
  await p.open(old([E('a', 'Rent', 1000, 'monthly')], { groceries: { '2026-01': 430 } }));
  let rows = p.Views.forecast.generate();
  check('Forecast week to week: VAULT moves by net pay - 250 fixed - 107.50 groceries (430 / 4)', near(rows[1].vault - rows[0].vault, rows[1].netPay - 250 - 107.5), String(rows[1].vault - rows[0].vault));
  check('Forecast: 52 weeks of the 250 charge = 13,000 (the cautious "4 weeks a month" effect, by design)', near(rows[51].vault - rows[0].vault, rows.slice(1).reduce((t, r) => t + r.netPay, 0) - 51 * (250 + 107.5)), '');
  p = makePage(); await tick();
  await p.open(old([], { acc: { car_loan: 5000 }, settings: { carLoanMonthlyTarget: 1500 } }));
  rows = p.Views.forecast.generate();
  check('v1 file: the car loan falls by 1,500 / 4 = 375 a week (5,000 -> 4,625 -> 4,250)', near(rows[0].carLoan, 4625) && near(rows[1].carLoan, 4250), rows[0].carLoan + ' / ' + rows[1].carLoan);
  check('v1 file: the car loan never goes below 0', rows.every(r => r.carLoan >= 0) && rows[51].carLoan === 0);
  p = makePage(); await tick();
  await p.open(M.convert(old([], { acc: { car_loan: 5000 }, settings: { carLoanMonthlyTarget: 1500 } }), { today: '2026-10-29' }).data);
  rows = p.Views.forecast.generate();
  check('v2 file: no payoff is projected (balance stays 5,000)', rows.every(r => r.carLoan === 5000), String(rows[0].carLoan));
  check('no script errors', p.errors.length === 0, p.errors.join('|'));

  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();