// Run:  node pagegroceries.test.js     (needs jsdom, like renderer.test.js)
// Groceries page: "Add to month" adds an amount to a month's total instead of replacing it.
const fs = require('fs'), path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
const M = require('./migrate.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const rd = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
let html = rd('index.html');
for (const f of ['dates.js', 'bills.js', 'ledger.js', 'v2view.js', 'settingscheck.js', 'paycheckrec.js']) html = html.replace('<script src="' + f + '"></script>', () => '<script>' + rd(f) + '</script>');
html = html.replace(/<script[^>]*\bsrc=[^>]*><\/script>/g, '');
const tick = () => new Promise(r => setImmediate(r));
const tx = (accountId, date, amount, balance) => ({ id: accountId + '-' + date, accountId, date, description: 'd ' + date, amount, balance, type: 'transaction' });
const mkOld = () => ({ accounts: {}, settings: { groceryStartYear: 2024, groceryStartMonth: 9 }, fixedExpenses: [], groceries: { '2024-09': 512.34, '2024-10': 0.1, '2024-11': 100, '2025-01': 0.14 }, creditScores: [], paychecks: [],
  transactions: [tx('vault', '2026-01-01', 5000, 5000)] });
const v2 = M.convert(mkOld(), { today: '2026-10-29' }).data;

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
  const open = async (file) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(file) }); await tick(); App.currentView = 'groceries'; App.renderCurrentView(); };
  const fire = async () => { for (const [id, t] of [...timers]) { timers.delete(id); await t.fn(); } };
  const add = (key, v) => { $('gadd-' + key).value = v; Views.groceries.add(key); };
  const last = () => JSON.parse(api.saved[api.saved.length - 1]);
  return { w, App, Views, api, toasts, errors, $, open, fire, add, last };
}

(async () => {
  for (const kind of ['v1', 'v2']) {
    const p = makePage(); await tick(); await p.open(kind === 'v1' ? mkOld() : v2);
    const G = () => p.App.data.groceries;
    check(kind + ': every month row has an "Add to month" box and button, and the header says so', /Add to month/.test(p.$('view-container').textContent) && p.Views.groceries.getMonths().every(m => !!p.$('gadd-' + m.year + '-' + String(m.month).padStart(2, '0'))) && p.w.document.querySelectorAll('button[onclick^="Views.groceries.add"]').length === p.Views.groceries.getMonths().length);
    check(kind + ': the existing total box still shows the month total', p.w.document.querySelector('input[data-key="2024-09"]').value === '512.34');

    p.add('2024-09', '100');
    check(kind + ': adding 100 to September 512.34 makes 612.34 (it adds, it does not replace)', G()['2024-09'] === 612.34, String(G()['2024-09']));
    check(kind + ': the page shows the new total and the user is told what happened', p.w.document.querySelector('input[data-key="2024-09"]').value === '612.34' && p.toasts.some(m => /Added \$100\.00 to September 2024: total now \$612\.34/.test(m)), p.toasts.join(' | '));
    check(kind + ': the add box is empty again afterwards', p.$('gadd-2024-09').value === '');
    await p.fire(); await tick();
    check(kind + ': it is saved to the file', p.api.saved.length >= 1 && p.last().groceries['2024-09'] === 612.34);
    if (kind === 'v2') check('v2: the saved file is still v2 and its entries are untouched', p.last().schemaVersion === 2 && JSON.stringify(p.last().transactions) === JSON.stringify(v2.transactions) && Array.isArray(p.last().accounts));

    p.add('2024-09', '0.01'); p.add('2024-09', '0.02');
    check(kind + ': small amounts add exactly (612.34 + 0.01 + 0.02 = 612.37)', G()['2024-09'] === 612.37, String(G()['2024-09']));
    p.add('2025-01', '0.01');
    check(kind + ': 0.14 + 0.01 is exactly 0.15 (plain decimal math gives 0.15000000000000002)', G()['2025-01'] === 0.15, String(G()['2025-01']));
    p.add('2024-10', '0.2');
    check(kind + ': 0.1 + 0.2 is exactly 0.3', G()['2024-10'] === 0.3, String(G()['2024-10']));
    const key = p.Views.groceries.getMonths().slice(-1)[0]; const k = key.year + '-' + String(key.month).padStart(2, '0');
    p.add(k, '50.5');
    check(kind + ': a month with nothing yet starts from 0 (current month: 50.50)', G()[k] === 50.5, String(G()[k]));
    check(kind + ': the Average card is redrawn right after an add and matches the new totals', p.App.calc.avgGroceries() > 0 && p.$('view-container').textContent.includes(p.App.fmt(p.App.calc.avgGroceries())));
    for (let i = 0; i < 10; i++) p.add('2024-11', '12.34');
    check(kind + ': ten adds in a row accumulate (100 + 123.40 = 223.40)', G()['2024-11'] === 223.4, String(G()['2024-11']));

    p.add('2024-11', '-23.4');
    check(kind + ': a negative amount takes money off (a refund): 223.40 - 23.40 = 200', G()['2024-11'] === 200, String(G()['2024-11']));
    const nT = p.toasts.length; p.add('2024-11', '-200.01');
    check(kind + ': taking off more than the month has is refused, total unchanged', G()['2024-11'] === 200 && /negative/.test(p.toasts[nT]), p.toasts[nT]);
    p.add('2024-11', '-200');
    check(kind + ': taking off exactly everything leaves 0', G()['2024-11'] === 0);

    const before = JSON.stringify(G());
    for (const bad of ['', '0', 'abc', '   ', '1e30', '-0']) { p.add('2024-09', bad); }
    check(kind + ': blank, zero, text and absurd amounts are refused and change nothing', JSON.stringify(G()) === before && p.toasts.filter(m => /Enter an amount to add/.test(m)).length >= 5);
    p.$('gadd-2024-09').value = '5'; p.$('gadd-2024-09').dispatchEvent(new p.w.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    check(kind + ': pressing Enter in the box adds too', G()['2024-09'] === 612.37 + 5, String(G()['2024-09']));
    p.$('gadd-2024-09').value = '5'; p.$('gadd-2024-09').dispatchEvent(new p.w.KeyboardEvent('keydown', { key: 'a', bubbles: true }));
    check(kind + ': other keys do not', G()['2024-09'] === 612.37 + 5);

    p.Views.groceries.save('2024-09', '300');
    check(kind + ': typing a whole new total in the Total box still replaces it, as before', G()['2024-09'] === 300);
    await p.fire(); await tick();
    check(kind + ': the final totals are in the saved file', p.last().groceries['2024-09'] === 300 && p.last().groceries['2024-10'] === 0.3 && p.last().groceries[k] === 50.5 && p.last().groceries['2024-11'] === 0 && p.last().groceries['2025-01'] === 0.15);
    check(kind + ': no page errors, no NaN on the page', p.errors.length === 0 && !/NaN|undefined/.test(p.$('view-container').textContent), p.errors.join(' | '));
  }
  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();