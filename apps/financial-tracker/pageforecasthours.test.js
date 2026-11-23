// Run:  node pageforecasthours.test.js     (needs jsdom, like renderer.test.js)
// The REAL index.html in a simulated browser: the hours the Forecast assumes for each paycheck.
// Fixed hours every week, or the alternating long / short pattern (weeks run Sunday to Saturday,
// the week containing the start date is a LONG week, a Friday pay covers the week of the Friday before).
const fs = require('fs'), path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const rd = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
let html = rd('index.html');
for (const f of ['dates.js', 'bills.js', 'ledger.js', 'v2view.js', 'settingscheck.js', 'paycheckrec.js']) html = html.replace('<script src="' + f + '"></script>', () => '<script>' + rd(f) + '</script>');
html = html.replace(/<script[^>]*\bsrc=[^>]*><\/script>/g, '');
const tick = () => new Promise(r => setImmediate(r));
const DAY = 86400000, utcDay = (y, m, d) => Math.round(Date.UTC(y, m, d) / DAY);

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
  const open = async (file) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(file) }); await tick(); };
  return { w, App, Views, errors, open };
}
const oldFile = () => ({ accounts: { vault: 5000, flex: 300, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 }, settings: {}, fixedExpenses: [], groceries: {}, creditScores: [], paychecks: [],
  transactions: [{ id: 'a', accountId: 'vault', date: '2026-01-01', description: 'd', amount: 5000, balance: 5000, type: 'transaction' }] });

(async () => {
  const watchdog = setTimeout(() => { console.log('FAIL: the test hung'); process.exit(1); }, 30000);
  const raw = rd('index.html');

  // L1 static
  check('L1 the old isAlternatingSunday and its 2-on 2-off rule are gone', !/isAlternatingSunday/.test(raw) && !/weeks % 4 < 2/.test(raw));
  check('L1 the Forecast asks forecastHoursFor for its hours', /const hours = App\.calc\.forecastHoursFor\(payDate\)/.test(raw));
  check('L1 the week math comes from dates.js', /FTDates\.isLongWeek\(f\.start,/.test(raw));
  check('L1 predictNetPay never goes below zero', /const net = Math\.max\(0, gross - taxes/.test(raw));

  const p = await (async () => { const q = makePage(); await tick(); await q.open(oldFile()); return q; })();
  const { App, Views, w } = p;
  const S = App.data.settings, C = App.calc;
  check('L2 defaults are in place on a fresh file: 40 / fixed / 48 / 36', S.forecastFixedHours === 40 && S.forecastHoursMode === 'fixed' && S.forecastLongWeekHours === 48 && S.forecastShortWeekHours === 36, JSON.stringify([S.forecastFixedHours, S.forecastHoursMode, S.forecastLongWeekHours, S.forecastShortWeekHours]));
  const d = (y, m, dd) => new w.Date(y, m - 1, dd);   // a local-time Date, like the page's own paycheck dates

  // L2 fixed mode
  let rows = Views.forecast.generate();
  check('fixed: 52 weeks of 40 hours by default', rows.length === 52 && rows.every(r => r.hours === 40));
  S.forecastFixedHours = 37.5; check('fixed: 37.5 is used as typed', Views.forecast.generate().every(r => r.hours === 37.5));
  App.data.fixedExpenses = [{ id: 1, name: 'Rent', amount: 1000, frequency: 'monthly', dueDay: 1, startDate: '2026-01-01' }];   // $250 a week
  S.forecastFixedHours = 0; rows = Views.forecast.generate();
  check('fixed: 0 hours is respected (not turned back into 40)', rows.every(r => r.hours === 0));
  check('fixed: 0 hours means no pay, never negative pay', rows.every(r => r.netPay === 0), String(rows[0].netPay));
  check('fixed: with 0 hours VAULT falls by exactly the weekly bills ($250), nothing else', Math.abs((rows[1].vault - rows[0].vault) + 250) < 1e-6 && Number.isFinite(rows[51].vault), String(rows[1].vault - rows[0].vault));
  S.forecastFixedHours = 40; check('fixed: with 40 hours VAULT rises (pay beats the bills)', Views.forecast.generate()[1].vault > Views.forecast.generate()[0].vault); S.forecastFixedHours = 0;
  S.forecastFixedHours = 168; check('fixed: 168 is allowed', C.forecastHoursFor(d(2026, 3, 20)) === 168);
  for (const bad of ['junk', '', '   ', null, undefined, NaN, Infinity, -1, 169, 1e9, true, false, [], {}, [40], () => 40]) {
    S.forecastFixedHours = bad;
    check('fixed: a bad saved value (' + (typeof bad) + ' ' + String(bad) + ') falls back to 40', C.forecastHoursFor(d(2026, 3, 20)) === 40);
  }
  S.forecastFixedHours = '36'; check('fixed: a number stored as text still works', C.forecastHoursFor(d(2026, 3, 20)) === 36);
  S.forecastFixedHours = 40;
  for (const m of ['fixed', 'Alternating', 'ALTERNATING', 'x', '', null, undefined, 1, true]) { S.forecastHoursMode = m; S.alternatingSundayStart = '2026-03-13'; check('mode ' + JSON.stringify(m) + ' is the fixed mode', C.forecastHoursFor(d(2026, 3, 20)) === 40); }

  // L2 alternating mode
  S.forecastHoursMode = 'alternating'; S.alternatingSundayStart = '2026-03-13'; S.forecastLongWeekHours = 50; S.forecastShortWeekHours = 30;
  check('alternating: pay Fri Mar 20 pays the week of Mar 8-14, which holds the start date = LONG', C.forecastHoursFor(d(2026, 3, 20)) === 50);
  check('alternating: pay Fri Mar 27 = short week', C.forecastHoursFor(d(2026, 3, 27)) === 30);
  check('alternating: pay Fri Apr 3 = long again', C.forecastHoursFor(d(2026, 4, 3)) === 50);
  check('alternating: pay Fri Mar 13 pays the week before the start = short', C.forecastHoursFor(d(2026, 3, 13)) === 30);
  check('alternating: the time of day on the date changes nothing', C.forecastHoursFor(new w.Date(2026, 2, 20, 23, 59, 59)) === 50 && C.forecastHoursFor(new w.Date(2026, 2, 20, 0, 0, 1)) === 50);
  S.alternatingSundayStart = '2026-03-08'; check('alternating: a start date on the Sunday itself works the same', C.forecastHoursFor(d(2026, 3, 20)) === 50 && C.forecastHoursFor(d(2026, 3, 27)) === 30);
  S.alternatingSundayStart = '2026-03-14'; check('alternating: a start date on the Saturday works the same', C.forecastHoursFor(d(2026, 3, 20)) === 50 && C.forecastHoursFor(d(2026, 3, 27)) === 30);
  S.alternatingSundayStart = '2026-03-13';
  rows = Views.forecast.generate();
  check('alternating: the Forecast has 52 rows', rows.length === 52);
  let flips = true; for (let i = 1; i < rows.length; i++) if (rows[i].hours === rows[i - 1].hours) flips = false;
  check('alternating: every week differs from the one before (one long, one short, ...)', flips);
  check('alternating: only the two chosen values appear', rows.every(r => r.hours === 50 || r.hours === 30));
  check('alternating: the first Forecast row matches the helper for its own pay date', rows[0].hours === C.forecastHoursFor(rows[0].payDate));
  S.forecastLongWeekHours = undefined; S.forecastShortWeekHours = undefined;
  check('alternating: missing long/short boxes fall back to 48 and 36', C.forecastHoursFor(d(2026, 3, 20)) === 48 && C.forecastHoursFor(d(2026, 3, 27)) === 36);
  S.forecastLongWeekHours = 0; S.forecastShortWeekHours = 0.5;
  check('alternating: 0 and 0.5 are respected', C.forecastHoursFor(d(2026, 3, 20)) === 0 && C.forecastHoursFor(d(2026, 3, 27)) === 0.5);
  S.forecastLongWeekHours = 48; S.forecastShortWeekHours = 36;
  for (const badStart of ['', 'garbage', '2026-02-30', null, undefined, 5]) { S.alternatingSundayStart = badStart; check('alternating: an unusable start date (' + String(badStart) + ') falls back to the fixed hours, no crash', C.forecastHoursFor(d(2026, 3, 20)) === 40); }
  S.alternatingSundayStart = '2026-03-13';
  check('alternating: a bad pay date falls back to the fixed hours', C.forecastHoursFor(new w.Date(NaN)) === 40 && C.forecastHoursFor(null) === 40 && C.forecastHoursFor(undefined) === 40);

  // net pay is never negative
  S.forecastHoursMode = 'fixed';
  const h0 = C.predictNetPay({ regular: 0 }), h1 = C.predictNetPay({ regular: 1 }), h40 = C.predictNetPay({ regular: 40 });
  check('net pay at 0 hours is exactly 0', h0.net === 0 && h0.gross === 0);
  check('net pay at 1 hour (less than the deductions) is 0, not negative', h1.net === 0);
  check('net pay at 40 hours is still positive and unchanged by the clamp', h40.net > 0 && Math.abs(h40.net - (h40.gross - h40.taxes - h40.retirement - S.benefitsDeduction - S.otherDeductions)) < 1e-9);

  // L4 sustained: 3,000 pay dates against an independent calculation
  S.forecastHoursMode = 'alternating'; S.alternatingSundayStart = '2026-03-13'; S.forecastLongWeekHours = 48; S.forecastShortWeekHours = 36;
  const base = utcDay(2026, 2, 8);   // Sunday Mar 8 2026 = the first long week
  let agree = true, bad = '';
  for (let i = -700; i < 2300 && agree; i++) {
    const pay = new w.Date(2026, 2, 20 + i);   // local date
    const worked = utcDay(pay.getFullYear(), pay.getMonth(), pay.getDate()) - 7;
    const wk = Math.floor((worked - base) / 7);
    const expect = Math.abs(wk) % 2 === 0 ? 48 : 36;
    if (C.forecastHoursFor(pay) !== expect) { agree = false; bad = pay.toDateString(); }
  }
  check('L4 3,000 pay dates (about 8 years) agree with an independent day count', agree, bad);
  const t0 = Date.now(); for (let i = 0; i < 5; i++) Views.forecast.generate();
  check('L4 five full 52-week Forecasts are fast', Date.now() - t0 < 4000);

  // L5 junk settings never crash the Forecast
  let noThrow = true, shape = true;
  const junk = ['x', null, undefined, NaN, {}, [], -5, 1e308, '9'.repeat(10000), true];
  try { for (const j of junk) for (const k of ['forecastFixedHours', 'forecastLongWeekHours', 'forecastShortWeekHours', 'forecastHoursMode', 'alternatingSundayStart']) {
    const keep = S[k]; S[k] = j; const r = Views.forecast.generate(); if (r.length !== 52 || !r.every(x => Number.isFinite(x.hours) && x.hours >= 0 && x.hours <= 168)) shape = false; S[k] = keep; } } catch (e) { noThrow = false; console.log(e.stack); }
  check('L5 junk in any hours setting never crashes the Forecast', noThrow);
  check('L5 and the Forecast always has 52 rows of sensible hours', shape);
  check('L5 no page errors in the simulated browser', p.errors.length === 0, p.errors.join(' | '));
  clearTimeout(watchdog);
  console.log(failed === 0 ? passed + '/' + passed + ' passed' : passed + ' passed, ' + failed + ' FAILED');
  process.exit(failed === 0 ? 0 : 1);
})();