// Run:  node pagev2carloan.test.js     (needs jsdom, like renderer.test.js)
// v2 files: the car loan is an ordinary account. The dashboard card shows just what is owed ("Paid off" at 0)
// and the Forecast table has no Car Loan column. Old (v1) files keep the progress bar, the target line and the column.
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
const tx = (accountId, date, amount, balance) => ({ id: accountId + '-' + date + '-' + amount, accountId, date, description: 'd ' + date, amount, balance, type: 'transaction' });
const ACC = { vault: 5000, flex: 300, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 };
const oldFile = (owed) => ({ accounts: { ...ACC, car_loan: owed }, settings: {}, fixedExpenses: [], groceries: {}, creditScores: [], paychecks: [],
  transactions: [tx('vault', '2026-01-01', 5000, 5000), tx('flex', '2026-09-05', 300, 300), tx('car_loan', '2026-02-01', 2500, 2500)].concat(owed === 2500 ? [] : [tx('car_loan', '2026-03-01', -2500, 0)]) });
const v1Owing = oldFile(2500), v1Paid = oldFile(0);
const v2Owing = M.convert(v1Owing, { today: '2026-10-29' }).data, v2Paid = M.convert(v1Paid, { today: '2026-10-29' }).data;

function makePage() {
  const errors = [];
  const api = { saved: [], handlers: {}, saveData: async (j) => { api.saved.push(j); return { ok: true }; }, createNewFile: async () => ({ ok: true }), loadFile: async () => ({ ok: false, canceled: true }), importFile: async () => ({ ok: false }), openBackupsFolder: async () => '', getAppInfo: async () => ({}), openExternal: async () => {}, flushDone: () => Promise.resolve(),
    onInitialData: (cb) => { api.handlers.initial = cb; }, onLoadProblem: (cb) => { api.handlers.problem = cb; }, onFlushRequest: (cb) => { api.handlers.flush = cb; } };
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/', beforeParse(w) {
    w.electronAPI = api; w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {}; w.ExcelJS = {};
    w.setTimeout = () => 1; w.clearTimeout = () => {}; w.HTMLCanvasElement.prototype.getContext = () => null; } });
  const w = dom.window, App = w.eval('App'), Views = w.eval('Views');
  App.showToast = () => {};
  const open = async (f, view) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(f) }); await tick(); App.currentView = view; App.renderCurrentView(); };
  return { w, App, Views, errors, open };
}
const txt = (el) => el.textContent.replace(/\s+/g, ' ').trim();

(async () => {
  const dash = async (f) => { const p = makePage(); await tick(); await p.open(f, 'dashboard'); const card = [...p.w.document.querySelectorAll('.balance-card')].find(c => c.querySelector('.label') && /Car Loan/.test(c.querySelector('.label').textContent)); return { p, card }; };
  const fc = async (f) => { const p = makePage(); await tick(); await p.open(f, 'forecast'); const d = p.w.document; return { p, header: [...d.querySelectorAll('.forecast-row.header > div')].map(txt), rows: [...d.querySelectorAll('.forecast-row:not(.header)')] }; };

  // dashboard card, v2
  let r = await dash(v2Owing);
  check('v2 owing 2500: the card shows what is owed and no progress bar, no Target line, no % paid off, no "Paid off"', !!r.card && /\$2,500\.00/.test(txt(r.card)) && !r.card.querySelector('.progress-bar') && !/Target|paid off|Paid off/.test(txt(r.card)), r.card && txt(r.card));
  check('v2 owing: "Remaining balance" label is kept', !!r.card && /Remaining balance/.test(txt(r.card)));
  r = await dash(v2Paid);
  check('v2 paid off (0): the card says "Paid off" and still has no bar or target', !!r.card && /Paid off/.test(txt(r.card)) && !r.card.querySelector('.progress-bar') && !/Target/.test(txt(r.card)), r.card && txt(r.card));
  check('no script errors (dashboard v2)', r.p.errors.length === 0, r.p.errors.join('|'));
  // dashboard card, v1 unchanged
  r = await dash(v1Owing);
  check('v1 owing: the old card keeps the progress bar and the "% paid off · Target" line', !!r.card && !!r.card.querySelector('.progress-bar') && /% paid off/.test(txt(r.card)) && /Target: \$1,500\.00\/mo/.test(txt(r.card)), r.card && txt(r.card));

  // forecast table
  let f = await fc(v2Owing);
  check('v2 forecast: header has 5 columns and no "Car Loan Est."', JSON.stringify(f.header) === JSON.stringify(['Wk', 'Pay Date', 'Hrs', 'Net Pay', 'VAULT Est.']), JSON.stringify(f.header));
  check('v2 forecast: 52 rows, each with 5 cells and the five-column layout class', f.rows.length === 52 && f.rows.every(x => x.children.length === 5 && x.classList.contains('five')), f.rows.length + ' rows, first has ' + (f.rows[0] && f.rows[0].children.length));
  check('v2 forecast: the header row uses the five-column layout too', f.p.w.document.querySelector('.forecast-row.header').classList.contains('five'));
  check('v2 forecast: no payoff is assumed (the loan balance stays exactly what is owed in every week)', f.p.Views.forecast.generate().every(x => x.carLoan === 2500));
  check('no script errors (forecast v2)', f.p.errors.length === 0, f.p.errors.join('|'));
  f = await fc(v1Owing);
  check('v1 forecast: still 6 columns with "Car Loan Est."', f.header.length === 6 && f.header[5] === 'Car Loan Est.' && f.rows.length === 52 && f.rows.every(x => x.children.length === 6 && !x.classList.contains('five')), JSON.stringify(f.header));
  const g = f.p.Views.forecast.generate();
  check('v1 forecast: the loan still pays down by the monthly target (declines, never below 0)', g[1].carLoan < g[0].carLoan && g.every(x => x.carLoan >= 0) && g[0].carLoan < 2500);

  // CSS
  check('L1 the five-column rule exists', /\.forecast-row\.five\s*\{\s*grid-template-columns:\s*40px 100px 80px 90px 110px;/.test(rd('index.html')));

  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();