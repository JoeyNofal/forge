// Run:  node pagev2accounts.test.js     (needs jsdom, like renderer.test.js)
// The REAL index.html in a simulated browser: the account lists follow the file's real accounts (renamed, added, closed).
// Old (v1) files still show the fixed seven accounts.
const fs = require('fs'), path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
const M = require('./migrate.js'), L = require('./ledger.js'), FD = require('./dates.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const rd = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
let html = rd('index.html');
for (const f of ['dates.js', 'bills.js', 'ledger.js', 'v2view.js']) html = html.replace('<script src="' + f + '"></script>', () => '<script>' + rd(f) + '</script>');
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
  let f = L.addAccount(v2, { name: 'Discover', kind: 'credit_card', owedCents: 25000, date: START, makeId: () => 'disc' }).data;
  f = L.renameAccount(f, 'cc', 'Chase Freedom').data;
  f = L.closeAccount(f, 'car_loan', TODAY).data;
  const openIds = ['vault', 'flex', 'funds', 'cc', 'cc2', 'brex', 'disc'];
  const page = async (file, view) => { const p = makePage(); await tick(); await p.open(file, view); return p; };
  const txt = (el) => el.textContent.replace(/\s+/g, ' ').trim();

  // L2 Update Balances boxes
  let p = await page(f, 'dashboard');
  const boxIds = [...p.w.document.querySelectorAll('input[id^="bal-"]')].map(e => e.id.slice(4));
  check('Update Balances: one box per OPEN account (the closed Car Loan has none, the added Discover has one)', JSON.stringify(boxIds) === JSON.stringify(openIds), boxIds.join(','));
  const labels = [...p.w.document.querySelectorAll('input[id^="bal-"]')].map(e => txt(e.parentElement.querySelector('label')));
  check('the box labels are the account names, including the renamed one', labels.includes('Chase Freedom') && labels.includes('Discover') && !labels.includes('Car Loan'), labels.join('|'));
  check('the new card box shows what is owed (250.00)', Number(p.$('bal-disc').value) === 250);

  // L3 correcting the new account through the real button
  const n0 = p.App.v2Raw.transactions.length;
  p.$('bal-disc').value = '100';
  await p.Views.dashboard.saveBalances(); await tick(); await tick();
  const sv = p.lastSaved(), ce = sv.transactions[sv.transactions.length - 1];
  check('setting Discover to 100 owed saves ONE payment entry of +15000 cents on the new account', p.api.saved.length === 1 && sv.transactions.length === n0 + 1 && ce.accountId === 'disc' && ce.amountCents === 15000 && ce.type === 'correction' && L.balanceCents(sv, 'disc', TODAY) === 10000, JSON.stringify(ce));

  // L2 Add Entry account box
  p = await page(f, 'inputs');
  const opts = [...p.$('txn-account').options].map(o => [o.value, o.textContent]);
  check('Add Entry: the account box lists the open accounts with their real names (no closed Car Loan)', JSON.stringify(opts.map(o => o[0])) === JSON.stringify(openIds) && opts.find(o => o[0] === 'cc')[1] === 'Chase Freedom' && opts.find(o => o[0] === 'disc')[1] === 'Discover', JSON.stringify(opts));
  p.$('txn-date').value = TODAY; p.$('txn-account').value = 'disc'; p.$('txn-desc').value = 'Coffee'; p.$('txn-amount').value = '-4.50';
  await p.Views.inputs.addTransactionV2(); await tick(); await tick();
  const e2 = p.lastSaved().transactions.slice(-1)[0];
  check('an entry on the new card saves (a charge of 4.50 raises what is owed to 254.50)', e2.accountId === 'disc' && e2.amountCents === -450 && L.balanceCents(p.lastSaved(), 'disc', TODAY) === 25450, JSON.stringify(e2));

  // L2 Ledgers tabs
  p = await page(f, 'ledgers');
  const tabs = () => [...p.w.document.querySelectorAll('.ledger-tab')].map(t => [txt(t), t.className.includes('active')]);
  check('Ledgers: a tab per open account, in file order, with real names; the closed Car Loan has none', JSON.stringify(tabs().map(t => t[0])) === JSON.stringify(['VAULT', 'FLEX', 'FUNDS', 'Chase Freedom', 'SAVOR (Capital One)', 'BREX', 'Discover']), JSON.stringify(tabs()));
  [...p.w.document.querySelectorAll('.ledger-tab')].find(t => txt(t) === 'Discover').click(); await tick();
  check('clicking the Discover tab opens it: title and current balance', txt(p.w.document.querySelector('.card-title')) === 'Discover' && /Current: \$250\.00/.test(txt(p.w.document.querySelector('.card-subtitle'))), txt(p.w.document.querySelector('.card-subtitle')));
  p.Views.ledgers.currentAccount = 'car_loan'; p.App.renderCurrentView();
  check('if the open ledger is an account that is closed, the first open account is shown instead (no error)', tabs()[0][1] === true && p.Views.ledgers.currentAccount === 'vault' && p.errors.length === 0, JSON.stringify(tabs()[0]));

  // L5 names with HTML characters and quotes can never break the page
  let h = L.renameAccount(f, 'disc', '<img src=x onerror=window.PWNED=1>').data;
  h = L.renameAccount(h, 'brex', 'O\'Brien "loan" & <b>co</b>').data;
  p = await page(h, 'ledgers');
  check('Ledgers: odd names appear as plain text (no element is created from them)', !p.w.document.querySelector('.ledger-tab img') && !p.w.document.querySelector('.ledger-tab b') && tabs().map(t => t[0]).includes('<img src=x onerror=window.PWNED=1>') && tabs().map(t => t[0]).includes('O\'Brien "loan" & <b>co</b>'), JSON.stringify(tabs()));
  [...p.w.document.querySelectorAll('.ledger-tab')].find(t => txt(t).startsWith('O\'Brien')).click(); await tick();
  check('and clicking that tab still works', p.Views.ledgers.currentAccount === 'brex' && txt(p.w.document.querySelector('.card-title')) === 'O\'Brien "loan" & <b>co</b>');
  p = await page(h, 'dashboard');
  check('Update Balances: odd names are plain text and boxes still exist', !p.w.document.querySelector('.card label img') && !!p.$('bal-disc') && !!p.$('bal-brex') && p.w.PWNED === undefined);
  p = await page(h, 'inputs');
  check('Add Entry: odd names are plain option text', [...p.$('txn-account').options].some(o => o.textContent === '<img src=x onerror=window.PWNED=1>') && p.w.PWNED === undefined);

  // L2 old (v1) files are exactly as before
  const oldFile = { accounts: { vault: 0, flex: 0, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 }, settings: {}, paychecks: [], fixedExpenses: [], transactions: [ tx('vault', '2026-03-01', 1000, 1000) ] };
  p = await page(oldFile, 'dashboard');
  const b1 = [...p.w.document.querySelectorAll('input[id^="bal-"]')].map(e => [e.id.slice(4), txt(e.parentElement.querySelector('label'))]);
  check('v1: the seven boxes with the old labels', JSON.stringify(b1) === JSON.stringify([['vault', 'VAULT'], ['flex', 'FLEX'], ['funds', 'FUNDS'], ['cc', 'FREEDOM'], ['cc2', 'SAVOR'], ['car_loan', 'Car Loan'], ['brex', 'BREX']]), JSON.stringify(b1));
  p = await page(oldFile, 'inputs');
  check('v1: the static account box (FREEDOM (Chase), SAVOR (Capital One) ...)', JSON.stringify([...p.$('txn-account').options].map(o => o.textContent)) === JSON.stringify(['VAULT', 'FLEX', 'FUNDS', 'FREEDOM (Chase)', 'SAVOR (Capital One)', 'Car Loan', 'BREX']));
  p = await page(oldFile, 'ledgers');
  check('v1: seven ledger tabs with the old names', JSON.stringify([...p.w.document.querySelectorAll('.ledger-tab')].map(t => txt(t))) === JSON.stringify(['VAULT', 'FLEX', 'FUNDS', 'FREEDOM', 'SAVOR', 'Car Loan', 'BREX']));

  check('no page errors anywhere', p.errors.length === 0, p.errors.join('|'));
  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();