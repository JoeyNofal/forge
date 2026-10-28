// Run:  node bills.test.js     (from apps/financial-tracker)
const fs = require('fs'), path = require('path');
const B = require('./bills.js'), D = require('./dates.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const up = B.upcomingBills;
const dates = (list) => list.map(b => b.date).join(',');
const one = (e, today, days) => dates(up([e], today, days));
const M = (dueDay, extra) => Object.assign({ name: 'Bill', amount: 10, frequency: 'monthly', dueDay }, extra || {});

// ---------- L1 static ----------
const src = fs.readFileSync(path.join(__dirname, 'bills.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\s\/\/ .*$/gm, '');
check('L1 bills.js never reads the clock or builds Dates', !/new Date|Date\.now|toISOString|getTimezoneOffset/.test(src));
check('L1 bills.js only depends on dates.js', (src.match(/require\(/g) || []).length === 1);

// ---------- L2 the real bugs ----------
check('a bill due TODAY is listed (it used to vanish)', one(M(26), '2026-10-26') === '2026-10-26');
check('a monthly bill due yesterday moves to next month', one(M(25), '2026-10-26') === '2026-11-25');
check('day 31 in a 30-day month is the 30th', one(M(31), '2026-04-01') === '2026-04-30');
check('day 31 in February is the 28th, not March 3', one(M(31), '2026-02-10') === '2026-02-28' && one(M(31), '2026-02-10', 30) !== '2026-03-03');
check('day 31 in a leap February is the 29th', one(M(31), '2028-02-10') === '2028-02-29');
check('day 30 and 29 in a short February', one(M(30), '2026-02-01') === '2026-02-28' && one(M(29), '2026-02-01') === '2026-02-28' && one(M(29), '2028-02-01') === '2028-02-29');
check('window includes day 30 from today and excludes day 31', one(M(1), '2026-10-01') === '2026-10-01' && one(M(31), '2026-10-01') === '2026-10-31' && one(M(1), '2026-10-02') === '2026-11-01' && one(M(2), '2026-10-02') === '2026-10-02');
check('window end is inclusive (today + 30)', one(M(1), '2026-10-02') === '2026-11-01' && one(M(2), '2026-10-02') === '2026-10-02');
check('December rolls into January', one(M(5), '2026-12-20') === '2027-01-05');
check('window spanning three months lists each month it touches', dates(up([M(1)], '2026-01-31')) === '2026-02-01,2026-03-01');
check('missing / odd due day means the 1st', one(M(undefined), '2026-10-26') === '2026-11-01' && one(M(0), '2026-10-26') === '2026-11-01' && one(M(-5), '2026-10-26') === '2026-11-01' && one(M(15.5), '2026-10-26') === '2026-11-01' && one(M(NaN), '2026-10-26') === '2026-11-01' && one(M('abc'), '2026-10-26') === '2026-11-01');
check('due day typed as text works', one(M('28'), '2026-10-26') === '2026-10-28' && one(M(' 28 '), '2026-10-26') === '2026-10-28');
check('due day 40 is clamped to the last day', one(M(40), '2026-10-26') === '2026-10-31');

// ---------- L2 start and end dates ----------
check('finished expense is not listed', one(M(28, { endDate: '2026-10-20' }), '2026-10-26') === '');
check('expense ending today is still due today', one(M(26, { endDate: '2026-10-26' }), '2026-10-26') === '2026-10-26');
check('only the occurrences before the end date are listed', one({ name: 'x', frequency: 'biweekly', startDate: '2026-10-02', endDate: '2026-10-31' }, '2026-10-26') === '2026-10-30');
check('monthly bill ending before its next due date is not listed', one(M(5, { endDate: '2026-10-30' }), '2026-10-26') === '');
check('a bill that has not started yet is not listed early', one(M(5, { startDate: '2026-12-01' }), '2026-10-26') === '' && one(M(28, { startDate: '2026-10-28' }), '2026-10-26') === '2026-10-28' && one(M(27, { startDate: '2026-10-28' }), '2026-10-26') === '');
check('bad start/end dates are ignored (not a crash)', one(M(28, { startDate: 'junk', endDate: 'junk' }), '2026-10-26') === '2026-10-28');

// ---------- L2 biweekly and weekly ----------
const BW = (s) => ({ name: 'Loan', amount: 5, frequency: 'biweekly', startDate: s });
check('biweekly counts every 14 days from the start date', dates(up([BW('2026-10-02')], '2026-10-26')) === '2026-10-30,2026-11-13');
check('biweekly start in the future', dates(up([BW('2026-11-10')], '2026-10-26')) === '2026-11-10,2026-11-24');
check('biweekly start today', dates(up([BW('2026-10-26')], '2026-10-26')) === '2026-10-26,2026-11-09,2026-11-23');
check('biweekly start long ago is fast and right', dates(up([BW('1900-01-01')], '2026-10-26')).split(',').every(d => D.daysBetween('1900-01-01', d) % 14 === 0) && up([BW('1900-01-01')], '2026-10-26').length >= 2);
check('biweekly without a start date is not listed', one({ name: 'x', frequency: 'biweekly' }, '2026-10-26') === '');
check('weekly counts from its start date weekday', dates(up([{ name: 'x', frequency: 'weekly', startDate: '2026-10-23' }], '2026-10-26')) === '2026-10-30,2026-11-06,2026-11-13,2026-11-20');
check('weekly with no start date counts from tomorrow (as before)', dates(up([{ name: 'x', frequency: 'weekly' }], '2026-10-26')) === '2026-10-27,2026-11-03,2026-11-10,2026-11-17,2026-11-24');
check('unknown frequencies are skipped', one({ name: 'x', frequency: 'yearly', dueDay: 5 }, '2026-10-26') === '' && one({ name: 'x' }, '2026-10-26') === '');

// ---------- L2 order, fields, window ----------
const mix = up([M(28, { name: 'B' }), M(28, { name: 'A' }), M(27, { name: 'Z' })], '2026-10-26');
check('sorted by date, then name', mix.map(b => b.name).join('') === 'ZAB');
check('fields are passed through', up([{ name: 'Rent', amount: 1200, frequency: 'monthly', dueDay: 28 }], '2026-10-26')[0].amount === 1200 && up([{ name: 'Rent', amount: 1200, frequency: 'monthly', dueDay: 28 }], '2026-10-26')[0].freq === 'monthly');
check('days parameter', one(M(10), '2026-10-26', 5) === '' && one(M(30), '2026-10-26', 5) === '2026-10-30' && one(M(10), '2026-10-26', 0) === '' && one(M(26), '2026-10-26', 0) === '2026-10-26');
check('input list is not changed', (() => { const l = [M(28)]; const c = JSON.stringify(l); up(l, '2026-10-26'); return JSON.stringify(l) === c; })());

// ---------- L2 bad input ----------
for (const bad of [null, undefined, {}, 'x', 5, true]) check('expenses = ' + JSON.stringify(bad) + ' gives an empty list', up(bad, '2026-10-26').length === 0);
for (const bad of [null, undefined, '', 'x', 5, '2026-02-30', {}, new Date(NaN)]) check('today = ' + JSON.stringify(bad) + ' gives an empty list', up([M(5)], bad).length === 0);
for (const bad of [-1, 1.5, NaN, 1000, '30', null]) check('days = ' + JSON.stringify(bad) + ' gives an empty list', up([M(5)], '2026-10-26', bad).length === 0);
check('junk entries in the list are skipped, good ones kept', dates(up([null, 5, 'x', [], undefined, M(28)], '2026-10-26')) === '2026-10-28');
check('missing name does not crash sorting', up([{ frequency: 'monthly', dueDay: 28 }, { frequency: 'monthly', dueDay: 28, name: 'A' }], '2026-10-26').length === 2);

// ---------- L4 sustained: 3,000 random cases, every rule checked ----------
let seed = 99; const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
const ri = (a, b) => a + Math.floor(rnd() * (b - a + 1));
const rdate = () => D.addDays('2024-01-01', ri(0, 1500));
let ok = true, why = '';
for (let i = 0; i < 3000 && ok; i++) {
  const today = rdate(), list = [];
  for (let j = 0; j < ri(1, 8); j++) {
    const f = ['monthly', 'biweekly', 'weekly'][ri(0, 2)];
    const e = { name: 'n' + j, amount: j, frequency: f, dueDay: ri(1, 31) };
    if (rnd() < 0.5) e.startDate = D.addDays(today, ri(-400, 60));
    if (rnd() < 0.4) e.endDate = D.addDays(today, ri(-30, 90));
    list.push(e);
  }
  const res = up(list, today), to = D.addDays(today, 30);
  for (let k = 0; k < res.length && ok; k++) {
    const b = res[k], e = list[+b.name.slice(1)];
    if (D.compare(b.date, today) < 0 || D.compare(b.date, to) > 0) { ok = false; why = 'outside window'; }
    if (k && res[k - 1].date > b.date) { ok = false; why = 'unsorted'; }
    if (e.endDate && D.compare(b.date, e.endDate) > 0) { ok = false; why = 'after end'; }
    if (e.startDate && D.compare(b.date, e.startDate) < 0) { ok = false; why = 'before start'; }
    if (e.frequency === 'monthly') { const y = +b.date.slice(0, 4), m = +b.date.slice(5, 7); if (b.date !== D.dueDateInMonth(y, m, e.dueDay)) { ok = false; why = 'wrong monthly day'; } }
    if (e.frequency !== 'monthly') { const step = e.frequency === 'weekly' ? 7 : 14; const anchor = e.startDate || D.addDays(today, 1); if (D.daysBetween(anchor, b.date) % step !== 0) { ok = false; why = 'off the ' + step + '-day count'; } }
  }
  // nothing missed: every monthly expense that should be due in the window appears
  for (const e of list) if (e.frequency === 'monthly' && ok) {
    const want = [];
    for (let d = today; D.compare(d, to) <= 0; d = D.addDays(d, 1)) { const y = +d.slice(0, 4), m = +d.slice(5, 7); if (d === D.dueDateInMonth(y, m, e.dueDay)) want.push(d); }
    const got = res.filter(b => b.name === e.name).map(b => b.date);
    const inLife = want.filter(d => (!e.startDate || d >= e.startDate) && (!e.endDate || d <= e.endDate));
    if (JSON.stringify(got) !== JSON.stringify(inLife)) { ok = false; why = 'monthly missed or extra: ' + JSON.stringify({ today, e, got, inLife }); }
  }
}
check('L4 3,000 random cases: every rule holds, nothing missed or extra', ok, why);

// ---------- L5 extreme ----------
const t0 = Date.now(); const many = Array.from({ length: 20000 }, (_, i) => M((i % 31) + 1, { name: 'n' + i }));
check('L5 20,000 expenses are handled quickly', up(many, '2026-10-26').length > 1000 && Date.now() - t0 < 3000, (Date.now() - t0) + 'ms');
check('L5 hostile fields do not crash', (() => { try { up([{ frequency: 'monthly', dueDay: {}, startDate: [], endDate: {}, name: Symbol('x') }, { frequency: 'weekly', startDate: 'x'.repeat(100000) }, { frequency: 'biweekly', startDate: '2199-12-31' }, { frequency: 'biweekly', startDate: '1900-01-01', endDate: '1900-01-02' }], '2026-10-26'); return true; } catch (e) { return false; } })());
check('L5 dates near the supported limits', up([M(31)], '2200-12-01').length >= 0 && up([M(1)], '1900-01-01').length >= 1);
check('L5 a year boundary every month of the year', Array.from({ length: 12 }, (_, m) => up([M(15)], '2026-' + String(m + 1).padStart(2, '0') + '-20').length).every(n => n === 1));
check('L5 leap day as today', one(M(29), '2028-02-29') === '2028-02-29,2028-03-29' && one(M(1), '2028-02-29') === '2028-03-01');

console.log(failed === 0 ? passed + '/' + passed + ' passed' : passed + '/' + (passed + failed) + ' passed, ' + failed + ' FAILED');
process.exit(failed === 0 ? 0 : 1);