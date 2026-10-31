// Run:  node pagerec.test.js     (needs jsdom, like renderer.test.js)
// The paycheck recommendation cards on the REAL page, for a v1 file and the same data as a v2 file:
// FLEX first, then FUNDS up to $100 above where it was at the previous approved paycheck, then VAULT
// up to its target (7 months of expenses + $1,500), any extra to FUNDS. No Car Fund anywhere.
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
const fixed = [{ id: 'f1', name: 'Rent', amount: 1000, frequency: 'monthly' }, { id: 'f2', name: 'Fuel', amount: 40, frequency: 'weekly' }, { id: 'f3', name: 'Fun', amount: 20, frequency: 'weekly' }];
const mkOld = (o) => { o = o || {}; return { accounts: {}, settings: Object.assign({ vaultBufferMonths: 7 }, o.settings), fixedExpenses: fixed, groceries: [], creditScores: [],
  paychecks: o.paychecks || [pay('pa', '2026-09-04', 1000, true), pay('pb', '2026-09-11', 1100, true), pay('pc', '2026-09-18', 1200, true), pay('pd', '2026-09-25', 1000, false)],
  transactions: [tx('vault', '2026-01-01', o.vault === undefined ? 5000 : o.vault, o.vault === undefined ? 5000 : o.vault), tx('funds', '2026-09-04', 2000, 2000), tx('funds', '2026-09-11', 300, 2300), tx('funds', '2026-09-18', 350, 2650)] }; };

function makePage() {
  const errors = [];
  const api = { saved: [], handlers: {}, saveData: async (j) => { api.saved.push(j); return { ok: true }; }, createNewFile: async () => ({ ok: true }), loadFile: async () => ({ ok: false, canceled: true }), importFile: async () => ({ ok: false }), openBackupsFolder: async () => '', getAppInfo: async () => ({}), openExternal: async () => {}, flushDone: () => Promise.resolve(),
    onInitialData: (cb) => { api.handlers.initial = cb; }, onLoadProblem: (cb) => { api.handlers.problem = cb; }, onFlushRequest: (cb) => { api.handlers.flush = cb; } };
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.message || e).slice(0, 200)));
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/', beforeParse(w) {
    w.electronAPI = api; w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {}; w.ExcelJS = {};
    w.setTimeout = () => 0; w.clearTimeout = () => {}; w.HTMLCanvasElement.prototype.getContext = () => null; } });
  const w = dom.window, App = w.eval('App');
  const open = async (file) => { api.handlers.initial({ path: 'C:\\x\\f.json', data: JSON.stringify(file) }); await tick(); App.currentView = 'dashboard'; App.renderCurrentView(); };
  const cards = () => [...w.document.querySelectorAll('#view-container .card')].filter(c => /Paycheck Recommendation/.test(c.textContent));
  const amounts = (card) => { const g = (re) => { const m = card.textContent.match(re); return m ? Number(m[1].replace(/,/g, '')) : null; }; return { flex: g(/Transfer to FLEX\s*\$([\d,]+\.\d\d)/), funds: g(/Transfer to FUNDS\s*\$([\d,]+\.\d\d)/), vault: g(/Keep in VAULT\s*\$([\d,]+\.\d\d)/) }; };
  return { w, App, errors, open, cards, amounts, api };
}
const both = async (old, fn) => { for (const kind of ['v1', 'v2']) { const p = makePage(); await tick(); await p.open(kind === 'v1' ? old : M.convert(old, { today: '2026-10-29' }).data); await fn(p, kind); } };

(async () => {
  check('L1 the old Car Fund recommendation code is gone and the page loads paycheckrec.js', !/carFundNote/.test(rd('index.html')) && rd('index.html').includes('<script src="paycheckrec.js"></script>') && /"paycheckrec\.js"/.test(rd('package.json')));

  // L3 the main scenario: approved card (C) and predicted card (D)
  await both(mkOld(), async (p, kind) => {
    const cs = p.cards(); const ap = p.amounts(cs[0]), pr = p.amounts(cs[1]);
    check(kind + ': two cards', cs.length === 2);
    check(kind + ' approved card (last paycheck, pay 1200): FLEX 60, FUNDS 0 (already above last time + 100), VAULT 1,140', ap.flex === 60 && ap.funds === 0 && ap.vault === 1140, JSON.stringify(ap));
    check(kind + ' approved card says savings is on track', /Savings: on track/.test(cs[0].textContent));
    check(kind + ' predicted card (pay 1000): FLEX 60, FUNDS 100 (2,650 -> 2,750), VAULT 840', pr.flex === 60 && pr.funds === 100 && pr.vault === 840, JSON.stringify(pr));
    check(kind + ' predicted card explains the FUNDS target', /so FUNDS reaches \$2,750\.00/.test(cs[1].textContent), cs[1].textContent.replace(/\s+/g, ' ').slice(0, 300));
    check(kind + ': no Car Fund anywhere in the recommendation cards', cs.every(c => !/Car Fund/i.test(c.textContent)));
    check(kind + ': FLEX + FUNDS + VAULT = net pay on both cards', ap.flex + ap.funds + ap.vault === 1200 && pr.flex + pr.funds + pr.vault === 1000);
    check(kind + ': the VAULT target is 7 months of expenses + 1,500 (10,318.60), not 8 months', Math.abs(p.App.calc.vaultBufferTarget() - 10318.6) < 0.005, String(p.App.calc.vaultBufferTarget()));
    check(kind + ': no NaN / undefined on the page, no errors', !/NaN|undefined/.test(p.w.document.getElementById('view-container').textContent) && p.errors.length === 0, p.errors.join(' | '));
  });

  // the baseline is the PREVIOUS approved paycheck, and later FUNDS entries do not count
  await both(mkOld(), async (p, kind) => {
    const pcs = p.App.data.paychecks, c = pcs.find(x => x.id === 'pc'), d = pcs.find(x => x.id === 'pd'), a = pcs.find(x => x.id === 'pa');
    check(kind + ': the previous approved paycheck of C is B, of D is C, of A is none', p.App.calc.previousApprovedPaycheck(c).id === 'pb' && p.App.calc.previousApprovedPaycheck(d).id === 'pc' && p.App.calc.previousApprovedPaycheck(a) === null);
    check(kind + ': FUNDS at the end of a day: 09-03 = 0, 09-04 = 2000, 09-10 = 2000, 09-11 = 2300, 09-17 = 2300, 09-18 = 2650, later = 2650', [['2026-09-03', 0], ['2026-09-04', 2000], ['2026-09-10', 2000], ['2026-09-11', 2300], ['2026-09-17', 2300], ['2026-09-18', 2650], ['2026-12-31', 2650]].every(([d2, v]) => p.App.calc.fundsAsOf(d2) === v), JSON.stringify([p.App.calc.fundsAsOf('2026-09-03'), p.App.calc.fundsAsOf('2026-09-10'), p.App.calc.fundsAsOf('2026-09-17')]));
    check(kind + ': an unusable day gives null, not a guess', p.App.calc.fundsAsOf(null) === null && p.App.calc.fundsAsOf('') === null);
  });

  // two paychecks on the SAME day are not "before" each other
  await both(mkOld({ paychecks: [pay('p1', '2026-09-11', 1100, true), pay('p2', '2026-09-11', 500, true), pay('pd', '2026-09-25', 1000, false)] }), async (p, kind) => {
    const f = (id) => p.App.data.paychecks.find(x => x.id === id);
    check(kind + ': same-day approved paychecks are not each other\'s "previous"; the predicted one compares with one of them', p.App.calc.previousApprovedPaycheck(f('p1')) === null && p.App.calc.previousApprovedPaycheck(f('p2')) === null && ['p1', 'p2'].includes(p.App.calc.previousApprovedPaycheck(f('pd')).id));
  });

  // only one approved paycheck: nothing earlier to compare with
  await both(mkOld({ paychecks: [pay('pc', '2026-09-18', 1200, true), pay('pd', '2026-09-25', 1000, false)] }), async (p, kind) => {
    const cs = p.cards(); const ap = p.amounts(cs[0]), pr = p.amounts(cs[1]);
    check(kind + ': first approved paycheck has nothing to compare with: FUNDS +100 and the card says why', ap.funds === 100 && ap.vault === 1040 && /no earlier approved paycheck/.test(cs[0].textContent), JSON.stringify(ap));
    check(kind + ': the predicted one compares with that paycheck (FUNDS 2,650)', pr.funds === 100 && pr.vault === 840);
  });

  // VAULT already full: the extra goes to FUNDS
  await both(mkOld({ vault: 20000 }), async (p, kind) => {
    const cs = p.cards(); const ap = p.amounts(cs[0]), pr = p.amounts(cs[1]);
    check(kind + ': VAULT over target: nothing to VAULT, everything else to FUNDS (predicted: 100 + 840 = 940)', pr.vault === 0 && pr.funds === 940 && pr.flex === 60, JSON.stringify(pr));
    check(kind + ': approved card: all 1,140 to FUNDS', ap.vault === 0 && ap.funds === 1140);
    check(kind + ': the card says VAULT is full and where the extra goes', /VAULT is full: extra \$840\.00 goes to FUNDS/.test(cs[1].textContent));
  });

  // the months setting is honoured (6 months here)
  await both(mkOld({ settings: { vaultBufferMonths: 6 } }), async (p, kind) => {
    check(kind + ': 6 months -> target 9,058.80', Math.abs(p.App.calc.vaultBufferTarget() - 9058.8) < 0.005, String(p.App.calc.vaultBufferTarget()));
  });

  // awkward paychecks
  await both(mkOld({ paychecks: [pay('pb', '2026-09-11', 1100, true), pay('px', 'garbage', 900, true), pay('pd', '2026-09-25', 1000, false)] }), async (p, kind) => {
    check(kind + ': a paycheck with a bad date does not break the page', p.cards().length === 2 && !/NaN|undefined/.test(p.cards().map(c => c.textContent).join('')) && p.errors.length === 0, p.errors.join(' | '));
  });
  await both(mkOld({ paychecks: [] }), async (p, kind) => {
    check(kind + ': no paychecks at all: both cards say so, no crash', p.cards().length === 2 && p.cards().every(c => /No .* paycheck found/.test(c.textContent)) && p.errors.length === 0);
  });
  await both(mkOld({ paychecks: [pay('pz', '2026-09-18', 0, true), pay('pd', '2026-09-25', 30, false)] }), async (p, kind) => {
    const pr = p.amounts(p.cards()[1]);
    check(kind + ': pay (30) smaller than the FLEX allowance (60): all 30 to FLEX, nothing else', pr.flex === 30 && pr.funds === 0 && pr.vault === 0, JSON.stringify(pr));
  });

  // v2 with a migration adjustment on FUNDS: the baseline comes from the ledger (adjustment included)
  const messy = mkOld(); messy.transactions[2].balance = 2400; messy.transactions[3].balance = 2750;  // typed balances 100 above the math
  const conv = M.convert(messy, { today: '2026-10-29' });
  check('setup: the messy file converts and needs a migration adjustment on FUNDS', conv.ok && conv.data.transactions.some(t => t.type === 'migration_adjustment' && t.accountId === 'funds'));
  const pm = makePage(); await tick(); await pm.open(conv.data);
  const same = ['2026-09-04', '2026-09-11', '2026-09-18', '2026-10-30'].every(d => pm.App.calc.fundsAsOf(d) === L.balanceCents(conv.data, 'funds', d) / 100);
  check('v2 with an adjustment: FUNDS as-of equals the ledger at every date', same, JSON.stringify(['2026-09-11', '2026-09-18'].map(d => [pm.App.calc.fundsAsOf(d), L.balanceCents(conv.data, 'funds', d) / 100])));
  check('v2 with an adjustment: the cards still render without errors', pm.cards().length === 2 && pm.errors.length === 0, pm.errors.join(' | '));

  console.log(passed + '/' + (passed + failed) + ' passed');
  process.exit(failed ? 1 : 0);
})();