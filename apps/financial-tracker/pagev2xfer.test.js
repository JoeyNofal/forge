// Run:  node pagev2xfer.test.js     (needs jsdom, like renderer.test.js)
// The REAL index.html in a simulated browser: transfers and deletes on a v2 file.
// Everything is saved first and the screen changes only after a good save; v1 files are unchanged.
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
const END = '2199-12-31';

function makePage() {
  const timers = new Map(); let tid = 1; const errors = [], confirms = [], ask = { choice: 'both' }; let lastBar = null;
  const api = { saved: [], handlers: {}, saveResult: () => ({ ok: true }), saveData: async (j) => { api.saved.push(j); const r = api.saveResult(j); if (r instanceof Error) throw r; return r; }, createNewFile: async () => ({ ok: true }), loadFile: async () => ({ ok: false, canceled: true }), importFile: async () => ({ ok: false }), openBackupsFolder: async () => '', getAppInfo: async () => ({}), openExternal: async () => {}, flushDone: () => Promise.resolve(),
    onInitialData: (cb) => { api.handlers.initial = cb; }, onLoadProblem: (cb) => { api.handlers.problem = cb; }, onFlushRequest: (cb) => { api.handlers.flush = cb; } };
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/', beforeParse(w) {
    w.electronAPI = api; w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {}; w.ExcelJS = {};
    w.confirm = (m) => { confirms.push(m); return true; };
    w.setTimeout = (fn, ms) => { const id = tid++; timers.set(id, { fn, ms }); return id; }; w.clearTimeout = (id) => { timers.delete(id); };
    w.HTMLCanvasElement.prototype.getContext = () => null; } });
  const w = dom.window, App = w.eval('App'), Views = w.eval('Views');
  const toasts = []; App.showToast = (m) => { toasts.push(m); };
  const $ = (id) => w.document.getElementById(id);
  const open = async (file, view) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(file) }); await tick(); App.currentView = view || 'inputs'; App.renderCurrentView(); };
  const xfer = (o) => { App.currentView = 'inputs'; App.renderCurrentView(); $('tf-from').value = o.from; $('tf-to').value = o.to; $('tf-amount').value = o.amount === undefined ? '' : o.amount; $('tf-desc').value = o.desc || ''; if (o.date) $('tf-date').value = o.date; };
  const lastSaved = () => JSON.parse(api.saved[api.saved.length - 1]);
  const ledger = (acct) => { App.currentView = 'ledgers'; Views.ledgers.currentAccount = acct; App.renderCurrentView(); };
  const pick = async () => { await tick(); const bar = $('del-half-bar'); lastBar = bar ? { text: bar.textContent, buttons: [...bar.querySelectorAll('button')].map(b => b.textContent), count: w.document.querySelectorAll('#del-half-bar').length } : null; if (bar) $('del-half-' + ask.choice).click(); await tick(); await tick(); await tick(); };
  const del = async (ids) => { lastBar = null; ledger(App._acct || 'vault'); for (const id of ids) { const c = w.document.querySelector('.txn-check[data-id="' + id + '"]'); if (!c) return false; c.checked = true; } Views.ledgers.deleteSelected(); $('del-confirm-yes').click(); await pick(); return true; };
  return { w, App, Views, api, toasts, errors, timers, confirms, ask, $, open, xfer, lastSaved, ledger, del, bar: () => lastBar };
}

(async () => {
  check('L1 transfers and deletes save only through commitV2, and ledger.js does the math', /App\.commitV2\(r\.data, 'Transfer recorded and saved'\)/.test(rd('index.html')) && /FTLedger\.addTransfer\(/.test(rd('index.html')) && /FTLedger\.deleteTransactions\(/.test(rd('index.html')));

  // L2 form
  const p = makePage(); await tick(); await p.open(v2);
  const names = (id) => [...p.$(id).options].map(o => o.value);
  check('the transfer boxes list every open account in both From and To (cards and loans too), VAULT to FLEX by default', JSON.stringify(names('tf-from')) === JSON.stringify(v2.accounts.filter(a => !a.closed).map(a => a.id)) && JSON.stringify(names('tf-to')) === JSON.stringify(names('tf-from')) && p.$('tf-from').value === 'vault' && p.$('tf-to').value === 'flex', names('tf-from').join(','));

  // L3 a normal transfer
  p.xfer({ from: 'vault', to: 'flex', amount: '100', date: '2026-10-01' });
  const vault0 = p.App.data.accounts.vault, flex0 = p.App.data.accounts.flex;
  await p.Views.inputs.addTransferV2(); await tick();
  check('exactly one save', p.api.saved.length === 1, String(p.api.saved.length));
  let f = p.lastSaved(); let [h1, h2] = f.transactions.slice(-2);
  check('two linked halves: -10000 out of VAULT, +10000 into FLEX, same date, type transfer, default description', h1.accountId === 'vault' && h1.amountCents === -10000 && h2.accountId === 'flex' && h2.amountCents === 10000 && h1.linkedId === h2.id && h2.linkedId === h1.id && h1.date === '2026-10-01' && h1.type === 'transfer' && h1.description === 'Transfer to FLEX' && h2.description === h1.description, JSON.stringify([h1, h2]));
  check('no typed balances or dollar amounts in the saved halves', !('balance' in h1) && !('amount' in h1) && !('balance' in h2) && !('amount' in h2));
  check('the screen shows VAULT -100 and FLEX +100 and the saved file is valid', p.App.data.accounts.vault === vault0 - 100 && p.App.data.accounts.flex === flex0 + 100 && L.validate(f).length === 0);
  check('every earlier entry in the file is unchanged', JSON.stringify(f.transactions.slice(0, -2)) === JSON.stringify(v2.transactions));

  // L3 card direction (the old app's bug): paying the card lowers what is owed
  const cc0 = p.App.data.accounts.cc;
  p.xfer({ from: 'vault', to: 'cc', amount: '25', desc: 'Pay card', date: '2026-10-02' }); await p.Views.inputs.addTransferV2(); await tick();
  check('paying the card (VAULT to FREEDOM 25) lowers what is owed by 25 and lowers VAULT by 25', p.App.data.accounts.cc === cc0 - 25 && L.balanceCents(p.lastSaved(), 'cc', END) === Math.round(cc0 * 100) - 2500, String(p.App.data.accounts.cc));
  check('a typed description is kept', p.lastSaved().transactions.slice(-1)[0].description === 'Pay card');
  p.xfer({ from: 'cc', to: 'vault', amount: '10', date: '2026-10-03' }); await p.Views.inputs.addTransferV2(); await tick();
  check('moving money OUT of a card (cash advance) raises what is owed by 10', p.App.data.accounts.cc === cc0 - 25 + 10, String(p.App.data.accounts.cc));
  const total = (data) => L.netWorthCents(data, END);
  check('net worth is unchanged by transfers (money only moves)', total(p.lastSaved()) === total(v2), total(p.lastSaved()) + ' vs ' + total(v2));

  // L5 bad input
  const n0 = p.api.saved.length;
  for (const [name, o] of [['no amount', { from: 'vault', to: 'flex', amount: '' }], ['zero', { from: 'vault', to: 'flex', amount: '0' }], ['negative', { from: 'vault', to: 'flex', amount: '-5' }], ['same account', { from: 'vault', to: 'vault', amount: '5' }]]) { p.xfer(o); await p.Views.inputs.addTransferV2(); check('refused: ' + name, p.api.saved.length === n0); }

  // L5 failed save changes nothing
  const raw0 = p.App.v2Raw, v0 = p.App.data.accounts.vault;
  p.api.saveResult = () => ({ ok: false, error: 'disk full' }); p.xfer({ from: 'vault', to: 'flex', amount: '7' }); await p.Views.inputs.addTransferV2(); await tick();
  check('failed save: screen data untouched, user told nothing was changed', p.App.v2Raw === raw0 && p.App.data.accounts.vault === v0 && p.toasts.some(m => /NOT saved, nothing was changed: disk full/.test(m)));
  p.api.saveResult = () => new Error('boom'); p.xfer({ from: 'vault', to: 'flex', amount: '7' }); await p.Views.inputs.addTransferV2(); await tick();
  check('a save that throws is reported too', p.App.v2Raw === raw0 && p.toasts.some(m => /nothing was changed: boom/.test(m)));
  p.api.saveResult = () => ({ ok: true });

  // L4 double click
  const n1 = p.api.saved.length; p.xfer({ from: 'vault', to: 'flex', amount: '3', desc: 'dbl' });
  const a = p.Views.inputs.addTransferV2(), b = p.Views.inputs.addTransferV2(); await Promise.all([a, b]); await tick();
  check('a double click records ONE transfer', p.api.saved.length === n1 + 1 && p.lastSaved().transactions.filter(t => t.description === 'dbl').length === 2);

  // L2 deleting
  const T = () => p.App.v2Raw.transactions;
  const ordinary = T().find(t => t.accountId === 'vault' && t.type === 'transaction' && t.description === 'd 2026-03-02 -100');
  p.App._acct = 'vault';
  const vBefore = p.App.data.accounts.vault; const nDel = p.api.saved.length;
  await p.del([ordinary.id]);
  check('deleting an ordinary entry: one save, entry gone, balance moves back, nothing asked about transfers', p.api.saved.length === nDel + 1 && !T().some(t => t.id === ordinary.id) && p.App.data.accounts.vault === vBefore + 100 && p.confirms.length === 0 && p.bar() === null && p.toasts.some(m => /1 transaction\(s\) deleted and saved/.test(m)), p.confirms.join('|'));
  check('the saved file no longer contains it and is still valid', !p.lastSaved().transactions.some(t => t.id === ordinary.id) && L.validate(p.lastSaved()).length === 0);

  const pay = T().find(t => t.description === 'Pay card' && t.accountId === 'vault'), payHalf = T().find(t => t.id === pay.linkedId);
  p.ask.choice = 'both'; const ccB = p.App.data.accounts.cc, vB = p.App.data.accounts.vault;
  await p.del([pay.id]);
  check('deleting one half shows a bar with three clear buttons (no pop-up), and "Delete both sides" removes BOTH', !!p.bar() && p.confirms.length === 0 && /one half of a transfer/.test(p.bar().text) && JSON.stringify(p.bar().buttons) === JSON.stringify(['Delete both sides', 'Delete only the selected', 'Keep everything']) && !T().some(t => t.id === pay.id || t.id === payHalf.id) && p.App.data.accounts.cc === ccB + 25 && p.App.data.accounts.vault === vB + 25 && L.validate(p.lastSaved()).length === 0, JSON.stringify(p.bar()));
  check('the bar is gone after answering', !p.$('del-half-bar'));

  const dbl = T().filter(t => t.description === 'dbl'), dblA = dbl.find(t => t.accountId === 'vault'), dblB = dbl.find(t => t.accountId === 'flex');
  p.ask.choice = 'one'; const fB = p.App.data.accounts.flex;
  await p.del([dblA.id]);
  const surv = T().find(t => t.id === dblB.id);
  check('"Delete only the selected" removes only that half; the other stays, becomes an ordinary entry, file valid', !!p.bar() && !T().some(t => t.id === dblA.id) && !!surv && !surv.linkedId && p.App.data.accounts.flex === fB && L.validate(p.lastSaved()).length === 0);

  // "Keep everything" deletes nothing and saves nothing
  p.xfer({ from: 'vault', to: 'flex', amount: '2', desc: 'keepme' }); await p.Views.inputs.addTransferV2(); await tick();
  const keepA = T().find(t => t.description === 'keepme' && t.accountId === 'vault'); const nK = p.api.saved.length, cntK = T().length; p.ask.choice = 'keep';
  await p.del([keepA.id]);
  check('"Keep everything": nothing deleted, nothing saved, the user is told', p.api.saved.length === nK && T().length === cntK && T().some(t => t.id === keepA.id) && p.toasts.some(m => /Nothing was deleted/.test(m)) && !p.$('del-half-bar'));

  // asking twice never stacks two bars
  p.ledger('vault'); p.w.document.querySelector('.txn-check[data-id="' + keepA.id + '"]').checked = true;
  p.Views.ledgers.deleteSelected(); p.$('del-confirm-yes').click(); await tick(); p.Views.ledgers.deleteSelected(); p.$('del-confirm-yes').click(); await tick();
  check('asking twice leaves ONE bar on screen', p.w.document.querySelectorAll('#del-half-bar').length === 1);
  p.$('del-half-keep').click(); await tick(); await tick();
  check('and answering it leaves none, with nothing deleted', p.w.document.querySelectorAll('#del-half-bar').length === 0 && T().some(t => t.id === keepA.id));

  // "Delete both sides" with a failed save changes nothing
  p.ask.choice = 'both'; p.api.saveResult = () => ({ ok: false, error: 'disk full' }); const rawK = p.App.v2Raw;
  await p.del([keepA.id]);
  check('a failed save after "Delete both sides" changes nothing on screen', p.App.v2Raw === rawK && T().some(t => t.id === keepA.id) && T().some(t => t.id === keepA.linkedId) && p.toasts.some(m => /NOT saved, nothing was changed: disk full/.test(m)));
  p.api.saveResult = () => ({ ok: true });
  check('the desktop pop-up (confirm) is never used for any of this', p.confirms.length === 0);

  // (Both halves of a transfer can never be ticked together: the Ledgers page shows one account at a time. ledger-delete.test.js covers that case.)

  // L5 delete with a failed save changes nothing
  const some = T().find(t => t.accountId === 'vault' && t.type === 'transaction'); const rawD = p.App.v2Raw;
  p.api.saveResult = () => ({ ok: false, error: 'disk full' }); await p.del([some.id]);
  check('failed save on delete: nothing removed on screen, user told', p.App.v2Raw === rawD && T().some(t => t.id === some.id) && p.toasts.some(m => /NOT saved, nothing was changed: disk full/.test(m)));
  p.api.saveResult = () => ({ ok: true });

  // L2 the real Transfer button (addTransfer) goes to the v2 saver
  const nbt = p.api.saved.length; p.xfer({ from: 'flex', to: 'funds', amount: '4.50', desc: 'Via the button' });
  p.Views.inputs.addTransfer(); await tick(); await tick(); await tick();
  const bt = p.api.saved.length === nbt + 1 ? p.lastSaved().transactions.slice(-2) : null;
  check('the Transfer button saves a v2 transfer (-450 / +450 cents, linked)', !!bt && bt[0].amountCents === -450 && bt[1].amountCents === 450 && bt[0].accountId === 'flex' && bt[1].accountId === 'funds' && bt[0].linkedId === bt[1].id, 'saves: ' + (p.api.saved.length - nbt));

  // L2 other edits still unsaved on v2
  const n2 = p.api.saved.length; p.App.dirty = true; p.App.scheduleSave(); await p.App.flushNow(); for (const t of [...p.timers.values()]) await t.fn();
  check('other edits are still NOT saved on a v2 file', p.api.saved.length === n2);

  // L2 v1 unchanged
  const q = makePage(); await tick(); await q.open(old);
  check('v1: the transfer boxes are the old ones and the v2 path is off', q.App.v2Raw === null && [...q.$('tf-from').options].length === 3);
  q.xfer({ from: 'vault', to: 'flex', amount: '10', desc: 'old way' }); q.Views.inputs.addTransfer(); await tick(); for (const t of [...q.timers.values()]) await t.fn();
  const s1 = q.api.saved.length ? JSON.parse(q.api.saved[0]) : null; const l2 = s1 && s1.transactions.slice(-2);
  check('v1: a transfer is saved the old way (two linked halves with balances), once', q.api.saved.length === 1 && l2[0].balance === 940 && l2[0].amount === -10 && l2[1].amount === 10 && l2[0].linkedId === l2[1].id && !('amountCents' in l2[0]), JSON.stringify(l2));
  check('v1: selecting rows and deleting still works the old way', await (async () => { const id = q.App.data.transactions[0].id; q.ledger('vault'); q.w.document.querySelector('.txn-check[data-id="' + id + '"]').checked = true; q.Views.ledgers.deleteSelected(); q.$('del-confirm-yes').click(); await tick(); return !q.App.data.transactions.some(t => t.id === id) && q.confirms.length === 0; })());
  check('no page errors anywhere', p.errors.length === 0 && q.errors.length === 0, p.errors.concat(q.errors).join(' | '));
  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();