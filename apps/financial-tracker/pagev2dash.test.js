// Run:  node pagev2dash.test.js     (needs jsdom, like renderer.test.js)
// The REAL index.html in a simulated browser: the Dashboard cards and alerts follow the file's real accounts (renamed, added, closed).
// Old (v1) files still show the fixed seven accounts.
const fs = require('fs'), path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
const M = require('./migrate.js'), L = require('./ledger.js'), FD = require('./dates.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const rd = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
let html = rd('index.html');
for (const f of ['dates.js', 'bills.js', 'ledger.js', 'v2view.js', 'settingscheck.js']) html = html.replace('<script src="' + f + '"></script>', () => '<script>' + rd(f) + '</script>');
html = html.replace(/<script[^>]*\bsrc=[^>]*><\/script>/g, '');
const tick = () => new Promise(r => setImmediate(r));
const tx = (accountId, date, amount, balance, extra) => Object.assign({ id: accountId + '-' + date + '-' + amount, accountId, date, description: 'd ' + date + ' ' + amount, amount, balance, type: 'transaction' }, extra || {});
const old = { accounts: {}, settings: {}, paychecks: [], fixedExpenses: [], transactions: [ tx('vault', '2026-03-01', 1000, 1000), tx('vault', '2026-03-02', -100, 950), tx('cc', '2026-03-03', 40, 40) ] };
const v2 = M.convert(old, { today: '2026-10-29' }).data;

function makePage() {
  const timers = new Map(); let tid = 1; const errors = [];
  const api = { saved: [], handlers: {}, saveResult: () => ({ ok: true }), saveData: async (j) => { api.saved.push(j); const r = api.saveResult(j); if (r instanceof Error) throw r; return r; }, createNewFile: async () => ({ ok: true }), loadFile: async () => ({ ok: false, canceled: true }), importFile: async () => ({ ok: false }), openBackupsFolder: async () => '', getAppInfo: async () => ({}), openExternal: async () => {}, flushDone: () => Promise.resolve(),
    onInitialData: (cb) => { api.handlers.initial = cb; }, onLoadProblem: (cb) => { api.handlers.problem = cb; }, onFlushRequest: (cb) => { api.handlers.flush = cb; } };
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/', beforeParse(w) {
    w.electronAPI = api; w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {}; w.ExcelJS = {};
    w.setTimeout = (fn, ms) => { const id = tid++; timers.set(id, { fn, ms }); return id; }; w.clearTimeout = (id) => { timers.delete(id); };
    w.HTMLCanvasElement.prototype.getContext = () => null; } });
  const w = dom.window, App = w.eval('App'), Views = w.eval('Views');
  const toasts = []; App.showToast = (m) => { toasts.push(m); };
  const $ = (id) => w.document.getElementById(id);
  const open = async (file, view) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(file) }); await tick(); App.currentView = view || 'inputs'; App.renderCurrentView(); };
  const lastSaved = () => JSON.parse(api.saved[api.saved.length - 1]);
  return { w, App, Views, api, toasts, errors, $, open, lastSaved };
}

(async () => {
  const TODAY = FD.todayStr(), START = '2026-10-29';
  const page = async (file, view) => { const p = makePage(); await tick(); await p.open(file, view || 'dashboard'); return p; };
  const txt = (el) => el.textContent.replace(/\s+/g, ' ').trim();
  const cards = (p) => [...p.w.document.querySelectorAll('.balance-card')].map(c => ({ label: txt(c.querySelector('.label')), amount: c.querySelector('.amount') ? txt(c.querySelector('.amount')) : '', amountClass: c.querySelector('.amount') ? c.querySelector('.amount').className : '', sub: c.querySelector('.sub-label') ? txt(c.querySelector('.sub-label')) : '', badge: c.querySelector('.badge') ? txt(c.querySelector('.badge')) : '' }));
  const labels = (p) => cards(p).map(c => c.label);
  const alerts = (p) => [...p.w.document.querySelectorAll('.alert-chip')].map(e => txt(e));
  const withAcct = (file, o) => L.addAccount(file, Object.assign({ date: START, makeId: () => o.id }, o)).data;

  // L2 default v2 file: the same cards as the old page
  const oldLabels = ['VAULT', 'FLEX', 'FREEDOM (Chase)', 'SAVOR (Capital One)', 'BREX Loan to friend', 'Car Loan', 'Credit Scores'];
  let p = await page(v2);
  check('v2 with the default accounts shows exactly the old set of cards, in the old order', JSON.stringify(labels(p)) === JSON.stringify(oldLabels), JSON.stringify(labels(p)));
  const oldFile = { accounts: { vault: 0, flex: 0, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 }, settings: {}, paychecks: [], fixedExpenses: [], transactions: [ tx('vault', '2026-03-01', 1000, 1000), tx('cc', '2026-03-03', 40, 40) ] };
  const p1 = await page(oldFile);
  check('v1 (old) file: the very same cards', JSON.stringify(labels(p1)) === JSON.stringify(oldLabels), JSON.stringify(labels(p1)));
  check('v1: the old FREEDOM alert is still there', alerts(p1).some(a => /FREEDOM has a balance — \$40\.00/.test(a)), JSON.stringify(alerts(p1)));

  // L2 renamed, closed, added
  let f = withAcct(v2, { id: 'disc', name: 'Discover', kind: 'credit_card', owedCents: 25000 });
  f = withAcct(f, { id: 'stu', name: 'Student Loan', kind: 'loan', owedCents: 100000 });
  f = L.renameAccount(f, 'cc', 'Chase Freedom').data;
  f = L.renameAccount(f, 'car_loan', 'Auto Loan').data;
  f = L.closeAccount(f, 'brex', TODAY).data;
  p = await page(f);
  check('the cards follow the file: renamed cards use the new name, the closed BREX card is gone, added accounts come after the Car Loan card', JSON.stringify(labels(p)) === JSON.stringify(['VAULT', 'FLEX', 'Chase Freedom', 'SAVOR (Capital One)', 'Auto Loan', 'Discover', 'Student Loan', 'Credit Scores']), JSON.stringify(labels(p)));
  const disc = cards(p).find(c => c.label === 'Discover'), stu = cards(p).find(c => c.label === 'Student Loan');
  check('an added credit card: amount owed in red, "Credit card", badge "Balance owing"', disc.amount === '$250.00' && /neg/.test(disc.amountClass) && disc.sub === 'Credit card' && disc.badge === 'Balance owing', JSON.stringify(disc));
  check('an added loan: "Remaining balance"', stu.amount === '$1,000.00' && stu.sub === 'Remaining balance' && stu.badge === 'Balance owing', JSON.stringify(stu));
  check('alerts: the added card with a balance gets one, under its real name; the renamed card too; a loan gets none', alerts(p).some(a => a === '◎ Discover has a balance — $250.00') && alerts(p).some(a => /^◎ Chase Freedom has a balance/.test(a)) && !alerts(p).some(a => /Student Loan/.test(a)) && !alerts(p).some(a => /FREEDOM has/.test(a)), JSON.stringify(alerts(p)));

  // L2 paid off
  let g = L.correctBalances(f, [{ accountId: 'disc', balanceCents: 0 }], TODAY, { makeId: () => 'fix1' }).data;
  p = await page(g);
  const d2 = cards(p).find(c => c.label === 'Discover');
  check('a card paid down to 0: green "Paid off", no alert', d2.badge === 'Paid off' && /pos/.test(d2.amountClass) && !alerts(p).some(a => /Discover/.test(a)), JSON.stringify(d2));

  // L2 reopen brings the card back
  const back = L.reopenAccount(f, 'brex').data;
  p = await page(back);
  check('reopening BREX brings its card back', labels(p).includes('BREX Loan to friend'));

  // L5 odd names
  let h = L.renameAccount(f, 'disc', '<img src=x onerror=window.PWNED=1>').data;
  h = L.renameAccount(h, 'cc', '<b>Chase</b> "Free\'dom"').data;
  h = L.renameAccount(h, 'car_loan', '<i>Auto</i>').data;
  p = await page(h);
  check('odd names are shown as plain text in cards and alerts (no element made from them, nothing runs)', !p.w.document.querySelector('.balance-card img, .balance-card b, .balance-card i, .alert-chip img, .alert-chip b') && labels(p).includes('<img src=x onerror=window.PWNED=1>') && labels(p).includes('<b>Chase</b> "Free\'dom"') && labels(p).includes('<i>Auto</i>') && alerts(p).some(a => a.includes('<img src=x onerror=window.PWNED=1> has a balance')) && p.w.PWNED === undefined, JSON.stringify(labels(p)));

  // L2 a file with the credit-card accounts missing entirely does not break the page
  const bare = JSON.parse(JSON.stringify(v2)); bare.accounts = bare.accounts.filter(a => !['cc', 'cc2', 'brex', 'car_loan'].includes(a.id)); bare.transactions = bare.transactions.filter(t => !['cc', 'cc2', 'brex', 'car_loan'].includes(t.accountId));
  p = await page(bare);
  check('a v2 file without those four accounts shows only VAULT, FLEX and the scores card, and no page error', JSON.stringify(labels(p)) === JSON.stringify(['VAULT', 'FLEX', 'Credit Scores']) && p.errors.length === 0, JSON.stringify(labels(p)) + p.errors.join('|'));

  check('no page errors anywhere', [p1].every(x => x.errors.length === 0) && p.errors.length === 0);
  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();