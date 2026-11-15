// Run:  node pagev2expensecalc.test.js     (needs jsdom, like renderer.test.js)
// The REAL page: yearly and quarterly in the expense form (a Start Date is required), and the numbers that use
// the fixed expenses: the VAULT target (monthly cost), the weekly Forecast cost, and Upcoming Bills.
const fs = require('fs'), path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const rd = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
let html = rd('index.html');
for (const f of ['dates.js', 'bills.js', 'ledger.js', 'v2view.js', 'settingscheck.js', 'paycheckrec.js']) html = html.replace('<script src="' + f + '"></script>', () => '<script>' + rd(f) + '</script>');
html = html.replace(/<script[^>]*\bsrc=[^>]*><\/script>/g, '');
const tick = () => new Promise(r => setImmediate(r));
const file = (fixed, months) => ({ accounts: { vault: 5000, flex: 300, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 }, settings: { vaultBufferMonths: months === undefined ? 7 : months },
  fixedExpenses: fixed, groceries: {}, creditScores: [], paychecks: [],
  transactions: [{ id: 't1', accountId: 'vault', date: '2026-01-01', description: 'x', amount: 5000, balance: 5000, type: 'transaction' }] });

function makePage() {
  const errors = [];
  const api = { saved: [], handlers: {}, saveData: async (j) => { api.saved.push(j); return { ok: true }; }, createNewFile: async () => ({ ok: true }), loadFile: async () => ({ ok: false, canceled: true }), importFile: async () => ({ ok: false }), openBackupsFolder: async () => '', getAppInfo: async () => ({}), openExternal: async () => {}, flushDone: () => Promise.resolve(),
    onInitialData: (cb) => { api.handlers.initial = cb; }, onLoadProblem: (cb) => { api.handlers.problem = cb; }, onFlushRequest: (cb) => { api.handlers.flush = cb; } };
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/', beforeParse(w) {
    w.electronAPI = api; w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {}; w.ExcelJS = {};
    w.setTimeout = () => 1; w.clearTimeout = () => {}; w.HTMLCanvasElement.prototype.getContext = () => null; } });
  const w = dom.window, App = w.eval('App'), Views = w.eval('Views');
  const toasts = []; App.showToast = (m, t) => { toasts.push({ m, t }); };
  const $ = (id) => w.document.getElementById(id);
  const open = async (f, view) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(f) }); await tick(); App.currentView = view || 'settings'; App.renderCurrentView(); };
  const today = () => w.eval('FTDates.todayStr()');
  const addDays = (d, n) => w.eval('FTDates.addDays')(d, n);
  return { w, App, Views, errors, toasts, $, open, today, addDays };
}
const FIX = [{ id: 'f1', name: 'Rent', amount: 1000, frequency: 'monthly' }, { id: 'f2', name: 'Fuel', amount: 40, frequency: 'weekly' }, { id: 'f3', name: 'Fun', amount: 20, frequency: 'weekly' }];

(async () => {
  let p = makePage(); await tick();
  const idx = rd('index.html');
  check('L1 the monthly cost comes from FTBills.monthlyTotal (the old per-frequency code is gone)', /FTBills\.monthlyTotal\(App\.data\.fixedExpenses, FTDates\.todayStr\(\)\)/.test(idx) && !/e\.amount \* 4\.33/.test(idx));
  check('L1 the weekly cost of quarterly/yearly bills uses 12 and 48 only (no leftover 13 or 52 lines)', /quarterly'\) return t \+ e\.amount \/ 12;/.test(idx) && /yearly'\) return t \+ e\.amount \/ 48;/.test(idx) && !/e\.amount \/ 13/.test(idx) && !/e\.amount \/ 52/.test(idx));

  // ---- the form ----
  await p.open(file(FIX.map(e => ({ ...e }))));
  p.Views.settings.openExpenseModal();
  const opts = [...p.$('ex-freq').options].map(o => o.value);
  check('the form offers monthly, biweekly, weekly, quarterly and yearly', JSON.stringify(opts) === JSON.stringify(['monthly', 'biweekly', 'weekly', 'quarterly', 'yearly']), JSON.stringify(opts));
  const visible = () => { const c = p.w.document.body.cloneNode(true); c.querySelectorAll('script').forEach(x => x.remove()); return c.textContent.replace(/\s+/g, ' '); };   // what a person can read (not the page's own code)
  check('the form says yearly/quarterly need a Start Date', /Yearly and quarterly bills are due on the Start Date's month and day, so they need a Start Date\./.test(visible()));
  const before = JSON.stringify(p.App.data.fixedExpenses);
  for (const f of ['yearly', 'quarterly']) {
    p.toasts.length = 0; p.$('ex-name').value = 'Insurance'; p.$('ex-amount').value = '600'; p.$('ex-freq').value = f; p.$('ex-start').value = '';
    p.Views.settings.saveExpense('');
    check(f + ' without a Start Date: refused with a clear message, nothing added', p.toasts.length === 1 && p.toasts[0].t === 'error' && /Start Date/.test(p.toasts[0].m) && JSON.stringify(p.App.data.fixedExpenses) === before, JSON.stringify(p.toasts));
  }
  p.toasts.length = 0; p.$('ex-name').value = 'Insurance'; p.$('ex-amount').value = '600'; p.$('ex-freq').value = 'yearly'; p.$('ex-start').value = '2026-03-15';
  p.Views.settings.saveExpense('');
  const added = p.App.data.fixedExpenses.find(e => e.name === 'Insurance');
  check('yearly with a Start Date saves (frequency and date kept)', p.toasts[0].m === 'Expense saved' && added && added.frequency === 'yearly' && added.startDate === '2026-03-15' && added.amount === 600);
  check('the list shows "yearly · from 2026-03-15"', /yearly · from 2026-03-15/.test(visible()));
  p.toasts.length = 0; p.Views.settings.openExpenseModal(); p.$('ex-name').value = 'Water'; p.$('ex-amount').value = '90'; p.$('ex-freq').value = 'quarterly'; p.$('ex-start').value = '2026-02-10';
  p.Views.settings.saveExpense('');
  check('quarterly with a Start Date saves', p.toasts[0].m === 'Expense saved' && p.App.data.fixedExpenses.some(e => e.name === 'Water' && e.frequency === 'quarterly'));
  p.toasts.length = 0; p.Views.settings.openExpenseModal(); p.$('ex-name').value = 'Gym'; p.$('ex-amount').value = '30'; p.$('ex-freq').value = 'monthly'; p.$('ex-start').value = '';
  p.Views.settings.saveExpense('');
  check('a monthly expense still needs no Start Date', p.toasts[0].m === 'Expense saved' && p.App.data.fixedExpenses.some(e => e.name === 'Gym'));
  const rentId = 'f1'; p.toasts.length = 0; p.Views.settings.openExpenseModal(rentId);
  check('editing: the frequency box shows the saved frequency, including yearly', (() => { p.Views.settings.openExpenseModal(added.id); return p.$('ex-freq').value === 'yearly'; })());
  p.$('ex-freq').value = 'quarterly'; p.$('ex-start').value = ''; p.toasts.length = 0; p.Views.settings.saveExpense(added.id);
  check('editing it to quarterly while clearing the Start Date is refused and the saved one is untouched', p.toasts[0].t === 'error' && p.App.data.fixedExpenses.find(e => e.id === added.id).frequency === 'yearly');
  check('no script errors in the form tests', p.errors.length === 0, p.errors.join('|'));

  // ---- monthly cost / VAULT target ----
  const T = p.today(), D = (n) => p.addDays(T, n);
  const target = async (fixed, months) => { const q = makePage(); await tick(); await q.open(file(fixed, months), 'dashboard'); return { q, monthly: q.App.calc.monthlyExpenses(), target: q.App.calc.vaultBufferTarget(), weekly: q.App.calc.weeklyFixedExpenses() }; };
  let r = await target(FIX.map(e => ({ ...e })), 7);
  check('rent 1,000 + 60 a week x 4.33 = 1,259.80 a month; 7 months -> 10,318.60 rounded UP to a target of 11,000', Math.abs(r.monthly - 1259.8) < 1e-9 && r.target === 11000, r.monthly + ' / ' + r.target);
  r = await target(FIX.concat([{ id: 'y', name: 'Ins', amount: 1200, frequency: 'yearly', startDate: '2020-05-01' }, { id: 'q', name: 'Water', amount: 300, frequency: 'quarterly', startDate: '2020-05-01' }]).map(e => ({ ...e })), 7);
  check('add yearly 1,200 (+100) and quarterly 300 (+100) a month -> 1,459.80', Math.abs(r.monthly - 1459.8) < 1e-9, String(r.monthly));
  r = await target(FIX.concat([{ id: 'e', name: 'Old', amount: 500, frequency: 'monthly', endDate: D(-1) }]).map(e => ({ ...e })), 7);
  check('an expense that ended yesterday is not in the target', Math.abs(r.monthly - 1259.8) < 1e-9, String(r.monthly));
  r = await target(FIX.concat([{ id: 'e', name: 'Last', amount: 500, frequency: 'monthly', endDate: T }]).map(e => ({ ...e })), 7);
  check('an expense whose last day is today still counts', Math.abs(r.monthly - 1759.8) < 1e-9, String(r.monthly));
  r = await target(FIX.concat([{ id: 'n', name: 'Soon', amount: 500, frequency: 'monthly', startDate: D(90) }]).map(e => ({ ...e })), 7);
  check('an expense that has not started yet DOES count in the target (7 x 1,759.80 + 1,500 = 13,818.60 -> 14,000)', Math.abs(r.monthly - 1759.8) < 1e-9 && r.target === 14000, r.monthly + ' / ' + r.target);
  r = await target(FIX.map(e => ({ ...e })), 0);
  check('0 months: the target is just the fixed 1,500, rounded up to 2,000', r.target === 2000, String(r.target));

  // ---- weekly forecast cost ----
  r = await target([{ id: 'y', name: 'Ins', amount: 4800, frequency: 'yearly', startDate: '2020-05-01' }, { id: 'q', name: 'Water', amount: 1200, frequency: 'quarterly', startDate: '2020-05-01' }], 7);
  check('weekly cost (a month = 4 weeks when dividing): yearly 4,800 / 48 = 100 a week, quarterly 1,200 / 12 = 100 a week', Math.abs(r.weekly - 200) < 1e-9, String(r.weekly));
  r = await target([{ id: 'y', name: 'Ins', amount: 4800, frequency: 'yearly', startDate: D(30) }], 7);
  check('weekly cost keeps its old rule: a bill that has not started is not in this week-by-week estimate', r.weekly === 0, String(r.weekly));

  // ---- upcoming bills ----
  const due = D(10), startYearAgo = (+due.slice(0, 4) - 1) + due.slice(4);
  r = await target([{ id: 'y', name: 'Car insurance', amount: 600, frequency: 'yearly', startDate: startYearAgo }, { id: 'q', name: 'Water', amount: 90, frequency: 'quarterly', startDate: startYearAgo }, { id: 'm', name: 'Far', amount: 5, frequency: 'yearly', startDate: p.addDays(startYearAgo, 100) }], 7);
  const ub = r.q.App.calc.upcoming30DayBills();
  check('Upcoming Bills lists the yearly and the quarterly bill due in 10 days, not the one 100 days away', ub.length === 2 && ub.every(b => r.q.w.eval('FTDates.toDateStr')(b.date) === due) && ub.some(b => b.name === 'Car insurance') && ub.some(b => b.name === 'Water'), JSON.stringify(ub));
  // the table lives on the Forecast page (card "Upcoming Bills", next 30 days); the Dashboard only shows an alert for bills due within 5 days
  const visibleOf = (q) => { const c = q.w.document.body.cloneNode(true); c.querySelectorAll('script').forEach(x => x.remove()); return c.textContent.replace(/\s+/g, ' '); };
  r.q.App.currentView = 'forecast'; r.q.App.renderCurrentView();
  const rows = [...r.q.w.document.querySelectorAll('.card')].filter(c => c.querySelector('.card-title') && /Upcoming Bills/.test(c.querySelector('.card-title').textContent)).flatMap(c => [...c.querySelectorAll('tbody tr')]).map(tr => tr.textContent.replace(/\s+/g, ' ').trim());
  check('the Forecast page "Upcoming Bills" table shows both rows with name, amount and the frequency word', rows.length === 2 && rows.some(t => /Car insurance/.test(t) && /\$600\.00/.test(t) && /yearly/.test(t)) && rows.some(t => /Water/.test(t) && /\$90\.00/.test(t) && /quarterly/.test(t)), JSON.stringify(rows));
  const soon = (n) => { const dd = D(n); return target([{ id: 'y', name: 'Soon yearly', amount: 70, frequency: 'yearly', startDate: (+dd.slice(0, 4) - 1) + dd.slice(4) }], 7); };
  let sn = await soon(3);
  check('Dashboard: a yearly bill due in 3 days gives the "1 bill due within 5 days" alert', /1 bill due within 5 days/.test(visibleOf(sn.q)), visibleOf(sn.q).slice(0, 200));
  sn = await soon(10);
  check('Dashboard: a yearly bill due in 10 days gives no "due within 5 days" alert (it is on the Forecast page instead)', !/due within 5 days/.test(visibleOf(sn.q)));
  check('no script errors in the calculation tests', r.q.errors.length === 0, r.q.errors.join('|'));

  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();