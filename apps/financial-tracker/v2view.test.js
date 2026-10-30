// Run:  node v2view.test.js     (from apps/financial-tracker)
const fs = require('fs'), path = require('path');
const V = require('./v2view.js'), M = require('./migrate.js'), L = require('./ledger.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const TODAY = '2026-10-29';
const tx = (accountId, date, amount, balance, extra) => Object.assign({ id: accountId + '-' + date + '-' + amount, accountId, date, description: 'd', amount, balance, type: 'transaction' }, extra || {});

// L1 static: the bridge never touches files, the clock or the page
const src = fs.readFileSync(path.join(__dirname, 'v2view.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
check('L1 no file, clock or page access', !/require\('fs'\)|new Date|Date\.now|document\.|window\./.test(src));

// L2 round trip: old file -> v2 -> page view must give back the old page's amounts, running balances and balances
const old = { accounts: { vault: 0, cc: 0, car_loan: 0 }, settings: { regularRate: 35.21 }, paychecks: [{ id: 'p' }], transactions: [
  tx('vault', '2026-02-01', 1000, 1000), tx('vault', '2026-02-02', -100, 900),
  tx('cc', '2026-02-03', 50, 50),
  tx('vault', '2026-02-04', -20, 880, { id: 't1', type: 'transfer', linkedId: 't2' }), tx('cc', '2026-02-04', 20, 30, { id: 't2', type: 'transfer', linkedId: 't1' }),
  tx('vault', '2026-02-05', -10, 870, { id: 't3', type: 'transfer', linkedId: 't4' }), tx('cc', '2026-02-05', 10, 40, { id: 't4', type: 'transfer', linkedId: 't3' }),
  tx('car_loan', '2026-02-06', 5000, 5000), tx('car_loan', '2026-02-07', -100, 4900)] };
const conv = M.convert(old, { today: TODAY });
check('conversion works', conv.ok && V.isV2(conv.data));
const pv = V.toPageData(conv.data, TODAY);
for (const o of old.transactions) {
  const p = pv.transactions.find(t => t.id === conv.data.transactions.find(x => x.accountId === o.accountId && x.date === o.date && x.description === o.description && x.id.indexOf(o.id) === 0).id);
  check('page row ' + o.id + ': amount and running balance equal the old page (' + o.amount + ' / ' + o.balance + ')', !!p && Math.abs(p.amount - o.amount) < 1e-9 && Math.abs(p.balance - o.balance) < 1e-9, p ? p.amount + ' / ' + p.balance : 'missing');
}
check('page balances equal the old page', pv.accounts.vault === 870 && pv.accounts.cc === 40 && pv.accounts.car_loan === 4900);
check('other file keys carry over, version flag gone, input untouched', pv.settings.regularRate === 35.21 && pv.paychecks.length === 1 && pv.schemaVersion === undefined && conv.data.schemaVersion === 2);

// L2 migration adjustments are kept out of the list and shown separately, with a running balance
const typo = M.convert({ accounts: {}, transactions: [tx('vault', '2026-03-01', 100, 100), tx('vault', '2026-03-02', -10, 100)] }, { today: TODAY });
const pt = V.toPageData(typo.data, TODAY);
check('adjustment is not in the normal list, is in migrationEntries, balance matches the old page (100)', pt.transactions.length === 2 && pt.migrationEntries.length === 1 && pt.migrationEntries[0].amount === 10 && pt.migrationEntries[0].balance === 100 && pt.accounts.vault === 100);

// L2 future-dated entries count only from their date; entries before the opening date do not move the balance
const fut = { schemaVersion: 2, accounts: [{ id: 'vault', name: 'V', kind: 'bank', role: 'vault', openingCents: 1000, openingDate: '2026-01-10', closed: false }],
  transactions: [{ id: 'a', accountId: 'vault', date: '2026-01-05', description: 'old', amountCents: 999, type: 'transaction' }, { id: 'b', accountId: 'vault', date: '2026-11-30', description: 'later', amountCents: 500, type: 'transaction' }, { id: 'c', accountId: 'vault', date: '2026-01-11', description: 'x', amountCents: -200, type: 'transaction' }] };
const pf = V.toPageData(fut, TODAY);
check('balance today ignores the future entry and the pre-opening entry (8.00)', pf.accounts.vault === 8);
check('running balances: 10.00 (pre-opening, unchanged), 8.00, 13.00', JSON.stringify(pf.transactions.map(t => t.balance)) === JSON.stringify([10, 8, 13]));

// L3 same math as ledger.js for every account (random-ish data)
const many = { schemaVersion: 2, accounts: [{ id: 'b', kind: 'bank', role: 'none', openingCents: 123, openingDate: '2026-01-01' }, { id: 'c', kind: 'credit_card', role: 'none', openingCents: 5000, openingDate: '2026-01-01' }], transactions: [] };
for (let i = 0; i < 300; i++) many.transactions.push({ id: 'x' + i, accountId: i % 2 ? 'b' : 'c', date: '2026-0' + (1 + (i % 9)) + '-' + String(1 + (i % 28)).padStart(2, '0'), description: 'd', amountCents: (i * 37 % 1000) - 400, type: 'transaction' });
const pm = V.toPageData(many, '2026-12-31');
check('300 entries: balances equal ledger.js to the cent', pm.accounts.b === L.balanceCents(many, 'b', '2026-12-31') / 100 && pm.accounts.c === L.balanceCents(many, 'c', '2026-12-31') / 100);
const lastB = pm.transactions.filter(t => t.accountId === 'b').slice(-1)[0], lastC = pm.transactions.filter(t => t.accountId === 'c').slice(-1)[0];
check('last running balance of each account equals its balance', lastB.balance === pm.accounts.b && lastC.balance === pm.accounts.c);

// L5 junk never crashes
let crashed = false;
try { V.toPageData({ schemaVersion: 2 }, TODAY); V.toPageData({ schemaVersion: 2, accounts: [null, 5, { id: 'x', kind: 'bank' }], transactions: [null, 'a', { accountId: 'x', date: 5, amountCents: 1 }, { accountId: 'x', date: '2026-01-01', amountCents: 1.5 }] }, TODAY); } catch (e) { crashed = true; }
check('L5 junk entries and a missing accounts list do not crash', !crashed);
check('isV2 only says yes for an object with schemaVersion 2', V.isV2({ schemaVersion: 2 }) && !V.isV2({ schemaVersion: 1 }) && !V.isV2(null) && !V.isV2([]) && !V.isV2({}));
console.log(passed + '/' + (passed + failed) + ' passed');
process.exit(failed ? 1 : 0);