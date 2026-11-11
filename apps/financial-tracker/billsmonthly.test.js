// Run:  node billsmonthly.test.js     (from apps/financial-tracker)
// What the fixed expenses cost per month (this feeds the VAULT target). Weekly x 4.33 a month, biweekly = 26 a year,
// quarterly = amount / 3, yearly = amount / 12. Finished expenses (end date before today) do not count; expenses that
// have not started yet DO count. Junk never throws.
const fs = require('fs'), path = require('path');
const B = require('./bills.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const near = (a, b) => Math.abs(a - b) < 1e-9;
const E = (frequency, amount, extra) => Object.assign({ name: 'x', frequency, amount }, extra || {});
const tot = (list, today) => B.monthlyTotal(list, today === undefined ? '2026-11-10' : today);

const src = fs.readFileSync(path.join(__dirname, 'bills.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\s\/\/ .*$/gm, '');
check('L1 bills.js still never reads the clock or builds Dates', !/new Date|Date\.now|toISOString|getTimezoneOffset/.test(src));

// per-expense monthly amounts
check('monthly counts as is', B.monthlyAmount(E('monthly', 1000)) === 1000);
check('weekly counts 4.33 weeks a month when multiplying (not 4)', near(B.monthlyAmount(E('weekly', 60)), 259.8) && near(B.monthlyAmount(E('weekly', 100)), 433));
check('biweekly counts 26 payments a year / 12', near(B.monthlyAmount(E('biweekly', 120)), 260));
check('quarterly: amount / 3 ($300 every 3 months = $100 a month)', B.monthlyAmount(E('quarterly', 300)) === 100);
check('yearly: amount / 12 ($1,200 a year = $100 a month)', B.monthlyAmount(E('yearly', 1200)) === 100);
check('cents survive (yearly 100.50 / 12)', near(B.monthlyAmount(E('yearly', 100.5)), 8.375));
check('text amounts are read as numbers (no string joining)', B.monthlyAmount(E('monthly', '250')) === 250 && tot([E('monthly', '100'), E('monthly', '50')]) === 150);
for (const bad of [undefined, null, 'abc', NaN, Infinity, {}, []]) check('junk amount ' + String(bad) + ' counts 0', B.monthlyAmount(E('monthly', bad)) === 0 || (Array.isArray(bad) && B.monthlyAmount(E('monthly', bad)) === 0));
check('unknown frequency counts 0', B.monthlyAmount(E('fortnightly', 50)) === 0 && B.monthlyAmount(E(undefined, 50)) === 0 && B.monthlyAmount(null) === 0 && B.monthlyAmount('x') === 0);

// totals and dates
check('a mixed list adds up', near(tot([E('monthly', 1000), E('weekly', 60), E('quarterly', 300), E('yearly', 1200)]), 1000 + 259.8 + 100 + 100));
check('empty or not a list: 0', tot([]) === 0 && tot(null) === 0 && tot(undefined) === 0 && tot('x') === 0 && tot({}) === 0);
check('an expense that ended yesterday does not count', tot([E('monthly', 500, { endDate: '2026-11-09' }), E('monthly', 100)]) === 100);
check('an expense that ends TODAY still counts (last day is included)', tot([E('monthly', 500, { endDate: '2026-11-10' })]) === 500);
check('an expense that ends later counts', tot([E('monthly', 500, { endDate: '2027-01-01' })]) === 500);
check('an expense that has NOT STARTED yet still counts (planning ahead)', tot([E('monthly', 500, { startDate: '2027-06-01' })]) === 500 && tot([E('yearly', 1200, { startDate: '2030-01-01' })]) === 100);
check('a junk end date is ignored, not treated as finished', tot([E('monthly', 500, { endDate: 'soon' }), E('monthly', 5, { endDate: '' }), E('monthly', 5, { endDate: null })]) === 510);
check('a junk "today" counts everything (safe side)', B.monthlyTotal([E('monthly', 500, { endDate: '2020-01-01' })], 'junk') === 500 && B.monthlyTotal([E('monthly', 500, { endDate: '2020-01-01' })]) === 500);
check('non-object entries in the list are skipped', tot([null, 'x', 5, undefined, E('monthly', 10)]) === 10);
check('the day boundary follows the calendar, not the clock', B.monthlyTotal([E('monthly', 1, { endDate: '2026-12-31' })], '2026-12-31') === 1 && B.monthlyTotal([E('monthly', 1, { endDate: '2026-12-31' })], '2027-01-01') === 0);
check('the input list is not changed', (() => { const l = [E('weekly', 10, { endDate: '2020-01-01' })]; const c = JSON.stringify(l); tot(l); return JSON.stringify(l) === c; })());

// L4/L5 stress
let threw = 0, bad = 0, seed = 4242;
const rnd = (n) => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) % n;
const freqs = ['monthly', 'weekly', 'biweekly', 'quarterly', 'yearly', 'x', undefined];
const amts = [0, 1, 99.99, '12', 'abc', null, undefined, 1e6, -5, NaN];
for (let i = 0; i < 20000; i++) {
  const list = []; for (let k = 0; k < 1 + rnd(5); k++) list.push({ frequency: freqs[rnd(7)], amount: amts[rnd(10)], endDate: [null, '2020-01-01', '2030-01-01', 'bad'][rnd(4)], startDate: [null, '2031-01-01'][rnd(2)] });
  try { const t = B.monthlyTotal(list, '2026-11-10'); if (!Number.isFinite(t)) bad++; } catch (e) { threw++; }
}
check('20,000 random lists: never throws, always a finite number', threw === 0 && bad === 0, 'threw=' + threw + ' bad=' + bad);
check('a 100,000-expense list adds up fast', (() => { const t = Date.now(); const l = []; for (let i = 0; i < 100000; i++) l.push(E('monthly', 1)); const s = B.monthlyTotal(l, '2026-11-10'); return s === 100000 && Date.now() - t < 3000; })());

console.log(passed + '/' + (passed + failed) + ' passed');
process.exit(failed ? 1 : 0);