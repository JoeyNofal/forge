// Run:  node billsperiodic.test.js     (from apps/financial-tracker)
// Yearly and quarterly bills in "Upcoming Bills". A yearly bill falls due every year on its START date's month and
// day; a quarterly bill every 3 months on that day. Without a start date they are skipped (nothing to count from).
const fs = require('fs'), path = require('path');
const B = require('./bills.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const up = B.upcomingBills;
const dates = (list) => list.map(b => b.date).join(',');
const Y = (start, extra) => Object.assign({ name: 'Yearly', amount: 120, frequency: 'yearly', startDate: start }, extra || {});
const Q = (start, extra) => Object.assign({ name: 'Quarterly', amount: 90, frequency: 'quarterly', startDate: start }, extra || {});
const one = (e, today, days) => dates(up([e], today, days));

const src = fs.readFileSync(path.join(__dirname, 'bills.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\s\/\/ .*$/gm, '');
check('L1 bills.js still never reads the clock or builds Dates', !/new Date|Date\.now|toISOString|getTimezoneOffset/.test(src));

// yearly
check('yearly: due in 14 days is listed', one(Y('2026-03-15'), '2026-03-01') === '2026-03-15');
check('yearly: due TODAY is listed', one(Y('2026-03-15'), '2026-03-15') === '2026-03-15');
check('yearly: yesterday is not listed, and next year is outside 30 days', one(Y('2026-03-15'), '2026-03-16') === '');
check('yearly: the next year repeats it', one(Y('2026-03-15'), '2027-03-01') === '2027-03-15' && one(Y('2026-03-15'), '2031-03-10') === '2031-03-15');
check('yearly: a start date in the future does not count before it', one(Y('2027-03-15'), '2026-10-01') === '' && one(Y('2027-03-15'), '2027-03-10') === '2027-03-15');
check('yearly: an old start date still repeats every year', one(Y('2019-07-04'), '2026-06-20') === '2026-07-04');
check('yearly: crossing New Year (start Jan 5, today Dec 20)', one(Y('2020-01-05'), '2026-12-20') === '2027-01-05');
check('yearly: only the month it belongs to', one(Y('2026-03-15'), '2026-06-01') === '' && one(Y('2026-03-15'), '2026-09-01') === '');
check('yearly: Feb 29 start falls on Feb 28 in a normal year and Feb 29 in a leap year', one(Y('2024-02-29'), '2026-02-10') === '2026-02-28' && one(Y('2024-02-29'), '2028-02-10') === '2028-02-29');
check('yearly: the end date stops it', one(Y('2026-03-15', { endDate: '2026-03-14' }), '2026-03-01') === '' && one(Y('2026-03-15', { endDate: '2026-03-15' }), '2026-03-01') === '2026-03-15' && one(Y('2026-03-15', { endDate: '2026-12-31' }), '2027-03-01') === '');
check('yearly: the entry carries name, amount and the word yearly', (() => { const b = up([Y('2026-03-15')], '2026-03-01')[0] || {}; return b.name === 'Yearly' && b.amount === 120 && b.freq === 'yearly'; })());

// quarterly
const qDates = (today, days) => one(Q('2026-03-15'), today, days);
check('quarterly: Mar 15, Jun 15, Sep 15, Dec 15 and the next Mar 15', qDates('2026-03-01') === '2026-03-15' && qDates('2026-06-01') === '2026-06-15' && qDates('2026-09-01') === '2026-09-15' && qDates('2026-12-01') === '2026-12-15' && qDates('2027-03-01') === '2027-03-15');
check('quarterly: months in between have nothing', qDates('2026-04-20') === '' && qDates('2026-07-20') === '' && qDates('2026-10-20') === '' && qDates('2027-01-20') === '');
check('quarterly: due today listed, yesterday not', qDates('2026-06-15') === '2026-06-15' && qDates('2026-06-16') === '');
check('quarterly: a start date in the future does not count before it', one(Q('2026-12-15'), '2026-06-01') === '' && one(Q('2026-12-15'), '2026-12-10') === '2026-12-15' && one(Q('2026-12-15'), '2027-03-10') === '2027-03-15');
check('quarterly: the last day clamps (start Jan 31: Apr 30, Jul 31, Oct 31, Jan 31)', one(Q('2026-01-31'), '2026-04-01') === '2026-04-30' && one(Q('2026-01-31'), '2026-07-01') === '2026-07-31' && one(Q('2026-01-31'), '2026-10-01') === '2026-10-31' && one(Q('2026-01-31'), '2027-01-02') === '2027-01-31');
check('quarterly: the end date stops it', one(Q('2026-03-15', { endDate: '2026-06-14' }), '2026-06-01') === '' && one(Q('2026-03-15', { endDate: '2026-06-15' }), '2026-06-01') === '2026-06-15');
check('quarterly: a longer window lists each one in it, in order', qDates('2026-03-01', 400) === '2026-03-15,2026-06-15,2026-09-15,2026-12-15,2027-03-15', qDates('2026-03-01', 400));
check('yearly: a 400-day window can hold two', one(Y('2026-03-15'), '2026-03-01', 400) === '2026-03-15,2027-03-15');
check('quarterly: window across the year end (Dec 20 + 120 days)', qDates('2026-12-20', 120) === '2027-03-15');

// no start date, junk, mixing
for (const f of ['yearly', 'quarterly']) {
  check(f + ': without a start date it is skipped', one({ name: 'x', amount: 5, frequency: f }, '2026-03-01') === '' && one({ name: 'x', amount: 5, frequency: f, startDate: null }, '2026-03-01') === '' && one({ name: 'x', amount: 5, frequency: f, startDate: 'junk' }, '2026-03-01') === '');
  check(f + ': the old due-day box does not move it (the start date decides)', one({ name: 'x', amount: 5, frequency: f, startDate: '2026-03-15', dueDay: 3 }, '2026-03-01') === '2026-03-15');
}
const mixed = up([{ name: 'Rent', amount: 1000, frequency: 'monthly', dueDay: 1 }, Y('2026-11-20', { name: 'Insurance' }), Q('2026-11-05', { name: 'Water' }), { name: 'Gym', amount: 9, frequency: 'weekly' }], '2026-11-01', 30);
check('mixed list is sorted by date and each kind appears', mixed.map(b => b.date + ' ' + b.name).join('|').indexOf('2026-11-01 Rent') === 0 && mixed.some(b => b.name === 'Water' && b.date === '2026-11-05') && mixed.some(b => b.name === 'Insurance' && b.date === '2026-11-20') && mixed.every((b, i) => i === 0 || b.date >= mixed[i - 1].date), JSON.stringify(mixed.map(b => b.date + b.name)));
check('other frequencies still behave (monthly, biweekly, weekly, unknown)', one({ name: 'a', amount: 1, frequency: 'monthly', dueDay: 5 }, '2026-11-01') === '2026-11-05' && one({ name: 'b', amount: 1, frequency: 'biweekly', startDate: '2026-11-02' }, '2026-11-01', 20) === '2026-11-02,2026-11-16' && one({ name: 'c', amount: 1, frequency: 'fortnightly' }, '2026-11-01') === '');

// L4/L5 stress
let threw = 0, outside = 0, seed = 987;
const rnd = (n) => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) % n;
const pad = (n) => String(n).padStart(2, '0');
for (let i = 0; i < 6000; i++) {
  const f = rnd(2) ? 'yearly' : 'quarterly';
  const start = [null, 'junk', '', 2000 + rnd(40) + '-' + pad(1 + rnd(12)) + '-' + pad(1 + rnd(31)), 2000 + rnd(40) + '-02-30'][rnd(5)];
  const today = 2020 + rnd(15) + '-' + pad(1 + rnd(12)) + '-' + pad(1 + rnd(28)), span = [0, 30, 100, 400][rnd(4)];
  try { for (const b of up([{ name: 'r', amount: 1, frequency: f, startDate: start, endDate: rnd(3) ? null : '2030-06-01' }], today, span)) { if (b.date < today || b.date > require('./dates.js').addDays(today, span) || (start && /^\d{4}-\d{2}-\d{2}$/.test(start) && b.date < start)) outside++; } } catch (e) { threw++; }
}
check('6,000 random yearly/quarterly entries: never throws, always inside the window and never before the start date', threw === 0 && outside === 0, 'threw=' + threw + ' outside=' + outside);
check('a very long expense list stays fast', (() => { const t = Date.now(); const list = []; for (let i = 0; i < 20000; i++) list.push(i % 2 ? Y('2020-0' + (1 + i % 9) + '-15') : Q('2021-0' + (1 + i % 9) + '-10')); up(list, '2026-10-01', 30); return Date.now() - t < 3000; })());

console.log(passed + '/' + (passed + failed) + ' passed');
process.exit(failed ? 1 : 0);