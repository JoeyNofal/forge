// Run:  node pageworkschedule.test.js     (needs jsdom, like renderer.test.js)
// The REAL index.html in a simulated browser: Settings > Work Schedule (forecast hours, the alternating
// switch, long / short week hours, start date). Everything is checked first; one bad box saves nothing.
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
  const open = async (file) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(file) }); await tick(); App.currentView = 'settings'; App.renderCurrentView(); };
  const fire = async () => { for (const [id, t] of [...timers]) { timers.delete(id); await t.fn(); } };
  const last = () => JSON.parse(api.saved[api.saved.length - 1]);
  return { w, App, Views, api, toasts, errors, $, open, fire, last };
}
const newPage = async (file) => { const p = makePage(); await tick(); await p.open(file); return p; };

(async () => {
  const watchdog = setTimeout(() => { console.log('FAIL: the test hung'); process.exit(1); }, 40000);
  const SAVE = (p) => { p.Views.settings.save(); };
  const snap = (p) => JSON.stringify(p.App.data.settings);
  const idx = rd('index.html');

  // L1 static
  for (const id of ['s-fixedhours', 's-alternating', 's-longhours', 's-shorthours', 's-sundaystart']) check('L1 the page has the box ' + id, idx.includes('id="' + id + '"'));
  check('L1 the switch is a checkbox and the save reads .checked', /type="checkbox" id="s-alternating"/.test(idx) && /altBox\.checked/.test(idx));
  check('L1 the card says weeks run Sunday to Saturday', /Weeks run Sunday to Saturday/.test(idx));

  for (const [label, file] of [['v2 file', v2], ['v1 file', v1]]) {
    // L2 what the boxes show
    let p = await newPage(file);
    check(label + ': boxes show 40 / 48 / 36 and the switch is off on a fresh file', p.$('s-fixedhours').value === '40' && p.$('s-longhours').value === '48' && p.$('s-shorthours').value === '36' && p.$('s-alternating').checked === false, [p.$('s-fixedhours').value, p.$('s-longhours').value, p.$('s-shorthours').value, p.$('s-alternating').checked].join(','));
    check(label + ': the labels are on the page', /Forecast Hours per Week/.test(p.w.document.body.textContent) && /Long Week Hours/.test(p.w.document.body.textContent) && /Short Week Hours/.test(p.w.document.body.textContent) && /alternating long \/ short week pattern/.test(p.w.document.body.textContent));
    const before = snap(p);
    SAVE(p); await p.fire(); await tick();
    check(label + ': saving untouched changes nothing', p.toasts.length === 1 && p.toasts[0].m === 'Settings saved' && snap(p) === before, JSON.stringify(p.toasts));

    // L3 real edits
    p = await newPage(file);
    p.$('s-fixedhours').value = '38.5'; p.$('s-longhours').value = '50'; p.$('s-shorthours').value = '30.25'; p.$('s-alternating').checked = true; p.$('s-sundaystart').value = '2026-03-13';
    SAVE(p); await p.fire(); await tick();
    let st = p.App.data.settings;
    check(label + ': edits saved: 38.5 / 50 / 30.25 / alternating', p.toasts[0].m === 'Settings saved' && st.forecastFixedHours === 38.5 && st.forecastLongWeekHours === 50 && st.forecastShortWeekHours === 30.25 && st.forecastHoursMode === 'alternating', JSON.stringify(p.toasts) + snap(p));
    check(label + ': ...and written to the file', p.api.saved.length >= 1 && p.last().settings.forecastFixedHours === 38.5 && p.last().settings.forecastHoursMode === 'alternating' && p.last().settings.forecastShortWeekHours === 30.25);
    p.App.renderCurrentView();
    check(label + ': after a redraw the boxes show what was saved', p.$('s-fixedhours').value === '38.5' && p.$('s-longhours').value === '50' && p.$('s-shorthours').value === '30.25' && p.$('s-alternating').checked === true);
    const rows = p.Views.forecast.generate();
    check(label + ': the Forecast now uses them (alternating 50 / 30.25)', rows.every(r => r.hours === 50 || r.hours === 30.25) && rows.some(r => r.hours === 50) && rows.some(r => r.hours === 30.25));
    p.$('s-alternating').checked = false; SAVE(p); await p.fire(); await tick();
    check(label + ': switching the pattern off saves fixed and the Forecast goes back to the fixed hours', p.App.data.settings.forecastHoursMode === 'fixed' && p.Views.forecast.generate().every(r => r.hours === 38.5));
    p.$('s-fixedhours').value = '0'; SAVE(p); await p.fire(); await tick();
    check(label + ': 0 forecast hours saves and the Forecast uses 0', p.App.data.settings.forecastFixedHours === 0 && p.Views.forecast.generate().every(r => r.hours === 0));

    // refusals: nothing saved, the box is named
    p = await newPage(file);
    const ref = snap(p); const writes = p.api.saved.length;
    for (const [id, val, name] of [['s-fixedhours', '', 'Forecast Hours per Week'], ['s-fixedhours', '169', 'Forecast Hours per Week'], ['s-fixedhours', '-1', 'Forecast Hours per Week'], ['s-fixedhours', '40.555', 'Forecast Hours per Week'],
      ['s-longhours', '', 'Long Week Hours'], ['s-longhours', '200', 'Long Week Hours'], ['s-shorthours', '', 'Short Week Hours'], ['s-shorthours', '168.5', 'Short Week Hours']]) {
      p.toasts.length = 0; p.$(id).value = val; SAVE(p); await p.fire(); await tick();
      check(label + ': ' + id + ' = "' + val + '" is refused, naming the box', p.toasts.length === 1 && p.toasts[0].t === 'error' && p.toasts[0].m.indexOf('Not saved. ' + name) === 0 && snap(p) === ref && p.api.saved.length === writes, JSON.stringify(p.toasts));
      p.App.renderCurrentView();
    }
    // alternating needs a start date
    p = await newPage(file);
    p.App.data.settings.alternatingSundayStart = ''; p.App.renderCurrentView();
    p.$('s-alternating').checked = true; p.toasts.length = 0; const ref2 = snap(p);
    SAVE(p); await p.fire(); await tick();
    check(label + ': alternating with no start date anywhere is refused and names the date', p.toasts.length === 1 && /Not saved\. Alternating Sunday Start Date/.test(p.toasts[0].m) && snap(p) === ref2, JSON.stringify(p.toasts));
    p.$('s-sundaystart').value = '2026-03-13'; p.toasts.length = 0; SAVE(p); await p.fire(); await tick();
    check(label + ': typing the date then lets it save', p.toasts[0].m === 'Settings saved' && p.App.data.settings.forecastHoursMode === 'alternating' && p.App.data.settings.alternatingSundayStart === '2026-03-13');
    // one bad box elsewhere blocks the new boxes too (all or nothing)
    p = await newPage(file);
    p.$('s-fixedhours').value = '45'; p.$('s-rate').value = '0'; const ref3 = snap(p); SAVE(p); await p.fire(); await tick();
    check(label + ': a bad box elsewhere blocks the hours from saving too', /^Not saved\. Hourly Rate/.test(p.toasts[0].m) && p.App.data.settings.forecastFixedHours === 40 && snap(p) === ref3, JSON.stringify(p.toasts));
    check(label + ': no page errors', p.errors.length === 0, p.errors.join(' | '));
  }

  // old page without the new boxes: nothing is reset
  let p = await newPage(v2);
  const ws = ['s-fixedhours', 's-alternating', 's-longhours', 's-shorthours'];
  p.App.data.settings.forecastFixedHours = 42; p.App.data.settings.forecastHoursMode = 'alternating'; p.App.data.settings.forecastLongWeekHours = 47; p.App.data.settings.forecastShortWeekHours = 33; p.App.renderCurrentView();
  for (const id of ws) { const el = p.$(id); el.parentNode.removeChild(el); }
  SAVE(p); await p.fire(); await tick();
  check('L5 with the new boxes missing from the page the saved hours are left alone', p.toasts[0].m === 'Settings saved' && p.App.data.settings.forecastFixedHours === 42 && p.App.data.settings.forecastHoursMode === 'alternating' && p.App.data.settings.forecastLongWeekHours === 47 && p.App.data.settings.forecastShortWeekHours === 33);

  // L4 sustained: 40 saves in a row, alternating the switch
  p = await newPage(v2); let ok = true;
  for (let i = 0; i < 40; i++) { p.$('s-alternating').checked = i % 2 === 0; p.$('s-fixedhours').value = String(30 + i); p.toasts.length = 0; SAVE(p); await p.fire(); await tick();
    const s = p.App.data.settings; if (p.toasts[0].m !== 'Settings saved' || s.forecastFixedHours !== 30 + i || s.forecastHoursMode !== (i % 2 === 0 ? 'alternating' : 'fixed')) { ok = false; break; } p.App.renderCurrentView(); }
  check('L4 40 saves in a row all land correctly', ok);
  // L5 junk typed into the boxes
  p = await newPage(v2); let nothrow = true;
  try { for (const val of ['abc', '1e999', '9'.repeat(5000), '0x10', ' ', '4 0', '😀', '--1', '١٢']) for (const id of ['s-fixedhours', 's-longhours', 's-shorthours']) { p.$(id).value = val; SAVE(p); await p.fire(); p.App.renderCurrentView(); } } catch (e) { nothrow = false; console.log(e.stack); }
  check('L5 junk typed into the hours boxes never crashes and the settings stay sane', nothrow && Number.isFinite(p.App.data.settings.forecastFixedHours));
  check('L5 no page errors', p.errors.length === 0, p.errors.join(' | '));
  clearTimeout(watchdog);
  console.log(failed === 0 ? passed + '/' + passed + ' passed' : passed + ' passed, ' + failed + ' FAILED');
  process.exit(failed === 0 ? 0 : 1);
})();