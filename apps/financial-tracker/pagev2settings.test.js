// Run:  node pagev2settings.test.js     (needs jsdom, like renderer.test.js)
// The REAL index.html in a simulated browser: the Accounts card on the Settings page (rename, close, reopen, add).
// Old (v1) files do not get the card.
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
  const page = async (file, view) => { const p = makePage(); await tick(); await p.open(file, view || 'settings'); return p; };
  const txt = (el) => el.textContent.replace(/\s+/g, ' ').trim();
  const D = (p) => p.w.document;
  const rows = (p) => [...D(p).querySelectorAll('#accounts-card .expense-item')].map(r => ({ id: r.querySelector('input').id.slice(10), name: r.querySelector('input').value, disabled: r.querySelector('input').disabled, meta: txt(r.querySelector('.expense-meta')), amount: txt(r.querySelector('.expense-amount')), buttons: [...r.querySelectorAll('button')].map(b => txt(b) + (b.disabled ? '(off)' : '')) }));
  const fill = (p, o) => { D(p).getElementById('na-name').value = o.name; D(p).getElementById('na-kind').value = o.kind || 'credit_card'; D(p).getElementById('na-owed').value = o.owed; D(p).getElementById('na-date').value = o.date === undefined ? START : o.date; };
  const accts = (p) => p.lastSaved().accounts;

  // L2 old files get no card
  const oldFile = { accounts: { vault: 0, flex: 0, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 }, settings: {}, paychecks: [], fixedExpenses: [], transactions: [ tx('vault', '2026-03-01', 1000, 1000) ] };
  const p1 = await page(oldFile);
  check('v1 (old) file: no Accounts card, and the Settings page still shows (Save All Settings is there)', !D(p1).getElementById('accounts-card') && /Save All Settings/.test(D(p1).body.textContent), '');

  // L2 the card on a v2 file
  let f = L.closeAccount(L.addAccount(v2, { name: 'Old Card', kind: 'credit_card', owedCents: 0, date: START, makeId: () => 'oldc' }).data, 'oldc', TODAY).data;
  let p = await page(f);
  const r0 = rows(p), by = (id) => r0.find(r => r.id === id);
  check('one row per account, closed ones included, in file order', JSON.stringify(r0.map(r => r.id)) === JSON.stringify(['vault', 'flex', 'funds', 'cc', 'cc2', 'car_loan', 'brex', 'oldc']), JSON.stringify(r0.map(r => r.id)));
  check('VAULT, FLEX and FUNDS: renameable, no Close button, marked as such', ['vault', 'flex', 'funds'].every(id => JSON.stringify(by(id).buttons) === JSON.stringify(['Rename']) && /cannot be closed/.test(by(id).meta)), JSON.stringify(['vault', 'flex', 'funds'].map(id => by(id))));
  check('a card owing money: the Close button is there but switched off; a loan on 0: Close works', JSON.stringify(by('cc').buttons) === JSON.stringify(['Rename', 'Close(off)']) && by('cc').amount === '$40.00' && JSON.stringify(by('car_loan').buttons) === JSON.stringify(['Rename', 'Close']), JSON.stringify([by('cc'), by('car_loan')]));
  check('a closed account: name box locked, only Reopen, marked closed', by('oldc').disabled === true && JSON.stringify(by('oldc').buttons) === JSON.stringify(['Reopen']) && /closed/.test(by('oldc').meta));

  // L3 rename through the real function
  D(p).getElementById('acct-name-cc').value = '  Chase   Freedom ';
  await p.Views.settings.renameAccount('cc'); await tick(); await tick();
  check('rename: ONE save, only the name changed (id, kind, role, opening all kept), message shown', p.api.saved.length === 1 && JSON.stringify(accts(p).find(a => a.id === 'cc')) === JSON.stringify(Object.assign({}, f.accounts.find(a => a.id === 'cc'), { name: 'Chase Freedom' })) && p.toasts.some(m => /renamed and saved/.test(m)), JSON.stringify(accts(p).find(a => a.id === 'cc')));
  check('entries and the other accounts are untouched by a rename', JSON.stringify(p.lastSaved().transactions) === JSON.stringify(f.transactions) && JSON.stringify(accts(p).filter(a => a.id !== 'cc')) === JSON.stringify(f.accounts.filter(a => a.id !== 'cc')));
  check('the page redraws with the new name (box and Ledgers/Dashboard use it)', rows(p).find(r => r.id === 'cc').name === 'Chase Freedom' && p.App.acctName('cc', 'x') === 'Chase Freedom');

  // L5 rename refusals: nothing saved
  p = await page(f);
  const refusals = [['empty', '', /1 to 40/], ['spaces', '   ', /1 to 40/], ['too long', 'x'.repeat(41), /1 to 40/], ['same as another account', ' vault ', /already has that name/], ['same as a closed account', 'old card', /already has that name/]];
  for (const [nm, val, re] of refusals) { D(p).getElementById('acct-name-cc').value = val; p.toasts.length = 0; await p.Views.settings.renameAccount('cc'); await tick(); check('rename refused: ' + nm, p.api.saved.length === 0 && p.toasts.some(m => /Not renamed/.test(m) && re.test(m)), JSON.stringify(p.toasts)); }
  D(p).getElementById('acct-name-cc').value = 'FREEDOM (Chase)'; p.toasts.length = 0;
  await p.Views.settings.renameAccount('cc'); await tick();
  check('renaming to its own name saves nothing and says so', p.api.saved.length === 0 && p.toasts.some(m => /already its name/.test(m)));

  // L3 close and reopen
  p = await page(f);
  await p.Views.settings.closeAccount('car_loan'); await tick(); await tick();
  check('close the Car Loan (balance 0): ONE save, closed true, nothing else changed', p.api.saved.length === 1 && accts(p).find(a => a.id === 'car_loan').closed === true && JSON.stringify(p.lastSaved().transactions) === JSON.stringify(f.transactions) && p.toasts.some(m => /closed and saved/.test(m)));
  check('after closing: the row shows Reopen and a locked box', JSON.stringify(rows(p).find(r => r.id === 'car_loan').buttons) === JSON.stringify(['Reopen']) && rows(p).find(r => r.id === 'car_loan').disabled);
  p.App.currentView = 'dashboard'; p.App.renderCurrentView();
  check('the Dashboard no longer shows a Car Loan card', ![...D(p).querySelectorAll('.balance-card .label')].some(l => /Car Loan/.test(txt(l))));
  p.App.currentView = 'settings'; p.App.renderCurrentView();
  await p.Views.settings.reopenAccount('car_loan'); await tick(); await tick();
  check('reopen: closed false again, the card is back', p.api.saved.length === 2 && accts(p).find(a => a.id === 'car_loan').closed === false && JSON.stringify(rows(p).find(r => r.id === 'car_loan').buttons) === JSON.stringify(['Rename', 'Close']));

  // L5 close refusals
  p = await page(f);
  for (const [nm, id, re] of [['a card that owes money', 'cc', /balance is not zero/], ['VAULT (special role)', 'vault', /./], ['unknown account', 'nope', /unknown/]]) { p.toasts.length = 0; await p.Views.settings.closeAccount(id); await tick(); check('close refused: ' + nm, p.api.saved.length === 0 && p.toasts.some(m => /Not closed/.test(m) && re.test(m)), JSON.stringify(p.toasts)); }
  const fut = L.addTransaction(f, { accountId: 'car_loan', date: '2027-02-01', description: 'later', amountCents: 100, makeId: () => 'futx' }).data;
  p = await page(fut); await p.Views.settings.closeAccount('car_loan'); await tick();
  check('close refused when the account has an entry dated in the future', p.api.saved.length === 0 && p.toasts.some(m => /Not closed.*after that day/.test(m)), JSON.stringify(p.toasts));
  p = await page(f); await p.Views.settings.reopenAccount('cc'); await tick();
  check('reopen refused for an account that is not closed', p.api.saved.length === 0 && p.toasts.some(m => /Not reopened/.test(m)));

  // L3 add
  p = await page(f);
  fill(p, { name: ' Discover ', kind: 'credit_card', owed: '250.00' });
  const nAcc = f.accounts.length;
  await p.Views.settings.addAccount(); await tick(); await tick();
  const added = accts(p)[accts(p).length - 1];
  check('add: ONE save, one new account with the exact shape (role none, owed as opening, the chosen date, open)', p.api.saved.length === 1 && accts(p).length === nAcc + 1 && added.name === 'Discover' && added.kind === 'credit_card' && added.role === 'none' && added.openingCents === 25000 && added.openingDate === START && added.closed === false && /^[A-Za-z0-9]+$/.test(added.id) && JSON.stringify(Object.keys(added).sort()) === JSON.stringify(['closed', 'id', 'kind', 'name', 'openingCents', 'openingDate', 'role']), JSON.stringify(added));
  check('the new account owes what was typed from that day, and the page shows its row and clears the form', L.balanceCents(p.lastSaved(), added.id, TODAY) === 25000 && rows(p).some(r => r.name === 'Discover' && r.amount === '$250.00') && D(p).getElementById('na-name').value === '');
  p.App.currentView = 'dashboard'; p.App.renderCurrentView();
  check('and it has a card and an alert on the Dashboard', [...D(p).querySelectorAll('.balance-card .label')].some(l => txt(l) === 'Discover') && [...D(p).querySelectorAll('.alert-chip')].some(e => /Discover has a balance — \$250\.00/.test(txt(e))));
  fill((p = await page(f)), { name: 'Student Loan', kind: 'loan', owed: '1000' });
  await p.Views.settings.addAccount(); await tick(); await tick();
  check('add a loan', accts(p)[accts(p).length - 1].kind === 'loan' && accts(p)[accts(p).length - 1].openingCents === 100000);
  fill((p = await page(f)), { name: 'Zero', kind: 'credit_card', owed: '0' });
  await p.Views.settings.addAccount(); await tick(); await tick();
  check('adding with 0 owed is fine', p.api.saved.length === 1 && accts(p).slice(-1)[0].openingCents === 0);

  // L5 add refusals: nothing saved, the form keeps what was typed
  const bad = [['no name', { name: '', owed: '5' }, /1 to 40/], ['long name', { name: 'q'.repeat(41), owed: '5' }, /1 to 40/], ['same name as another account', { name: 'savor (capital one)', owed: '5' }, /already has that name/], ['same name as a closed account', { name: 'OLD CARD', owed: '5' }, /already has that name/],
    ['no amount', { name: 'N', owed: '' }, /enter what is owed/], ['negative amount', { name: 'N', owed: '-5' }, /0 or more/], ['absurd amount', { name: 'N', owed: '99999999999999999' }, /not a valid number/], ['no date', { name: 'N', owed: '5', date: '' }, /bad date/]];
  for (const [nm, o, re] of bad) { p = await page(f); fill(p, o); await p.Views.settings.addAccount(); await tick(); check('add refused: ' + nm, p.api.saved.length === 0 && p.toasts.some(m => /Not added/.test(m) && re.test(m)) && D(p).getElementById('na-name').value === o.name, JSON.stringify(p.toasts)); }
  p = await page(f); fill(p, { name: 'Bad', owed: '' }); Object.defineProperty(D(p).getElementById('na-owed'), 'validity', { value: { badInput: true } });
  await p.Views.settings.addAccount(); await tick();
  check('unreadable text in the amount box: refused', p.api.saved.length === 0 && p.toasts.some(m => /Not added.*valid number/.test(m)));
  p = await page(f); fill(p, { name: 'Bank', kind: 'bank', owed: '5' }); D(p).getElementById('na-kind').innerHTML += '<option value="bank">bank</option>'; D(p).getElementById('na-kind').value = 'bank';
  await p.Views.settings.addAccount(); await tick();
  check('a kind other than card or loan is refused even if the page is tampered with', p.api.saved.length === 0 && p.toasts.some(m => /only a credit card or a loan/.test(m)));

  // L4 double click: one account only
  p = await page(f); fill(p, { name: 'Twice', owed: '10' });
  const a1 = p.Views.settings.addAccount(), a2 = p.Views.settings.addAccount(); await a1; await a2; await tick(); await tick();
  check('double click on Add: ONE save, ONE new account, the second click is told to wait', p.api.saved.length === 1 && accts(p).filter(a => a.name === 'Twice').length === 1 && p.toasts.some(m => /Still saving/.test(m)), p.api.saved.length + ' ' + JSON.stringify(p.toasts));

  // L5 a failed save changes nothing
  p = await page(f); p.api.saveResult = () => ({ ok: false, error: 'disk full' });
  D(p).getElementById('acct-name-cc').value = 'New Name'; await p.Views.settings.renameAccount('cc'); await tick(); await tick();
  check('failed save: the account keeps its old name in memory, the user is told it was NOT saved', p.App.acctName('cc', '') === 'FREEDOM (Chase)' && p.toasts.some(m => /NOT saved/i.test(m)), JSON.stringify(p.toasts));
  p.api.saveResult = () => ({ ok: true }); D(p).getElementById('acct-name-cc').value = 'New Name'; await p.Views.settings.renameAccount('cc'); await tick(); await tick();
  check('and a retry afterwards works', p.App.acctName('cc', '') === 'New Name' && p.api.saved.length === 2);

  // L5 odd names: shown as text, never become page code
  let h = L.renameAccount(L.renameAccount(f, 'cc', '"><img src=x onerror=window.PWNED=1> \'q\'').data, 'brex', '<b>x</b> & y').data;
  p = await page(h);
  check('odd names sit in the name boxes as plain text (no element made, nothing runs)', !D(p).querySelector('#accounts-card img, #accounts-card b') && rows(p).find(r => r.id === 'cc').name === '"><img src=x onerror=window.PWNED=1> \'q\'' && rows(p).find(r => r.id === 'brex').name === '<b>x</b> & y' && p.w.PWNED === undefined, JSON.stringify(rows(p).find(r => r.id === 'cc')));
  D(p).getElementById('acct-name-brex').value = '<b>x</b> & z';
  await p.Views.settings.renameAccount('brex'); await tick(); await tick();
  check('and renaming such an account still works', p.api.saved.length === 1 && accts(p).find(a => a.id === 'brex').name === '<b>x</b> & z');

  // L2 the rest of the Settings page still works next to the card
  p = await page(f);
  D(p).getElementById('s-rate').value = '33.5';
  p.Views.settings.save(); await tick(); await tick();
  check('Save All Settings still works on a v2 file with the card present', p.errors.length === 0 && /33\.5/.test(JSON.stringify(p.App.data.settings.regularRate)));

  check('no page errors anywhere', [p1, p].every(x => x.errors.length === 0), [p1, p].map(x => x.errors.join('|')).join(' / '));
  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();