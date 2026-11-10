// Run:  node pagev2expenses.test.js     (needs jsdom, like renderer.test.js)
// The REAL index.html in a simulated browser: editing a fixed expense in place on the Settings page.
// Works on old (v1) and new (v2) files.
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
  const fire = async () => { for (const [id, t] of [...timers]) { timers.delete(id); await t.fn(); } };
  return { w, App, Views, api, toasts, errors, $, open, lastSaved, fire };
}

(async () => {
  const page = async (file) => { const p = makePage(); await tick(); await p.open(file, 'settings'); return p; };
  const txt = (el) => el.textContent.replace(/\s+/g, ' ').trim();
  const D = (p) => p.w.document;
  const EXP = () => [
    { id: 'e1', name: 'Rent', amount: 1000, frequency: 'monthly', dueDay: 1, startDate: '2026-01-01', endDate: null, note: 'keep me' },
    { id: 'e2', name: 'Gym', amount: 25, frequency: 'monthly', dueDay: 15, startDate: null, endDate: null },
    { id: 7, name: 'Old numeric id', amount: 5, frequency: 'weekly', dueDay: null, startDate: '2026-02-01', endDate: '2026-12-01' }];
  const v1 = () => ({ accounts: { vault: 0, flex: 0, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 }, settings: {}, paychecks: [], fixedExpenses: EXP(), transactions: [ tx('vault', '2026-03-01', 1000, 1000) ] });
  const v2f = () => Object.assign({}, M.convert(old, { today: '2026-10-29' }).data, { fixedExpenses: EXP(), settings: {} });
  const fld = (p) => ({ name: D(p).getElementById('ex-name'), amount: D(p).getElementById('ex-amount'), freq: D(p).getElementById('ex-freq'), due: D(p).getElementById('ex-dueday'), start: D(p).getElementById('ex-start'), end: D(p).getElementById('ex-end') });
  const saved = (p, kind) => kind === 'v2' ? p.lastSaved().fixedExpenses : p.lastSaved().fixedExpenses;
  const rowsOf = (p) => [...D(p).querySelectorAll('.expense-item')].filter(r => r.querySelector('.expense-name') && !r.closest('#accounts-card'));

  for (const kind of ['v1', 'v2']) {
    const file = () => kind === 'v1' ? v1() : v2f();
    let p = await page(file());
    const rows = rowsOf(p);
    check(`${kind}: every fixed expense row has an Edit button AND the delete button`, rows.length === 3 && rows.every(r => [...r.querySelectorAll('button')].map(b => txt(b)).join('|') === 'Edit|×'), rows.map(r => [...r.querySelectorAll('button')].map(b => txt(b)).join('|')).join(' ; '));

    // open the editor: prefilled
    [...rows[0].querySelectorAll('button')][0].click(); await tick();
    let f = fld(p);
    check(`${kind}: clicking Edit opens the form in Edit mode with everything filled in`, /Edit Fixed Expense/.test(txt(D(p).getElementById('modal-content'))) && f.name.value === 'Rent' && f.amount.value === '1000' && f.freq.value === 'monthly' && f.due.value === '1' && f.start.value === '2026-01-01' && f.end.value === '' && D(p).getElementById('modal-overlay').classList.contains('open'));

    // change and save
    f.name.value = ' Rent (new lease) '; f.amount.value = '1100.50'; f.freq.value = 'biweekly'; f.due.value = '5'; f.end.value = '2027-01-01';
    p.Views.settings.saveExpense('e1'); await p.fire(); await tick();
    const after = p.App.data.fixedExpenses, sv = saved(p, kind);
    check(`${kind}: edited IN PLACE: same id, same position, same count, the other two untouched`, after.length === 3 && after[0].id === 'e1' && JSON.stringify(after.slice(1)) === JSON.stringify(EXP().slice(1)));
    check(`${kind}: the changed fields are right (name trimmed, amount, frequency, due day, end date) and the field the form does not show is kept`, after[0].name === 'Rent (new lease)' && after[0].amount === 1100.5 && after[0].frequency === 'biweekly' && after[0].dueDay === 5 && after[0].endDate === '2027-01-01' && after[0].startDate === '2026-01-01' && after[0].note === 'keep me');
    check(`${kind}: it is saved to the file, the form closes, and the list shows the new values`, JSON.stringify(sv) === JSON.stringify(after) && !D(p).getElementById('modal-overlay').classList.contains('open') && /Rent \(new lease\)/.test(txt(rowsOf(p)[0])) && /\$1,100\.50/.test(txt(rowsOf(p)[0])) && p.toasts.some(m => /Expense saved/.test(m)));
    if (kind === 'v2') check('v2: the ledger part of the saved file (accounts and entries) is untouched by an expense edit', JSON.stringify(p.lastSaved().transactions) === JSON.stringify(file().transactions) && JSON.stringify(p.lastSaved().accounts) === JSON.stringify(file().accounts));

    // a second edit of the same expense
    p.Views.settings.openExpenseModal('e1'); await tick(); f = fld(p);
    check(`${kind}: opening it again shows the NEW values`, f.name.value === 'Rent (new lease)' && f.amount.value === '1100.5' && f.freq.value === 'biweekly');
    p.App.closeModal();

    // numeric id (old files)
    p = await page(file());
    p.Views.settings.openExpenseModal('7'); await tick(); f = fld(p);
    check(`${kind}: an expense whose id is a number (older files) can be edited too`, f.name.value === 'Old numeric id');
    f.amount.value = '6'; p.Views.settings.saveExpense('7'); await p.fire(); await tick();
    check(`${kind}: and the right one is changed`, p.App.data.fixedExpenses[2].amount === 6 && p.App.data.fixedExpenses.length === 3);

    // odd names
    const odd = file(); odd.fixedExpenses[1].name = 'Bob\'s "car" <b>x</b> & <img src=x onerror=window.PWNED=1>';
    p = await page(odd);
    check(`${kind}: an odd name is shown as plain text in the list (nothing is made from it)`, !D(p).querySelector('.expense-item img, .expense-item b') && txt(rowsOf(p)[1].querySelector('.expense-name')) === odd.fixedExpenses[1].name && p.w.PWNED === undefined);
    p.Views.settings.openExpenseModal('e2'); await tick(); f = fld(p);
    check(`${kind}: the edit form holds the odd name EXACTLY (it used to be cut off at the first quote)`, f.name.value === odd.fixedExpenses[1].name);
    f.amount.value = '30'; p.Views.settings.saveExpense('e2'); await p.fire(); await tick();
    check(`${kind}: changing only the amount keeps that name intact`, p.App.data.fixedExpenses[1].name === odd.fixedExpenses[1].name && p.App.data.fixedExpenses[1].amount === 30 && p.w.PWNED === undefined);

    // validation: nothing changes
    const bad = [['empty name', { name: '  ' }, /Fill name and amount/], ['amount 0', { amount: '0' }, /Fill name and amount/], ['negative amount', { amount: '-5' }, /Fill name and amount/], ['no amount', { amount: '' }, /Fill name and amount/],
      ['due day 0', { due: '0' }, null], ['due day 32', { due: '32' }, /between 1 and 31/], ['due day 99', { due: '99' }, /between 1 and 31/], ['end before start', { start: '2026-05-01', end: '2026-04-30' }, /end date is before/]];
    for (const [nm, change, re] of bad) {
      p = await page(file()); p.Views.settings.openExpenseModal('e1'); await tick(); f = fld(p);
      for (const [k, v] of Object.entries(change)) f[k].value = v;
      p.toasts.length = 0; p.Views.settings.saveExpense('e1'); await p.fire(); await tick();
      const unchanged = JSON.stringify(p.App.data.fixedExpenses) === JSON.stringify(EXP());
      if (nm === 'due day 0') check(`${kind}: "due day 0" is the same as blank (no due day), the rest saves`, p.App.data.fixedExpenses[0].dueDay === null);
      else check(`${kind}: refused: ${nm}`, unchanged && p.api.saved.length === 0 && p.toasts.some(m => re.test(m)) && D(p).getElementById('modal-overlay').classList.contains('open'), JSON.stringify(p.toasts));
    }
    p = await page(file()); p.Views.settings.openExpenseModal('e1'); await tick(); f = fld(p); f.due.value = '31'; f.start.value = '2026-05-01'; f.end.value = '2026-05-01';
    p.Views.settings.saveExpense('e1'); await p.fire(); await tick();
    check(`${kind}: boundaries are fine (due day 31, end date equal to start date)`, p.App.data.fixedExpenses[0].dueDay === 31 && p.App.data.fixedExpenses[0].endDate === '2026-05-01');

    // the expense vanished while the form was open
    p = await page(file()); p.Views.settings.openExpenseModal('e2'); await tick(); f = fld(p); f.amount.value = '99';
    p.Views.settings.deleteExpense('e2'); p.toasts.length = 0; p.Views.settings.saveExpense('e2'); await p.fire(); await tick();
    check(`${kind}: saving an expense that was deleted meanwhile says so and adds nothing`, p.App.data.fixedExpenses.length === 2 && !p.App.data.fixedExpenses.some(e => e.id === 'e2') && p.toasts.some(m => /no longer exists/.test(m)) && !D(p).getElementById('modal-overlay').classList.contains('open'), JSON.stringify(p.toasts));

    // add and delete still work
    p = await page(file()); p.Views.settings.openExpenseModal(); await tick(); f = fld(p);
    check(`${kind}: the Add form is still the Add form (empty, titled Add)`, /Add Fixed Expense/.test(txt(D(p).getElementById('modal-content'))) && f.name.value === '' && f.amount.value === '');
    f.name.value = 'Phone'; f.amount.value = '40'; p.Views.settings.saveExpense(''); await p.fire(); await tick();
    check(`${kind}: adding a new expense still works (a new id, at the end)`, p.App.data.fixedExpenses.length === 4 && p.App.data.fixedExpenses[3].name === 'Phone' && p.App.data.fixedExpenses[3].id && p.App.data.fixedExpenses[3].id !== 'e1');
    p.Views.settings.deleteExpense('e2'); await p.fire(); await tick();
    check(`${kind}: delete still works`, !p.App.data.fixedExpenses.some(e => e.id === 'e2') && p.App.data.fixedExpenses.length === 3);
    check(`${kind}: no page errors`, p.errors.length === 0, p.errors.join('|'));
  }

  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();