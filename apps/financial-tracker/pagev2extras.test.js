// Run:  node pagev2extras.test.js     (needs jsdom, like renderer.test.js)
// On a v2 file EVERYTHING saves now: settings, paychecks, fixed expenses, groceries, credit scores...
// The ledger part (accounts + transactions) is never touched by those saves, and an autosave and a
// ledger save (add / transfer / delete) can never overwrite each other.
const fs = require('fs'), path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
const M = require('./migrate.js'), L = require('./ledger.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const rd = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
let html = rd('index.html');
for (const f of ['dates.js', 'bills.js', 'ledger.js', 'v2view.js', 'paycheckrec.js']) html = html.replace('<script src="' + f + '"></script>', () => '<script>' + rd(f) + '</script>');
html = html.replace(/<script[^>]*\bsrc=[^>]*><\/script>/g, '');
const tick = () => new Promise(r => setImmediate(r));
const tx = (accountId, date, amount, balance) => ({ id: accountId + '-' + date, accountId, date, description: 'd ' + date, amount, balance, type: 'transaction' });
const pay = (id, date, net, approved) => ({ id, date, workWeekEnd: date, hours: 40, bonus: 0, grossPay: net, taxes: { federal: 0, socialSecurity: 0, medicare: 0, indiana: 0, stJoseph: 0 }, deductions: 0, netPay: net, approved });
const mkOld = () => ({ accounts: {}, settings: { vaultBufferMonths: 7, flexFloor: 500 }, fixedExpenses: [{ id: 'f1', name: 'Rent', amount: 1000, frequency: 'monthly' }], groceries: { '2026-09': 400 }, creditScores: [],
  paychecks: [pay('pa', '2026-09-04', 1000, true), pay('pd', '2026-09-25', 1000, false)],
  transactions: [tx('vault', '2026-01-01', 5000, 5000), tx('funds', '2026-09-04', 2000, 2000), tx('flex', '2026-09-05', 300, 300)] });
const v2 = M.convert(mkOld(), { today: '2026-10-29' }).data;

function makePage() {
  const timers = new Map(); let tid = 1; const errors = [];
  const api = { saved: [], handlers: {}, hold: false, release: null, saveResult: () => ({ ok: true }),
    saveData: async (j) => { api.saved.push(j); if (api.hold) await new Promise(r => { api.release = r; }); const r = api.saveResult(j); if (r instanceof Error) throw r; return r; },
    createNewFile: async () => ({ ok: true }), loadFile: async () => ({ ok: false, canceled: true }), importFile: async () => ({ ok: false }), openBackupsFolder: async () => '', getAppInfo: async () => ({}), openExternal: async () => {}, flushDone: () => Promise.resolve(),
    onInitialData: (cb) => { api.handlers.initial = cb; }, onLoadProblem: (cb) => { api.handlers.problem = cb; }, onFlushRequest: (cb) => { api.handlers.flush = cb; } };
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/', beforeParse(w) {
    w.electronAPI = api; w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {}; w.ExcelJS = {};
    w.setTimeout = (fn, ms) => { const id = tid++; timers.set(id, { fn, ms }); return id; }; w.clearTimeout = (id) => { timers.delete(id); };
    w.HTMLCanvasElement.prototype.getContext = () => null; } });
  const w = dom.window, App = w.eval('App'), Views = w.eval('Views');
  const toasts = []; App.showToast = (m) => { toasts.push(m); };
  const $ = (id) => w.document.getElementById(id);
  const open = async (file, view) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(file) }); await tick(); App.currentView = view || 'dashboard'; App.renderCurrentView(); };
  const fire = async () => { for (const [id, t] of [...timers]) { timers.delete(id); await t.fn(); } };
  const last = () => JSON.parse(api.saved[api.saved.length - 1]);
  const fill = (o) => { App.currentView = 'inputs'; App.renderCurrentView(); $('txn-date').value = o.date || '2026-10-30'; $('txn-account').value = o.account || 'flex'; $('txn-desc').value = o.desc || 'x'; $('txn-amount').value = o.amount === undefined ? '-1' : o.amount; };
  return { w, App, Views, api, toasts, errors, timers, $, open, fire, last, fill };
}
const sameLedger = (f, base) => JSON.stringify(f.accounts) === JSON.stringify(base.accounts) && JSON.stringify(f.transactions) === JSON.stringify(base.transactions);

(async () => {
  const watchdog = setTimeout(() => { console.log('FAIL: the test hung (a save never finished)'); process.exit(1); }, 30000);
  check('L1 the read-only flag is gone from the page', !/_v2ReadOnly/.test(rd('index.html')) && /v2WithExtras\(raw\)/.test(rd('index.html')));

  // L2/L3 real flows: settings and approving a paycheck
  const p = makePage(); await tick(); await p.open(v2, 'settings');
  p.$('s-flexfloor').value = '650'; p.Views.settings.save(); await p.fire(); await tick();
  check('Settings > Save writes the v2 file with the new value', p.api.saved.length >= 1 && p.last().settings.flexFloor === 650, 'saves: ' + p.api.saved.length);
  check('the file is still v2, accounts are still a list, entries are untouched', p.last().schemaVersion === 2 && Array.isArray(p.last().accounts) && sameLedger(p.last(), v2));
  check('no page-only keys leaked into the file', !/_v2ReadOnly|migrationEntries|fundsSubAccounts/.test(p.api.saved[p.api.saved.length - 1]));
  check('the indicator says Saved and nobody is told "not saved"', /Saved/.test(p.$('save-indicator').textContent) && !p.toasts.some(m => /not saved/i.test(m)), p.$('save-indicator').textContent);
  const nA = p.api.saved.length; p.App.currentView = 'paychecks'; p.App.renderCurrentView(); p.Views.paychecks.approve('pd'); await p.fire(); await tick();
  check('approving a paycheck is saved', p.api.saved.length > nA && p.last().paychecks.find(x => x.id === 'pd').approved === true);

  // L3 every kind of extra, together
  p.App.data.fixedExpenses.push({ id: 'f2', name: 'Gym', amount: 25, frequency: 'monthly' });
  p.App.data.groceries['2026-10'] = 512.34; p.App.data.creditScores.push({ id: 'c1', date: '2026-10-01', score: 780, source: 'bank', notes: '', type: 'vantage' });
  p.App.data.settings.hiddenDescriptions = ['Old thing']; p.App.scheduleSave(); await p.fire(); await tick();
  const f = p.last();
  check('fixed expenses, groceries, credit scores and hidden items are all saved', f.fixedExpenses.some(e => e.id === 'f2') && f.groceries['2026-10'] === 512.34 && f.creditScores.some(s => s.id === 'c1') && f.settings.hiddenDescriptions[0] === 'Old thing');
  check('and the entries are STILL byte-for-byte the same', sameLedger(f, v2));
  // round trip: a fresh page reads that file back
  const r = makePage(); await tick(); await r.open(f);
  check('round trip: a fresh page reads the saved file with the same balances and the extras', r.App.data.accounts.vault === p.App.data.accounts.vault && r.App.data.accounts.flex === p.App.data.accounts.flex && r.App.data.fixedExpenses.some(e => e.id === 'f2') && r.App.data.paychecks.find(x => x.id === 'pd').approved === true && r.errors.length === 0);
  // the page's copy is a deep copy: later edits do not change what was written
  const w0 = p.App.v2WithExtras(p.App.v2Raw); const before = JSON.stringify(w0); p.App.data.settings.flexFloor = 9999; p.App.data.paychecks.push(pay('zz', '2026-11-01', 1, false));
  check('v2WithExtras makes a deep copy and never changes the raw ledger data', JSON.stringify(w0) === before && p.App.v2Raw.settings.flexFloor !== 9999);
  p.App.data.settings.flexFloor = 650; p.App.data.paychecks.pop();

  // L3 migration adjustments survive an extras save
  const messy = mkOld(); messy.transactions.push(tx('funds', '2026-09-18', 350, 2550));   // the math says 2,350: this makes a migration adjustment
  const conv = M.convert(messy, { today: '2026-10-29' });
  const pm = makePage(); await tick(); await pm.open(conv.data); pm.App.data.settings.flexFloor = 777; pm.App.scheduleSave(); await pm.fire(); await tick();
  check('a file that has migration adjustments keeps them, untouched, after a settings save', conv.data.transactions.some(t => t.type === 'migration_adjustment') && sameLedger(pm.last(), conv.data) && pm.last().settings.flexFloor === 777);

  // L4 an unsaved settings edit + a ledger save right away: both end up in the file
  const q = makePage(); await tick(); await q.open(v2);
  q.App.data.settings.flexFloor = 321; q.App.scheduleSave();
  q.fill({ desc: 'right after', amount: '-4' }); await q.Views.inputs.addTransactionV2(); await tick();
  check('the ledger save also carries the settings edit that was still waiting', q.last().settings.flexFloor === 321 && q.last().transactions.some(t => t.description === 'right after'));
  await q.fire(); await tick();
  check('and the autosave that fires afterwards keeps both (nothing lost, entry exactly once)', q.last().settings.flexFloor === 321 && q.last().transactions.filter(t => t.description === 'right after').length === 1);
  check('the page itself still shows both', q.App.data.settings.flexFloor === 321 && q.App.v2Raw.transactions.some(t => t.description === 'right after'));

  // L4 overlap 1: an autosave is running, the user adds an entry
  const o = makePage(); await tick(); await o.open(v2);
  o.App.data.settings.flexFloor = 111; o.App.dirty = true; o.api.hold = true;
  const saving = o.App.saveFile(); await tick();
  o.fill({ desc: 'during autosave', amount: '-2' }); const cnt = o.api.saved.length; await o.Views.inputs.addTransactionV2(); await tick();
  check('while an autosave is running, adding an entry waits ("Still saving") and writes nothing', o.api.saved.length === cnt && o.toasts.some(m => /Still saving/.test(m)));
  o.api.release(); await saving; await tick(); o.api.hold = false;
  check('the autosave finished, the lock is free again', o.App.v2Busy === false && o.last().settings.flexFloor === 111);
  o.fill({ desc: 'during autosave', amount: '-2' }); await o.Views.inputs.addTransactionV2(); await tick();
  check('adding the entry again works, and the file has both the entry and the setting', o.last().transactions.some(t => t.description === 'during autosave') && o.last().settings.flexFloor === 111);

  // L4 overlap 2: an entry is being saved, the autosave fires
  const o2 = makePage(); await tick(); await o2.open(v2);
  o2.fill({ desc: 'first', amount: '-3' }); o2.api.hold = true; const adding = o2.Views.inputs.addTransactionV2(); await tick();
  o2.App.data.settings.flexFloor = 222; o2.App.scheduleSave(); const n3 = o2.api.saved.length; await o2.App.saveFile();
  check('while an entry is being saved, the autosave does NOT write (it waits and retries)', o2.api.saved.length === n3 && [...o2.timers.values()].some(t => t.ms === 300));
  o2.api.release(); await adding; await tick(); o2.api.hold = false;
  check('an edit made while the entry was saving stays on screen and stays marked as unsaved', o2.App.data.settings.flexFloor === 222 && o2.App.dirty === true);
  await o2.fire(); await tick();
  check('afterwards the autosave writes the file with BOTH the entry and the setting', o2.last().transactions.some(t => t.description === 'first') && o2.last().settings.flexFloor === 222 && o2.last().transactions.filter(t => t.description === 'first').length === 1);

  // L4 overlap 3: you keep typing while an autosave is running - that edit must stay marked as unsaved
  const o3 = makePage(); await tick(); await o3.open(v2);
  o3.App.data.settings.flexFloor = 301; o3.App.scheduleSave(); o3.api.hold = true; const run = o3.App.saveFile(); await tick();
  o3.App.data.settings.flexFloor = 302; o3.App.scheduleSave();
  o3.api.release(); await run; await tick(); o3.api.hold = false;
  check('an edit typed while an autosave was running is still marked unsaved (so closing the window would save it)', o3.App.dirty === true && o3.last().settings.flexFloor === 301);
  await o3.fire(); await tick();
  check('and the next autosave writes it', o3.last().settings.flexFloor === 302 && o3.App.dirty === false);

  // L5 failed saves
  const e = makePage(); await tick(); await e.open(v2);
  e.api.saveResult = () => ({ ok: false, error: 'disk full' }); e.App.data.settings.flexFloor = 444; e.App.scheduleSave(); await e.fire(); await tick();
  check('failed save: indicator says SAVE FAILED, user told, a retry is scheduled in 5 s, the edit stays in memory', /SAVE FAILED/.test(e.$('save-indicator').textContent) && e.toasts.some(m => /Save failed: disk full/.test(m)) && [...e.timers.values()].some(t => t.ms === 5000) && e.App.data.settings.flexFloor === 444);
  check('a failed save leaves the lock free (adding an entry is not blocked)', e.App.v2Busy === false);
  e.api.saveResult = () => ({ ok: true }); await e.fire(); await tick();
  check('the retry works and writes the edit', e.last().settings.flexFloor === 444 && /Saved/.test(e.$('save-indicator').textContent));
  e.api.saveResult = () => new Error('boom'); e.App.data.settings.flexFloor = 445; e.App.scheduleSave(); await e.fire(); await tick();
  check('a save that throws is handled the same way', /SAVE FAILED/.test(e.$('save-indicator').textContent) && e.App.v2Busy === false);
  e.api.saveResult = () => ({ ok: true }); await e.fire(); await tick();

  // L2 flush on close
  const fl = makePage(); await tick(); await fl.open(v2);
  await fl.App.flushNow(); check('flush with nothing pending writes nothing', fl.api.saved.length === 0);
  fl.App.data.settings.flexFloor = 888; fl.App.scheduleSave(); await fl.App.flushNow(); await tick();
  check('flush with an edit pending writes it right away', fl.api.saved.length === 1 && fl.last().settings.flexFloor === 888);

  // L4 stress: 150 random steps (ledger adds + settings edits + saves), then the file must be exactly right
  const s = makePage(); await tick(); await s.open(v2);
  let seed = 7; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
  let accepted = 0, floor = 500;
  for (let i = 0; i < 150; i++) {
    const k = rnd();
    if (k < 0.4) { s.fill({ desc: 'stress ' + i, amount: String(-(1 + (i % 9))), account: ['flex', 'vault', 'funds'][i % 3] }); const before = s.App.v2Raw.transactions.length; await s.Views.inputs.addTransactionV2(); await tick(); if (s.App.v2Raw.transactions.length === before + 1) accepted++; }
    else if (k < 0.8) { floor = 100 + i; s.App.data.settings.flexFloor = floor; s.App.scheduleSave(); if (rnd() < 0.5) await s.fire(); }
    else { s.App.dirty = true; await s.App.flushNow(); }
    await tick();
  }
  await s.fire(); await tick(); await s.App.flushNow(); await tick();
  const sf = s.last(); const stressEntries = sf.transactions.filter(t => /^stress /.test(t.description));
  check('stress: every accepted entry is in the file exactly once, ids all different, no file errors', stressEntries.length === accepted && new Set(sf.transactions.map(t => t.id)).size === sf.transactions.length && L.validate(sf).length === 0, accepted + ' accepted, ' + stressEntries.length + ' in file');
  check('stress: the latest settings value is in the file, and it equals what the page shows', sf.settings.flexFloor === s.App.data.settings.flexFloor && sf.settings.flexFloor === floor, sf.settings.flexFloor + ' vs ' + floor);
  check('stress: the original entries are all still there and untouched', JSON.stringify(sf.transactions.slice(0, v2.transactions.length)) === JSON.stringify(v2.transactions) && s.App.v2Busy === false);



  // L2 v1 files unchanged
  const o1 = makePage(); await tick(); await o1.open(mkOld());
  o1.App.data.settings.flexFloor = 999; o1.App.scheduleSave(); await o1.fire(); await tick();
  check('v1: a save still writes the whole old-format file (typed balances, no v2 keys)', o1.api.saved.length === 1 && !!o1.last().transactions[0].balance && !Array.isArray(o1.last().accounts) && o1.last().schemaVersion === undefined && o1.last().settings.flexFloor === 999);
  check('no page errors anywhere', [p, pm, q, o, o2, o3, e, fl, s, o1, r].every(x => x.errors.length === 0), [p, pm, q, o, o2, o3, e, fl, s, o1, r].map(x => x.errors.join('|')).join(' / '));
  clearTimeout(watchdog);
  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();