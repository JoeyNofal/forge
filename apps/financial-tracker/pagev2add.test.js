// Run:  node pagev2add.test.js     (needs jsdom, like renderer.test.js)
// The REAL index.html in a simulated browser: adding an entry to a v2 file by amount only.
// It must save the v2 file correctly, change the screen ONLY after a good save, refuse bad input,
// never double-save, and leave v1 files working exactly as before.
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
const tx = (accountId, date, amount, balance, extra) => Object.assign({ id: accountId + '-' + date + '-' + amount, accountId, date, description: 'd ' + date, amount, balance, type: 'transaction' }, extra || {});
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
  const fire = (id, type) => $(id).dispatchEvent(new w.Event(type, { bubbles: true }));
  const fill = (o) => { if (o.date !== undefined) { $('txn-date').value = o.date; fire('txn-date', 'change'); } if (o.account) { $('txn-account').value = o.account; fire('txn-account', 'change'); } if (o.desc !== undefined) $('txn-desc').value = o.desc; if (o.amount !== undefined) { $('txn-amount').value = o.amount; fire('txn-amount', 'input'); } };
  const open = async (file) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(file) }); await tick(); App.currentView = 'inputs'; App.renderCurrentView(); };
  return { w, App, Views, api, toasts, errors, timers, $, fire, fill, open };
}
const today = () => { const d = new Date(), z = (n) => String(n).padStart(2, '0'); return d.getFullYear() + '-' + z(d.getMonth() + 1) + '-' + z(d.getDate()); };

(async () => {
  // L1 static
  check('L1 the v2 path saves through saveV2 only, and ledger.js does the math', /App\.saveV2\(r\.data\)/.test(rd('index.html')) && /FTLedger\.addTransaction\(/.test(rd('index.html')));

  // L2 the form on a v2 file
  const p = makePage(); await tick(); await p.open(v2);
  check('v2 form: the balance box is read-only and labelled calculated; the Type box is hidden', p.$('txn-balance').readOnly === true && /calculated/i.test(p.$('txn-balance').closest('.form-group').textContent) && p.$('txn-type').closest('.form-group').style.display === 'none');
  p.fill({ account: 'vault', amount: '-30' });
  check('preview: VAULT 950.00 and an expense of 30 shows 920.00', p.$('txn-balance').value === '920.00', p.$('txn-balance').value);
  p.fill({ account: 'cc', amount: '-30' });
  check('preview: the card owes 40.00, spending 30 shows 70.00 owed, with the card hint', p.$('txn-balance').value === '70.00' && /spending is negative/.test(p.$('txn-v2-note').textContent), p.$('txn-balance').value);
  p.fill({ account: 'cc', amount: '25' });
  check('preview: a 25 payment lowers the card to 15.00', p.$('txn-balance').value === '15.00');
  p.fill({ account: 'vault', date: '2099-01-01', amount: '-30' });
  check('future date: the note says it counts from that date', /Future date: it counts in balances from 2099-01-01/.test(p.$('txn-v2-note').textContent));
  p.fill({ date: today() });
  check('a normal date shows no future note', !/Future date/.test(p.$('txn-v2-note').textContent));

  // L2/L3 add one entry
  const before = JSON.stringify(v2);
  p.fill({ account: 'vault', date: today(), desc: 'Groceries', amount: '-30' });
  await p.Views.inputs.addTransactionV2(); await tick();
  const indAfter = p.$('save-indicator').textContent;
  check('exactly one save happened', p.api.saved.length === 1, 'saves: ' + p.api.saved.length);
  const f = JSON.parse(p.api.saved[0]);
  const last = f.transactions[f.transactions.length - 1];
  check('the saved file is v2 with the accounts still a list', f.schemaVersion === 2 && Array.isArray(f.accounts) && f.accounts.length === v2.accounts.length);
  check('the new entry: -3000 cents, no dollar amount, no typed balance, type transaction', last.amountCents === -3000 && last.description === 'Groceries' && last.accountId === 'vault' && last.type === 'transaction' && !('amount' in last) && !('balance' in last));
  check('every earlier entry and every other key is byte-for-byte unchanged', JSON.stringify(f.transactions.slice(0, -1)) === JSON.stringify(v2.transactions) && JSON.stringify(Object.assign({}, f, { transactions: 0 })) === JSON.stringify(Object.assign({}, v2, { transactions: 0 })) && JSON.stringify(v2) === before);
  check('no page-only fields leaked into the file', !/_v2ReadOnly|migrationEntries|fundsSubAccounts/.test(p.api.saved[0]));
  check('the saved file passes the shape check and VAULT is 920.00 in it', L.validate(f).length === 0 && L.balanceCents(f, 'vault', '2199-12-31') === 92000);
  check('the screen now shows VAULT 920 and the entry in Ledgers', p.App.data.accounts.vault === 920 && (p.App.currentView = 'ledgers', p.Views.ledgers.currentAccount = 'vault', p.App.renderCurrentView(), /Groceries/.test(p.$('view-container').textContent)));
  check('the user is told it saved, and the indicator says Saved', p.toasts.some(m => /added and saved/i.test(m)) && /Saved/.test(indAfter), indAfter);
  p.App.currentView = 'inputs'; p.App.renderCurrentView();
  check('the form is empty again after a save', p.$('txn-desc').value === '' && p.$('txn-amount').value === '');

  // L5 bad input is refused and nothing is saved
  const n0 = p.api.saved.length;
  for (const [name, o] of [['no description', { desc: '', amount: '-5' }], ['blank description', { desc: '   ', amount: '-5' }], ['no amount', { desc: 'x', amount: '' }], ['zero amount', { desc: 'x', amount: '0' }]]) {
    p.fill(Object.assign({ account: 'vault', date: today() }, o)); await p.Views.inputs.addTransactionV2();
    check('refused: ' + name, p.api.saved.length === n0);
  }
  p.fill({ account: 'vault', date: '', desc: 'x', amount: '-5' }); await p.Views.inputs.addTransactionV2();
  check('refused: no date', p.api.saved.length === n0);

  // L5 a failed save changes nothing on screen
  const raw0 = p.App.v2Raw, vault0 = p.App.data.accounts.vault, cnt0 = p.App.data.transactions.length;
  p.api.saveResult = () => ({ ok: false, error: 'disk full' });
  p.fill({ account: 'vault', date: today(), desc: 'Will fail', amount: '-10' }); await p.Views.inputs.addTransactionV2(); await tick();
  check('failed save: the screen data is untouched and the user is told nothing was added', p.App.v2Raw === raw0 && p.App.data.accounts.vault === vault0 && p.App.data.transactions.length === cnt0 && p.toasts.some(m => /NOT saved, nothing was added: disk full/.test(m)));
  p.api.saveResult = () => new Error('boom');
  p.fill({ account: 'vault', date: today(), desc: 'Will throw', amount: '-10' }); await p.Views.inputs.addTransactionV2(); await tick();
  check('a save that throws is also reported and changes nothing', p.App.v2Raw === raw0 && p.toasts.some(m => /NOT saved, nothing was added: boom/.test(m)));
  p.api.saveResult = () => ({ ok: true });
  p.fill({ account: 'vault', date: today(), desc: 'Retry works', amount: '-10' }); await p.Views.inputs.addTransactionV2(); await tick();
  check('after the problem is gone the same entry saves fine', p.App.data.accounts.vault === vault0 - 10);

  // L4 two clicks at once save only once
  const n1 = p.api.saved.length;
  p.fill({ account: 'flex', date: today(), desc: 'Double', amount: '-1' });
  const a = p.Views.inputs.addTransactionV2(), b = p.Views.inputs.addTransactionV2(); await Promise.all([a, b]); await tick();
  check('a double click saves ONE entry and tells the user to wait', p.api.saved.length === n1 + 1 && p.toasts.some(m => /Still saving/.test(m)));
  const fl = JSON.parse(p.api.saved[p.api.saved.length - 1]).transactions.filter(t => t.description === 'Double').length;
  check('and the file holds that entry exactly once', fl === 1);

  // L4 25 entries one after another all end up in the file
  for (let i = 0; i < 25; i++) { p.fill({ account: 'flex', date: today(), desc: 'Bulk ' + i, amount: '-1.01' }); await p.Views.inputs.addTransactionV2(); }
  const fin = JSON.parse(p.api.saved[p.api.saved.length - 1]);
  check('25 quick entries: all present once, FLEX balance exact', fin.transactions.filter(t => /^Bulk /.test(t.description)).length === 25 && L.balanceCents(fin, 'flex', '2199-12-31') === -100 - 2525, String(L.balanceCents(fin, 'flex', '2199-12-31')));

  // L2 the real button path (Add Transaction -> addTransaction) goes to the v2 saver
  const nb = p.api.saved.length;
  p.fill({ account: 'funds', date: today(), desc: 'Via the button', amount: '12.34' });
  p.Views.inputs.addTransaction(); await tick(); await tick(); await tick();
  const viaBtn = p.api.saved.length === nb + 1 ? JSON.parse(p.api.saved[nb]) : null;
  check('the Add Transaction button saves a v2 entry (+1234 cents on FUNDS, no typed balance)', !!viaBtn && viaBtn.transactions.some(t => t.description === 'Via the button' && t.amountCents === 1234 && t.accountId === 'funds' && !('balance' in t)), 'saves: ' + (p.api.saved.length - nb));

  // L2 nothing else is saved from a v2 file
  const n2 = p.api.saved.length;
  p.App.dirty = true; p.App.scheduleSave(); await p.App.flushNow(); for (const t of [...p.timers.values()]) await t.fn();
  check('other edits are still NOT saved on a v2 file (and the user is told)', p.api.saved.length === n2 && p.toasts.some(m => /not saved/i.test(m)));

  // L2 v1 files are unchanged
  const q = makePage(); await tick(); await q.open(old);
  check('v1 form: balance box editable, Type visible, v2 path off', q.App.v2Raw === null && q.$('txn-balance').readOnly === false && q.$('txn-type').closest('.form-group').style.display !== 'none' && !q.$('txn-v2-note'));
  q.fill({ account: 'vault', date: today(), desc: 'Old style', amount: '-5' });
  check('v1 form: typing the amount still auto-fills the new balance (945.00)', q.$('txn-balance').value === '945.00', q.$('txn-balance').value);
  q.Views.inputs.addTransaction(); await tick(); for (const t of [...q.timers.values()]) await t.fn();
  const s1 = q.api.saved.length ? JSON.parse(q.api.saved[0]) : null;
  check('v1: the entry is saved the old way (with a balance), once', q.api.saved.length === 1 && s1.transactions[s1.transactions.length - 1].balance === 945 && s1.transactions[s1.transactions.length - 1].amount === -5);
  check('no page errors anywhere', p.errors.length === 0 && q.errors.length === 0, p.errors.concat(q.errors).join(' | '));
  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();