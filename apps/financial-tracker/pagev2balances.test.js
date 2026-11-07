// Run:  node pagev2balances.test.js     (needs jsdom, like renderer.test.js)
// The REAL index.html in a simulated browser: Update Balances (manual balance correction) on a v2 file.
// A correction is an ordinary entry, saved first; v1 files are unchanged.
const fs = require('fs'), path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
const M = require('./migrate.js'), L = require('./ledger.js');
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
  const H = rd('index.html');
  check('L1 Update Balances on v2 goes through the ledger and commitV2 only (no hand-made entries, no old "not available" message)', /FTLedger\.correctBalances\(/.test(H) && /App\.commitV2\(r\.data, r\.changed/.test(H) && !/not available on v2/.test(H));

  const dashOf = async (file) => { const p = makePage(); await tick(); await p.open(file, 'dashboard'); return p; };
  const set = (p, id, v) => { p.$('bal-' + id).value = v; };
  const today = (p) => p.w.eval('FTDates.todayStr()');

  // L2 a bank account goes up
  let p = await dashOf(v2);
  const ids = ['vault', 'flex', 'funds', 'cc', 'cc2', 'car_loan', 'brex'];
  check('all seven boxes exist and show the current balances', ids.every(id => p.$('bal-' + id) && Number(p.$('bal-' + id).value) === Number(p.App.data.accounts[id].toFixed(2))), ids.map(id => id + '=' + (p.$('bal-' + id) && p.$('bal-' + id).value)).join(' '));
  const vault0 = p.App.data.accounts.vault, n0 = p.App.v2Raw.transactions.length;
  set(p, 'vault', (vault0 + 50).toFixed(2));
  await p.Views.dashboard.saveBalances(); await tick(); await tick();
  check('exactly one save', p.api.saved.length === 1, String(p.api.saved.length));
  let f = p.lastSaved(); let c = f.transactions[f.transactions.length - 1];
  check('one new entry: VAULT, today, +5000 cents, name "Manual Balance Correction", type correction, no typed balance', f.transactions.length === n0 + 1 && c.accountId === 'vault' && c.date === today(p) && c.amountCents === 5000 && c.description === 'Manual Balance Correction' && c.type === 'correction' && !('balance' in c) && !('amount' in c), JSON.stringify(c));
  check('every earlier entry is unchanged and the file is valid', JSON.stringify(f.transactions.slice(0, n0)) === JSON.stringify(v2.transactions) && L.validate(f).length === 0);
  check('the screen shows the new VAULT balance and the saved file agrees', Math.abs(p.App.data.accounts.vault - (vault0 + 50)) < 1e-9 && L.balanceCents(f, 'vault', today(p)) === Math.round((vault0 + 50) * 100));
  check('the box shows the new number after the redraw, and a success message appeared', Number(p.$('bal-vault').value) === Number((vault0 + 50).toFixed(2)) && p.toasts.some(m => /1 balance corrected and saved/.test(m)), p.toasts.join('|'));
  check('the correction is an ordinary visible entry (not hidden in the migration row)', p.App.data.transactions.some(t => t.id === c.id) && !p.App.data.migrationEntries.some(t => t.id === c.id));

  // L2 a card: the box means "amount owed"
  p = await dashOf(v2);
  const ccOwed = p.App.data.accounts.cc;
  set(p, 'cc', '0');
  await p.Views.dashboard.saveBalances(); await tick(); await tick();
  f = p.lastSaved(); c = f.transactions[f.transactions.length - 1];
  check('card: owed ' + ccOwed + ' -> 0 saves a PAYMENT (cash flow +' + Math.round(ccOwed * 100) + ' cents)', c.accountId === 'cc' && c.amountCents === Math.round(ccOwed * 100) && L.balanceCents(f, 'cc', today(p)) === 0 && p.App.data.accounts.cc === 0, JSON.stringify(c));
  p = await dashOf(v2);
  set(p, 'cc', String(p.App.data.accounts.cc + 25));
  await p.Views.dashboard.saveBalances(); await tick(); await tick();
  f = p.lastSaved(); c = f.transactions[f.transactions.length - 1];
  check('card: owing 25.00 MORE saves a charge (cash flow -2500)', c.accountId === 'cc' && c.amountCents === -2500 && Math.abs(p.App.data.accounts.cc - (ccOwed + 25)) < 1e-9, JSON.stringify(c));

  // L2 a loan paid off: the box means "amount still owed" (first owe 2,500.00, then pay it off)
  p = await dashOf(v2);
  set(p, 'car_loan', '2500');
  await p.Views.dashboard.saveBalances(); await tick(); await tick();
  f = p.lastSaved(); c = f.transactions[f.transactions.length - 1];
  check('loan: setting what is owed to 2500.00 saves a charge of -250000 cents and the loan shows 2500', c.accountId === 'car_loan' && c.amountCents === -250000 && p.App.data.accounts.car_loan === 2500, JSON.stringify(c));
  set(p, 'car_loan', '0');
  await p.Views.dashboard.saveBalances(); await tick(); await tick();
  f = p.lastSaved(); c = f.transactions[f.transactions.length - 1];
  check('loan paid off: owed 2500.00 -> 0 saves a payment of +250000 cents and the loan lands on exactly 0', p.api.saved.length === 2 && c.accountId === 'car_loan' && c.amountCents === 250000 && L.balanceCents(f, 'car_loan', today(p)) === 0 && p.App.data.accounts.car_loan === 0, JSON.stringify(c));

  // L2 several at once = one save, one entry each; unchanged boxes add nothing
  p = await dashOf(v2);
  set(p, 'vault', '123.45'); set(p, 'flex', '10'); set(p, 'funds', '-5.5');
  const n1 = p.App.v2Raw.transactions.length;
  await p.Views.dashboard.saveBalances(); await tick(); await tick();
  f = p.lastSaved();
  const news = f.transactions.slice(n1);
  check('three changed boxes: ONE save, three entries (one per changed account only)', p.api.saved.length === 1 && news.length === 3 && news.map(t => t.accountId).sort().join() === 'flex,funds,vault', news.map(t => t.accountId).join());
  check('each account lands exactly on its number (a negative number is fine)', L.balanceCents(f, 'vault', today(p)) === 12345 && L.balanceCents(f, 'flex', today(p)) === 1000 && L.balanceCents(f, 'funds', today(p)) === -550);
  check('toast says 3 balances', p.toasts.some(m => /3 balances corrected and saved/.test(m)));

  // L2 nothing changed
  p = await dashOf(v2);
  await p.Views.dashboard.saveBalances(); await tick();
  check('no box changed: nothing saved, nothing added, the user is told', p.api.saved.length === 0 && p.App.v2Raw.transactions.length === v2.transactions.length && p.toasts.some(m => /No balances were changed/.test(m)));

  // L5 bad input: all or nothing
  p = await dashOf(v2);
  set(p, 'vault', '999'); set(p, 'flex', 'abc'); Object.defineProperty(p.$('bal-flex'), 'validity', { value: { badInput: true } });   // a real browser reports unreadable text this way (and gives an empty value)
  await p.Views.dashboard.saveBalances(); await tick();
  check('one box with unreadable text: NOTHING is saved (not even the good box), and the message names the box', p.api.saved.length === 0 && p.App.v2Raw.transactions.length === v2.transactions.length && p.toasts.some(m => /Nothing saved/.test(m) && /FLEX/.test(m)), p.toasts.join('|'));
  for (const bad of ['1e999', '99999999999999999', '--5', '1,5,5']) {
    p = await dashOf(v2); set(p, 'vault', bad);
    await p.Views.dashboard.saveBalances(); await tick();
    check('junk "' + bad + '" is refused and nothing is saved', p.api.saved.length === 0 && p.App.v2Raw.transactions.length === v2.transactions.length, p.toasts.join('|'));
  }
  p = await dashOf(v2); set(p, 'vault', '   '); set(p, 'flex', '');
  await p.Views.dashboard.saveBalances(); await tick();
  check('blank boxes are skipped (same as "unchanged")', p.api.saved.length === 0 && p.toasts.some(m => /No balances were changed/.test(m)));
  p = await dashOf(v2); set(p, 'vault', '100.005');
  await p.Views.dashboard.saveBalances(); await tick(); await tick();
  check('half a cent rounds to whole cents (100.01), never a float', p.api.saved.length === 1 && L.balanceCents(p.lastSaved(), 'vault', today(p)) === 10001, String(p.api.saved.length && L.balanceCents(p.lastSaved(), 'vault', today(p))));

  // L5 a failed save changes nothing on screen
  p = await dashOf(v2);
  const vb = p.App.data.accounts.vault; p.api.saveResult = () => ({ ok: false, error: 'disk full' });
  set(p, 'vault', String(vb + 10));
  await p.Views.dashboard.saveBalances(); await tick(); await tick();
  check('failed save: screen balance and raw ledger unchanged, user told it was NOT saved', p.App.data.accounts.vault === vb && p.App.v2Raw.transactions.length === v2.transactions.length && p.toasts.some(m => /NOT saved/i.test(m)), p.toasts.join('|'));
  p.api.saveResult = () => ({ ok: true });
  set(p, 'vault', String(vb + 10));
  await p.Views.dashboard.saveBalances(); await tick(); await tick();
  check('and a retry afterwards works, adding exactly one entry', p.App.v2Raw.transactions.length === v2.transactions.length + 1 && Math.abs(p.App.data.accounts.vault - (vb + 10)) < 1e-9);

  // L4 double click while saving: one entry only
  p = await dashOf(v2);
  set(p, 'vault', String(p.App.data.accounts.vault + 7));
  const a1 = p.Views.dashboard.saveBalances(), a2 = p.Views.dashboard.saveBalances(); await a1; await a2; await tick(); await tick();
  check('double click: ONE save, ONE entry, the second click is told to wait', p.api.saved.length === 1 && p.App.v2Raw.transactions.length === v2.transactions.length + 1 && p.toasts.some(m => /Still saving/.test(m)), p.api.saved.length + ' saves, ' + p.toasts.join('|'));

  // L2 the correction can be deleted like any other entry, and the balance goes back
  p = await dashOf(v2);
  const before = p.App.data.accounts.vault; set(p, 'vault', String(before + 40));
  await p.Views.dashboard.saveBalances(); await tick(); await tick();
  const corr = p.App.v2Raw.transactions[p.App.v2Raw.transactions.length - 1];
  const dr = L.deleteTransactions(p.App.v2Raw, [corr.id], false);
  check('the correction can be deleted by the normal delete and the balance returns', dr.ok && L.balanceCents(dr.data, 'vault', today(p)) === Math.round(before * 100));

  // L2 a file with an account missing: the other boxes still work
  const noBrex = JSON.parse(JSON.stringify(v2)); noBrex.accounts = noBrex.accounts.filter(a => a.id !== 'brex'); noBrex.transactions = noBrex.transactions.filter(t => t.accountId !== 'brex');
  p = await dashOf(noBrex); set(p, 'vault', String(p.App.data.accounts.vault + 3));
  await p.Views.dashboard.saveBalances(); await tick(); await tick();
  check('a file without a BREX account: the other boxes still save', p.api.saved.length === 1 && p.errors.length === 0, p.errors.join('|') + p.toasts.join('|'));

  // L2 v1 files behave exactly as before
  const oldFile = { accounts: { vault: 0, flex: 0, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 }, settings: {}, paychecks: [], fixedExpenses: [], transactions: [ tx('vault', '2026-03-01', 1000, 1000), tx('vault', '2026-03-02', -100, 900) ] };
  const o1 = await dashOf(oldFile);
  const vOld = o1.App.data.accounts.vault; set(o1, 'vault', String(vOld + 5));
  o1.Views.dashboard.saveBalances(); await tick();
  const last = o1.App.data.transactions[o1.App.data.transactions.length - 1];
  check('v1: the old behaviour is untouched (typed-balance correction entry, no v2 keys)', !o1.App.v2Raw && last.type === 'correction' && last.balance === vOld + 5 && o1.App.data.accounts.vault === vOld + 5 && !('amountCents' in last));

  check('no page errors anywhere', [p, o1].every(x => x.errors.length === 0), [p, o1].map(x => x.errors.join('|')).join(' / '));
  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();