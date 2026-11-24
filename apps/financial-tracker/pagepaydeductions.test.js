// Run:  node pagepaydeductions.test.js     (needs jsdom, like renderer.test.js)
// The REAL index.html in a simulated browser: deductions typed on the Paychecks screens (the Predict box and the
// Add Paycheck window) are used for that one calculation only. The saved settings are never touched, even if
// something fails half way (the old code swapped the settings and swapped them back).
const fs = require('fs'), path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const rd = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
let html = rd('index.html');
for (const f of ['dates.js', 'bills.js', 'ledger.js', 'v2view.js', 'settingscheck.js', 'paycheckrec.js']) html = html.replace('<script src="' + f + '"></script>', () => '<script>' + rd(f) + '</script>');
html = html.replace(/<script[^>]*\bsrc=[^>]*><\/script>/g, '');
const tick = () => new Promise(r => setImmediate(r));

function makePage() {
  const timers = new Map(); let tid = 1; const errors = [];
  const api = { saved: [], handlers: {}, saveData: async (j) => { api.saved.push(j); return { ok: true }; },
    createNewFile: async () => ({ ok: true }), loadFile: async () => ({ ok: false, canceled: true }), importFile: async () => ({ ok: false }), openBackupsFolder: async () => '', getAppInfo: async () => ({}), openExternal: async () => {},
    onInitialData: (cb) => { api.handlers.initial = cb; }, onLoadProblem: (cb) => { api.handlers.problem = cb; }, onFlushRequest: (cb) => { api.handlers.flush = cb; } };
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/', beforeParse(w) {
    w.electronAPI = api; w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {}; w.ExcelJS = {};
    w.setTimeout = (fn, ms) => { const id = tid++; timers.set(id, { fn, ms }); return id; }; w.clearTimeout = (id) => { timers.delete(id); };
    w.HTMLCanvasElement.prototype.getContext = () => null; } });
  const w = dom.window, App = w.eval('App'), Views = w.eval('Views');
  const toasts = []; App.showToast = (m, t) => { toasts.push({ m, t }); };
  const $ = (id) => w.document.getElementById(id);
  const open = async (file) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(file) }); await tick(); App.currentView = 'paychecks'; App.renderCurrentView(); };
  return { w, App, Views, api, toasts, errors, $, open };
}
const oldFile = () => ({ accounts: { vault: 5000, flex: 300, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 }, settings: {}, fixedExpenses: [], groceries: {}, creditScores: [], paychecks: [],
  transactions: [{ id: 'a', accountId: 'vault', date: '2026-01-01', description: 'd', amount: 5000, balance: 5000, type: 'transaction' }] });
const newPage = async () => { const p = makePage(); await tick(); await p.open(oldFile()); return p; };
const money = n => '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

(async () => {
  const watchdog = setTimeout(() => { console.log('FAIL: the test hung'); process.exit(1); }, 40000);
  const raw = rd('index.html');
  // L1 static
  check('L1 the settings swap-and-restore code is gone', !/Temporarily/.test(raw) && !/origBenefits|origOther|origRetPct/.test(raw));
  check('L1 predictNetPay takes the typed deductions as a second argument', /predictNetPay\(hours, over\)/.test(raw));
  check('L1 both screens pass them in', /predictNetPay\(hours, \{ benefits: customBenefits/.test(raw) && /predictNetPay\(\{\.\.\.hours, bonus\}, \{ benefits: benefitsVal/.test(raw));
  check('L1 the Add Paycheck live estimate is never negative either', /const net = Math\.max\(0, gross - totalTax - retirement - benefits - other\)/.test(raw));

  let p = await newPage();
  const { App, Views } = p, S = App.data.settings, C = App.calc;
  const frozen = () => JSON.stringify(S);
  S.regularRate = 30; S.benefitsDeduction = 30.92; S.otherDeductions = 54.49; S.retirementPercent = 5;
  const hours = { regular: 40 };

  // L2 predictNetPay
  const base = C.predictNetPay(hours), snap0 = frozen();
  check('no override: the net is gross - taxes - retirement - benefits - other', Math.abs(base.net - (base.gross - base.taxes - base.retirement - 30.92 - 54.49)) < 1e-9 && base.net > 0);
  check('no override: the result reports what it used', base.used.benefits === 30.92 && base.used.other === 54.49 && base.used.retirementPercent === 5);
  let r = C.predictNetPay(hours, { benefits: 100 });
  check('benefits override: net drops by exactly the difference', Math.abs((base.net - r.net) - (100 - 30.92)) < 1e-9 && r.used.benefits === 100);
  r = C.predictNetPay(hours, { other: 0 });
  check('other = 0 is a real value (not ignored)', Math.abs((r.net - base.net) - 54.49) < 1e-9 && r.used.other === 0);
  r = C.predictNetPay(hours, { retirementPercent: 10 });
  check('retirement 10% is used', Math.abs(r.retirement - r.gross * 0.1) < 1e-9 && r.used.retirementPercent === 10);
  r = C.predictNetPay(hours, { retirementPercent: 0 });
  check('retirement 0% is a real value', r.retirement === 0);
  r = C.predictNetPay(hours, { retirementPercent: 100 });
  check('retirement 100% is allowed', r.used.retirementPercent === 100 && r.net === 0);
  check('settings were never touched by any of that', frozen() === snap0);
  for (const bad of [NaN, -1, Infinity, '50', null, undefined, {}, [], true, 1e12]) {
    const x = C.predictNetPay(hours, { benefits: bad, other: bad });
    check('a bad override (' + typeof bad + ' ' + String(bad) + ') is ignored', x.used.benefits === 30.92 && x.used.other === 54.49 && Math.abs(x.net - base.net) < 1e-9);
  }
  for (const bad of [101, -5, NaN, '5']) check('retirement ' + String(bad) + ' is ignored', C.predictNetPay(hours, { retirementPercent: bad }).used.retirementPercent === 5);
  check('a non-object second argument is ignored', C.predictNetPay(hours, 5).used.benefits === 30.92 && C.predictNetPay(hours, 'x').used.benefits === 30.92 && C.predictNetPay(hours, null).used.benefits === 30.92);
  check('0 hours with big deductions is 0, never negative', C.predictNetPay({ regular: 0 }, { benefits: 500 }).net === 0);

  // the Predict box
  const SET = (id, v) => { p.$(id).value = String(v); };
  SET('pred-reg', 40); SET('pred-ot', 0); SET('pred-ns', 0); SET('pred-hol', 0); SET('pred-pto', 0); SET('pred-bonus', 0);
  SET('pred-benefits', 100); SET('pred-ret-pct', 10); SET('pred-other', 25);
  const before = frozen();
  Views.paychecks.predict();
  const txt = p.$('pred-result').textContent;
  const exp = C.predictNetPay(hours, { benefits: 100, retirementPercent: 10, other: 25 });
  check('Predict box: shows the typed deductions', txt.includes(money(100)) && txt.includes(money(25)) && /Retirement \(10%\)/.test(txt), txt.slice(0, 200));
  check('Predict box: shows the right net pay', txt.includes(money(exp.net)), money(exp.net) + ' in ' + txt.slice(0, 120));
  check('Predict box: the saved settings are untouched afterwards', frozen() === before);
  SET('pred-benefits', ''); SET('pred-ret-pct', ''); SET('pred-other', '');
  Views.paychecks.predict();
  const t2 = p.$('pred-result').textContent;
  check('Predict box: empty boxes fall back to the saved settings', t2.includes(money(30.92)) && t2.includes(money(54.49)) && /Retirement \(5%\)/.test(t2), t2.slice(0, 200));
  // a failure half way must leave the settings alone (the old code swapped them first and restored them later)
  SET('pred-benefits', 999); SET('pred-other', 888); SET('pred-ret-pct', 77);
  const real = C.predictNetPay; C.predictNetPay = () => { throw new Error('boom'); };
  let threw = false; try { Views.paychecks.predict(); } catch (e) { threw = true; }
  C.predictNetPay = real;
  check('Predict box: if the calculation fails, the saved settings are still the real ones', threw && frozen() === before && S.benefitsDeduction === 30.92 && S.otherDeductions === 54.49 && S.retirementPercent === 5);

  // the Add Paycheck window
  p = await newPage(); const A = p.App, V = p.Views, S2 = A.data.settings;
  S2.regularRate = 30; S2.benefitsDeduction = 30.92; S2.otherDeductions = 54.49; S2.retirementPercent = 5;
  const frozen2 = () => JSON.stringify(S2);
  V.paychecks.openAddModal(); await tick();
  const mset = (id, v) => { p.$(id).value = String(v); };
  check('Add Paycheck window opened with the saved deductions', p.$('m-benefits') && p.$('m-benefits').value === '30.92' && p.$('m-other').value === '54.49' && p.$('m-ret-pct').value === '5');
  mset('m-reg', 40); mset('m-benefits', 100); mset('m-other', 25); mset('m-ret-pct', 10);
  V.paychecks.recalcModal();
  const before2 = frozen2();
  V.paychecks.saveFromModal(); await tick();
  const saved = A.data.paychecks[A.data.paychecks.length - 1];
  check('Add Paycheck: a paycheck was saved', !!saved && saved.hours && saved.hours.regular === 40, JSON.stringify(A.data.paychecks).slice(0, 200));
  check('Add Paycheck: it carries the typed deductions', saved && saved.deductions.benefits === 100 && saved.deductions.other === 25 && Math.abs(saved.deductions.retirement - saved.grossPay * 0.1) < 1e-9, JSON.stringify(saved && saved.deductions));
  check('Add Paycheck: its net pay uses them', saved && Math.abs(saved.netPay - C.predictNetPay(hours, { benefits: 100, other: 25, retirementPercent: 10 }).net) < 1e-9, saved && String(saved.netPay));
  check('Add Paycheck: the saved settings are untouched', frozen2() === before2 && S2.benefitsDeduction === 30.92 && S2.otherDeductions === 54.49 && S2.retirementPercent === 5);
  V.paychecks.openAddModal(); await tick();
  mset('m-reg', 40); mset('m-benefits', 777); mset('m-other', 666); mset('m-ret-pct', 55);
  const real2 = A.calc.predictNetPay; A.calc.predictNetPay = () => { throw new Error('boom'); };
  let threw2 = false; try { V.paychecks.saveFromModal(); } catch (e) { threw2 = true; }
  A.calc.predictNetPay = real2;
  check('Add Paycheck: if the calculation fails, the saved settings are still the real ones', threw2 && frozen2() === before2);

  // L4 sustained
  let ok = true; const snap3 = frozen2();
  for (let i = 0; i < 2000; i++) { const x = A.calc.predictNetPay({ regular: i % 80 }, { benefits: i % 300, other: i % 70, retirementPercent: i % 101 }); if (!(x.net >= 0) || frozen2() !== snap3) { ok = false; break; } }
  check('L4 2,000 predictions: never negative, settings never change', ok);
  // L5 extreme
  let nothrow = true; try { for (const bad of [{ benefits: 1e308 }, { other: -1e308 }, { retirementPercent: 1e9 }, { benefits: {}, other: [] }, Object.create(null)]) A.calc.predictNetPay({ regular: 1e9, overtime: NaN, bonus: 'x' }, bad); } catch (e) { nothrow = false; console.log(e.stack); }
  check('L5 absurd overrides and hours never throw', nothrow);
  check('L5 no page errors', p.errors.length === 0, p.errors.join(' | '));
  clearTimeout(watchdog);
  console.log(failed === 0 ? passed + '/' + passed + ' passed' : passed + ' passed, ' + failed + ' FAILED');
  process.exit(failed === 0 ? 0 : 1);
})();