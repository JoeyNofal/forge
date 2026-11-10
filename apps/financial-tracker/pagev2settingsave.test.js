// Run:  node pagev2settingsave.test.js     (needs jsdom, like renderer.test.js)
// The REAL index.html in a simulated browser: Settings > Save All Settings.
// Every box is checked first (settingscheck.js); one bad box means NOTHING is saved. Blank counts as 0,
// overtime / night shift are typed as percentages and stored as multipliers.
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
const mkOld = () => ({ accounts: {}, settings: {}, fixedExpenses: [], groceries: {}, creditScores: [], paychecks: [], transactions: [tx('vault', '2026-01-01', 5000, 5000), tx('flex', '2026-09-05', 300, 300)] });
const v2 = M.convert(mkOld(), { today: '2026-10-29' }).data;
const v1 = mkOld(); v1.accounts = { vault: 5000, flex: 300, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 };

function makePage() {
  const timers = new Map(); let tid = 1; const errors = [];
  const api = { saved: [], handlers: {}, saveData: async (j) => { api.saved.push(j); return { ok: true }; },
    createNewFile: async () => ({ ok: true }), loadFile: async () => ({ ok: false, canceled: true }), importFile: async () => ({ ok: false }), openBackupsFolder: async () => '', getAppInfo: async () => ({}), openExternal: async () => {}, flushDone: () => Promise.resolve(),
    onInitialData: (cb) => { api.handlers.initial = cb; }, onLoadProblem: (cb) => { api.handlers.problem = cb; }, onFlushRequest: (cb) => { api.handlers.flush = cb; } };
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/', beforeParse(w) {
    w.electronAPI = api; w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {}; w.ExcelJS = {};
    w.setTimeout = (fn, ms) => { const id = tid++; timers.set(id, { fn, ms }); return id; }; w.clearTimeout = (id) => { timers.delete(id); };
    w.HTMLCanvasElement.prototype.getContext = () => null; } });
  const w = dom.window, App = w.eval('App'), Views = w.eval('Views');
  const toasts = []; App.showToast = (m, t) => { toasts.push({ m, t }); };
  const $ = (id) => w.document.getElementById(id);
  const open = async (file) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(file) }); await tick(); App.currentView = 'settings'; App.renderCurrentView(); };
  const fire = async () => { for (const [id, t] of [...timers]) { timers.delete(id); await t.fn(); } };
  const last = () => JSON.parse(api.saved[api.saved.length - 1]);
  return { w, App, Views, api, toasts, errors, timers, $, open, fire, last };
}

(async () => {
  const watchdog = setTimeout(() => { console.log('FAIL: the test hung'); process.exit(1); }, 30000);
  const SAVE = (p) => { p.Views.settings.save(); };
  const snap = (p) => JSON.stringify(p.App.data.settings);

  // L1 static
  const idx = rd('index.html');
  check('L1 the page loads settingscheck.js and ships it', idx.includes('<script src="settingscheck.js"></script>') && /"settingscheck\.js"/.test(rd('package.json')));
  const saveSrc = idx.slice(idx.indexOf('  save() {\n    // Read every box'), idx.indexOf('  openExpenseModal(id)'));
  check('L1 the old "blank keeps the old value" code is gone from the settings save', saveSrc.length > 200 && !/parseFloat\(/.test(saveSrc) && !/parseInt\(/.test(saveSrc) && /FTSettingsCheck\.validate/.test(saveSrc));

  // L2 what the boxes show
  let p = makePage(); await tick(); await p.open(v2);
  check('percent boxes: OT shows 150 and night shift shows 113 (stored 1.5 and 1.13)', p.$('s-ot').value === '150' && p.$('s-ns').value === '113', p.$('s-ot').value + ' / ' + p.$('s-ns').value);
  check('labels say percent; VAULT months can go down to 0', /OT Multiplier \(%\)/.test(p.w.document.body.textContent) && /Nightshift Multiplier \(%\)/.test(p.w.document.body.textContent) && p.$('s-vaultmonths').getAttribute('min') === '0');
  check('v2: no Car Fund or Car Loan boxes', !p.$('s-carmin') && !p.$('s-cartarget') && !p.$('s-carloan') && !p.$('s-carloaninitial'));

  // L2 saving untouched settings changes nothing
  const before = snap(p);
  SAVE(p); await p.fire(); await tick();
  check('save with nothing changed: "Settings saved", every value identical', p.toasts.length === 1 && p.toasts[0].m === 'Settings saved' && snap(p) === before, JSON.stringify(p.toasts) + (snap(p) === before ? '' : ' CHANGED'));
  check('...and the v2 file was written with the same settings', p.api.saved.length >= 1 && JSON.stringify(p.last().settings.overtimeMultiplier) === '1.5' && p.last().settings.nightshiftMultiplier === 1.13);

  check('v2 save keeps the hidden Car Loan settings exactly as stored (not reset to 0)', p.App.data.settings.carLoanMonthlyTarget === 1500 && p.App.data.settings.carLoanInitial === 18500 && p.last().settings.carLoanMonthlyTarget === 1500 && p.last().settings.carLoanInitial === 18500, JSON.stringify([p.App.data.settings.carLoanMonthlyTarget, p.App.data.settings.carLoanInitial]));

  // L3 real edits
  p = makePage(); await tick(); await p.open(v2);
  p.$('s-ot').value = '175'; p.$('s-ns').value = '10.1'; p.$('s-flexfloor').value = '650'; p.$('s-benefits').value = ''; p.$('s-vaultmonths').value = '0'; p.$('s-ret').value = '0';
  SAVE(p); await p.fire(); await tick();
  let f = p.last();
  check('175 -> 1.75, 10.1 -> 0.101 (exact), 650, blank -> 0, VAULT months 0, retirement 0 all saved', f.settings.overtimeMultiplier === 1.75 && f.settings.nightshiftMultiplier === 0.101 && f.settings.flexFloor === 650 && f.settings.benefitsDeduction === 0 && f.settings.vaultBufferMonths === 0 && f.settings.retirementPercent === 0, JSON.stringify(f.settings));
  p.App.renderCurrentView();
  check('after redraw the OT box shows 175', p.$('s-ot').value === '175');
  p.$('s-vaultmonths').value = '5000'; SAVE(p); await p.fire(); await tick();
  check('VAULT months has no upper limit (5000 saves)', p.last().settings.vaultBufferMonths === 5000);
  check('the ledger part of the file is untouched by a settings save', JSON.stringify(f.accounts) === JSON.stringify(v2.accounts) && JSON.stringify(f.transactions) === JSON.stringify(v2.transactions));

  // L3 refusals: all or nothing
  p = makePage(); await tick(); await p.open(v2);
  const b0 = snap(p), n0 = p.api.saved.length;
  p.$('s-flexfloor').value = '650'; p.$('s-ret').value = '101';
  SAVE(p); await p.fire(); await tick();
  check('one good change + one bad box: refused, toast names the box', p.toasts.length === 1 && p.toasts[0].t === 'error' && /^Not saved\. Retirement \(%\)/.test(p.toasts[0].m), JSON.stringify(p.toasts));
  check('...NOTHING changed in memory (the good change is not applied either)', snap(p) === b0 && p.App.data.settings.flexFloor !== 650);
  check('...and nothing was written or scheduled', p.api.saved.length === n0 && p.timers.size === 0);
  for (const [id, val, re] of [['s-rate', '', /Hourly Rate: cannot be blank/], ['s-rate', '0', /Hourly Rate/], ['s-ccdue', '40', /FREEDOM Payment Due Day/], ['s-cc2stmt', '0', /SAVOR Statement Day/], ['s-vaultmonths', '2.5', /VAULT Buffer Months/], ['s-benefits', '10.123', /Benefits Deduction/], ['s-ot', '-5', /OT Multiplier/], ['s-flexfloor', '1e3', /FLEX Floor/]]) {
    p = makePage(); await tick(); await p.open(v2); const s0 = snap(p);
    p.$(id).value = val; SAVE(p); await p.fire();
    check('bad ' + id + ' = "' + val + '": refused with its name; nothing changed or saved', p.toasts.length === 1 && re.test(p.toasts[0].m) && p.toasts[0].t === 'error' && snap(p) === s0 && p.api.saved.length === 0, JSON.stringify(p.toasts));
  }

  // a browser reports "" for text it cannot read as a number; the page asks the box (validity.badInput)
  p = makePage(); await tick(); await p.open(v2); const s1 = snap(p);
  Object.defineProperty(p.$('s-flexfloor'), 'validity', { value: { badInput: true } });
  SAVE(p); await p.fire();
  check('a box the browser says holds non-number text is refused (not treated as blank)', p.toasts.length === 1 && /FLEX Floor: must be a number/.test(p.toasts[0].m) && snap(p) === s1 && p.api.saved.length === 0, JSON.stringify(p.toasts));

  // date box
  p = makePage(); await tick(); await p.open(v2); const d0 = p.App.data.settings.alternatingSundayStart;
  p.$('s-sundaystart').value = ''; SAVE(p); await p.fire();
  check('blank Sunday start date keeps the old date', p.toasts[0].m === 'Settings saved' && p.App.data.settings.alternatingSundayStart === d0 && d0);

  // v1 (old) file: same checks, Car Fund boxes present and checked
  p = makePage(); await tick(); await p.open(v1);
  check('v1 file: Car Fund and Car Loan boxes are on the page', !!p.$('s-carmin') && !!p.$('s-cartarget') && !!p.$('s-carloan') && !!p.$('s-carloaninitial'));
  p.$('s-carmin').value = '-5'; const s2 = snap(p); SAVE(p); await p.fire();
  check('v1 file: a bad Car Fund Minimum is refused and nothing changes', /Car Fund Minimum/.test(p.toasts[0].m) && snap(p) === s2);
  p.toasts.length = 0; p.$('s-carmin').value = '1200'; p.$('s-ot').value = '150'; SAVE(p); await p.fire(); await tick();
  check('v1 file: good values save as before (Car Fund Minimum 1200, OT 1.5)', p.toasts[0].m === 'Settings saved' && p.App.data.settings.carFundMinimum === 1200 && p.App.data.settings.overtimeMultiplier === 1.5);

  // L4/L5 repeated saves and odd existing values
  p = makePage(); await tick(); await p.open(v2);
  let bad = 0;
  for (let i = 0; i < 200; i++) { p.$('s-flexfloor').value = String(i); p.$('s-ot').value = String(100 + i); SAVE(p); if (p.App.data.settings.flexFloor !== i || p.App.data.settings.overtimeMultiplier !== Number(((100 + i) / 100).toPrecision(12))) bad++; }
  await p.fire(); await tick();
  check('200 quick saves: every one applied exactly, no script errors', bad === 0 && p.errors.length === 0, 'bad=' + bad + ' ' + p.errors.join('|'));
  p = makePage(); await tick(); await p.open(v2); p.App.data.settings.overtimeMultiplier = 'junk'; p.App.data.settings.nightshiftMultiplier = undefined; p.App.renderCurrentView();
  check('a damaged stored multiplier shows an empty box instead of crashing the page', p.$('s-ot').value === '' && p.$('s-ns').value === '' && p.errors.length === 0, p.errors.join('|'));
  p.$('s-ot').value = '150'; p.$('s-ns').value = '113'; SAVE(p);
  check('and typing both back fixes it', p.App.data.settings.overtimeMultiplier === 1.5 && p.App.data.settings.nightshiftMultiplier === 1.13);
  check('no script errors in the whole run', p.errors.length === 0, p.errors.join('|'));

  clearTimeout(watchdog);
  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();