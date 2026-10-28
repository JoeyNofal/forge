// Run:  node pagedates.test.js     (from apps/financial-tracker)
// Loads the REAL index.html in a simulated browser, once per time zone, and checks the date
// behaviour the user actually sees: stored dates, "today" in the evening, the next paycheck date.
const fs = require('fs'), path = require('path');
const { spawnSync } = require('child_process');
const ZONES = { 'America/Indiana/Indianapolis': 240, 'UTC': 0, 'America/Los_Angeles': 420, 'Pacific/Auckland': -720, 'Asia/Kolkata': -330 };

function core(zone) {
  const { JSDOM, VirtualConsole } = require('jsdom');
  let passed = 0, failed = 0; const fails = [];
  const check = (name, cond, extra) => { if (cond) passed++; else { failed++; fails.push(name + (extra ? ' -> ' + extra : '')); } };
  const raw = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
  const datesSrc = fs.readFileSync(path.join(__dirname, 'dates.js'), 'utf8');
  const billsSrc = fs.readFileSync(path.join(__dirname, 'bills.js'), 'utf8');
  const html = raw.replace('<script src="dates.js"></script>', () => '<script>' + datesSrc + '</script>').replace('<script src="bills.js"></script>', () => '<script>' + billsSrc + '</script>').replace(/<script[^>]*\bsrc=[^>]*><\/script>/g, '');
  const errors = []; const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/',
    beforeParse(w) {
      w.electronAPI = { saveData: async () => ({ ok: true }), onInitialData() {}, onLoadProblem() {}, onFlushRequest() {}, flushDone() {}, loadFile: async () => ({ ok: false }), importFile: async () => ({ ok: false }), createNewFile: async () => ({ ok: true }), openBackupsFolder: async () => '' };
      w.Chart = class { constructor() {} destroy() {} update() {} }; w.ExcelJS = {};
      w.HTMLCanvasElement.prototype.getContext = () => null;
    }
  });
  const w = dom.window, App = w.eval('App');
  check('zone really in effect', new Date(2026, 6, 1).getTimezoneOffset() === ZONES[zone], zone);
  check('page starts without script errors', errors.length === 0, errors.join(' | '));
  check('the page has the date helpers', typeof w.FTDates === 'object');

  // 1. a stored date shows the same day
  for (const [s, shown] of [['2026-03-13', 'Mar 13, 2026'], ['2026-01-01', 'Jan 1, 2026'], ['2026-12-31', 'Dec 31, 2026'], ['2028-02-29', 'Feb 29, 2028']])
    check('page shows ' + s + ' as ' + shown, App.fmtDate(s) === shown, App.fmtDate(s));
  check('page shows nothing odd for a bad date', App.fmtDate('') === '—' && App.fmtDate(undefined) === '—' && App.fmtDate('garbage') === '—');
  // 2. "today" in the evening is still today
  for (const [h, mi] of [[0, 5], [12, 0], [19, 30], [20, 15], [23, 30], [23, 59]])
    check('date field default at ' + h + ':' + mi + ' is today, not tomorrow', App.fmtDateInput(new Date(2026, 9, 26, h, mi)) === '2026-10-26');
  check('a date typed into a date field comes back unchanged', App.fmtDateInput('2026-10-26') === '2026-10-26' && App.fmtDateInput('') === '');
  // 3. next paycheck date (a Friday far in the future, so the real clock does not matter)
  App.data.paychecks = [{ id: 'p1', approved: true, date: '2099-10-02', grossPay: 1, netPay: 1 }];
  let np; try { np = App.calc.nextPaycheckDate(); } catch (e) { np = null; }
  check('next paycheck date is a real date', np instanceof w.Date && !isNaN(np));
  check('next paycheck after Friday 2099-10-02 is Friday 2099-10-09 (shown)', np && App.fmtDate(np) === 'Oct 9, 2099', np && App.fmtDate(np));
  check('next paycheck date pre-filled into the form is 2099-10-09', np && App.fmtDateInput(np) === '2099-10-09', np && App.fmtDateInput(np));
  check('"work week end" pre-filled is the Friday a week earlier, 2099-10-02', (() => { const we = new w.Date(np); we.setDate(np.getDate() - 7); return App.fmtDateInput(we) === '2099-10-02'; })());
  // 3b. a bill due today stays on the list (it used to vanish), and the 31st never spills into the next month
  const todayS = w.FTDates.todayStr(), dayNow = +todayS.slice(8, 10);
  App.data.fixedExpenses = [{ id: 'e1', name: 'DueToday', amount: 10, frequency: 'monthly', dueDay: dayNow }, { id: 'e2', name: 'ThirtyFirst', amount: 20, frequency: 'monthly', dueDay: 31 }];
  let bills; try { bills = App.calc.upcoming30DayBills(); } catch (e) { bills = null; }
  check('bills list works on the page', Array.isArray(bills) && bills.length >= 2, bills && JSON.stringify(bills.length));
  check('a bill due today is on the list (dated today)', bills && bills.some(b => b.name === 'DueToday' && App.fmtDateInput(b.date) === todayS));
  check('bill dates are real Dates the page can show', bills && bills.every(b => b.date instanceof w.Date && App.fmtDate(b.date) !== '—'));
  check('the 31st bill falls on a real last-of-month date', bills && bills.filter(b => b.name === 'ThirtyFirst').every(b => { const s = App.fmtDateInput(b.date); return +s.slice(8, 10) === new Date(+s.slice(0, 4), +s.slice(5, 7), 0).getDate(); }));
  // 4. no old time-zone traps left in the two display helpers
  const m = raw.match(/fmtDate\(d\) \{[^\n]*\n\s*fmtDateInput\(d\) \{[^\n]*\n/);
  check('fmtDate and fmtDateInput are one-line calls into dates.js', !!m && !/toISOString|toLocale/.test(m[0]));
  return { zone, passed, failed, fails };
}

if (process.argv[2] === '--child') {
  console.log('@@' + JSON.stringify(core(process.env.TZ)));
} else {
  let total = 0, bad = 0;
  for (const zone of Object.keys(ZONES)) {
    const r = spawnSync(process.execPath, [__filename, '--child'], { env: Object.assign({}, process.env, { TZ: zone }), encoding: 'utf8' });
    const line = (r.stdout || '').split('\n').find(l => l.startsWith('@@'));
    if (!line) { bad++; console.log('FAIL: ' + zone + ' crashed: ' + (r.stderr || '').slice(0, 300)); continue; }
    const res = JSON.parse(line.slice(2)); total += res.passed; bad += res.failed;
    for (const f of res.fails) console.log('FAIL [' + zone + ']: ' + f);
  }
  console.log(bad === 0 ? total + '/' + total + ' passed (' + Object.keys(ZONES).length + ' time zones)' : total + ' passed, ' + bad + ' FAILED');
  process.exit(bad === 0 ? 0 : 1);
}