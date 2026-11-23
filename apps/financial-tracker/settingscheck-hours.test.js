// Run:  node settingscheck-hours.test.js     (from apps/financial-tracker)
// Tests the forecast-hours boxes and the alternating switch in settingscheck.js.
const S = require('./settingscheck.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }

const base = () => ({ rate: '35.21', ot: '150', ns: '110', benefits: '45.5', other: '0', ret: '5', flexfloor: '300', vaultmonths: '7',
  cclimit: '5000', ccdue: '15', ccstmt: '18', cc2limit: '7000', cc2due: '21', cc2stmt: '24', brexstart: '500', sundaystart: '2026-03-13' });
const withHours = (o) => Object.assign(base(), { fixedhours: '40', alternating: false, longhours: '48', shorthours: '36' }, o || {});
const cur = { alternatingSundayStart: '2026-03-13' };
const HOURS = [['fixedhours', 'Forecast Hours per Week', 'forecastFixedHours'], ['longhours', 'Long Week Hours', 'forecastLongWeekHours'], ['shorthours', 'Short Week Hours', 'forecastShortWeekHours']];

// L1 static: the boxes exist with the right names
const byKey = k => S.BOXES.find(b => b.key === k);
for (const [k, label, to] of HOURS) check('L1 box ' + k + ' is ' + label + ' -> ' + to, byKey(k) && byKey(k).label === label && byKey(k).to === to && byKey(k).required === true && byKey(k).optionalBox === true && byKey(k).min === 0 && byKey(k).max === 168);
check('L1 the switch box stores forecastHoursMode', byKey('alternating') && byKey('alternating').to === 'forecastHoursMode' && byKey('alternating').kind === 'mode');
check('L1 keys and settings names are still unique', new Set(S.BOXES.map(b => b.to)).size === S.BOXES.length && new Set(S.BOXES.map(b => b.key)).size === S.BOXES.length);

// L2 good input
let r = S.validate(withHours(), cur);
check('good input is ok', r.ok === true, JSON.stringify(r));
check('40 / 48 / 36 carried as numbers, switch off = fixed', r.values.forecastFixedHours === 40 && r.values.forecastLongWeekHours === 48 && r.values.forecastShortWeekHours === 36 && r.values.forecastHoursMode === 'fixed', JSON.stringify(r.values));
check('switch on = alternating', S.validate(withHours({ alternating: true }), cur).values.forecastHoursMode === 'alternating');
check('37.5 and 0.25 are fine (2 decimals)', S.validate(withHours({ fixedhours: '37.5', longhours: '0.25' }), cur).ok);
check('0 hours is allowed (it is not turned into 40)', S.validate(withHours({ fixedhours: '0', longhours: '0', shorthours: '0' }), cur).values.forecastFixedHours === 0);
check('168 hours (every hour of the week) is allowed', S.validate(withHours({ fixedhours: '168' }), cur).ok);
check('-0 becomes plain 0', Object.is(S.validate(withHours({ fixedhours: '-0' }), cur).values.forecastFixedHours, 0));
check('spaces around a number are ignored', S.validate(withHours({ fixedhours: '  40  ' }), cur).values.forecastFixedHours === 40);
check('the other settings are unchanged by the new boxes', r.values.regularRate === 35.21 && r.values.overtimeMultiplier === 1.5 && r.values.vaultBufferMonths === 7 && r.values.alternatingSundayStart === '2026-03-13');

// absent boxes (an older page) are skipped, nothing is invented
r = S.validate(base(), cur);
check('with none of the new boxes present the result is ok', r.ok === true);
check('and none of the new keys appear in the saved values', !('forecastFixedHours' in r.values) && !('forecastLongWeekHours' in r.values) && !('forecastShortWeekHours' in r.values) && !('forecastHoursMode' in r.values));
for (const [k] of HOURS) { const o = withHours(); delete o[k]; check('only ' + k + ' absent: skipped, the rest still checked', S.validate(o, cur).ok && !(byKey(k).to in S.validate(o, cur).values)); }
const noSwitch = withHours(); delete noSwitch.alternating;
check('switch absent: skipped (mode key not written)', S.validate(noSwitch, cur).ok && !('forecastHoursMode' in S.validate(noSwitch, cur).values));
check('null counts as absent for the switch and the hours', S.validate(withHours({ alternating: null, fixedhours: null }), cur).ok);

// refusals, each names its own box
for (const [k, label] of HOURS) {
  for (const bad of ['', '   ', 'abc', '-1', '168.01', '169', '1000', '40.555', '4e1', '40 hours', '1,5', '--5', '40.', 'Infinity', 'NaN']) {
    const res = S.validate(withHours({ [k]: bad }), cur);
    check(label + ' refuses "' + bad + '"', res.ok === false && res.box === label && !('values' in res), JSON.stringify(res));
  }
}
check('blank message says cannot be blank', /cannot be blank/.test(S.validate(withHours({ longhours: '' }), cur).message));
check('range message names the limits', /0 to 168/.test(S.validate(withHours({ shorthours: '200' }), cur).message), S.validate(withHours({ shorthours: '200' }), cur).message);
for (const bad of ['true', 'false', 1, 0, 'on', '', {}, [], [true], () => true]) {
  const res = S.validate(withHours({ alternating: bad }), cur);
  check('the switch refuses ' + (typeof bad) + ' ' + String(bad), res.ok === false && res.box === 'Use the alternating pattern', JSON.stringify(res));
}

// the alternating pattern needs a start date somewhere
check('alternating on, saved date exists, box blank: ok (keeps the old date)', S.validate(withHours({ alternating: true, sundaystart: '' }), cur).ok);
r = S.validate(withHours({ alternating: true, sundaystart: '' }), {});
check('alternating on, no date anywhere: refused, names the date box', r.ok === false && r.box === 'Alternating Sunday Start Date' && /needed when the alternating pattern is on/.test(r.message), JSON.stringify(r));
check('alternating on, no saved date, date typed: ok', S.validate(withHours({ alternating: true, sundaystart: '2026-03-13' }), {}).ok);
check('alternating off, no date anywhere: ok', S.validate(withHours({ alternating: false, sundaystart: '' }), {}).ok);
check('alternating on with a bad typed date names the bad date first', S.validate(withHours({ alternating: true, sundaystart: '2026-02-30' }), {}).message.indexOf('not a real date') > 0);

// all or nothing, first bad box wins, page order
r = S.validate(withHours({ fixedhours: 'x', longhours: 'y' }), cur);
check('two bad hours boxes: the first one on the page is named', r.ok === false && r.box === 'Forecast Hours per Week');
r = S.validate(withHours({ rate: '0', fixedhours: 'x' }), cur);
check('an earlier bad box (rate) is named before the hours', r.box === 'Hourly Rate');
check('a refusal never carries values', !('values' in S.validate(withHours({ shorthours: '-5' }), cur)));

// L4 sustained: 5,000 random inputs against an independent rule
let seed = 12345; const rnd = n => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed % n; };
const pool = ['0', '40', '36', '48', '168', '168.5', '37.5', '', ' ', 'x', '-1', '1e2', '12.345', '40.', '.5', '+8', '00040', '0x10', '1,0'];
const oracle = t => { t = t.trim(); if (t === '') return false; if (!/^[+-]?(\d+(\.\d{1,2})?|\.\d{1,2})$/.test(t)) return false; const n = Number(t); return n >= 0 && n <= 168; };
let agree = true, firstBad = '';
for (let i = 0; i < 5000 && agree; i++) {
  const t = pool[rnd(pool.length)], k = HOURS[rnd(3)][0];
  const res = S.validate(withHours({ [k]: t }), cur);
  if (res.ok !== oracle(t)) { agree = false; firstBad = k + '=' + JSON.stringify(t); }
}
check('L4 5,000 random hour entries agree with the independent rule', agree, firstBad);
check('L4 the same input twice gives the same answer', JSON.stringify(S.validate(withHours({ fixedhours: '37.5' }), cur)) === JSON.stringify(S.validate(withHours({ fixedhours: '37.5' }), cur)));
const t0 = Date.now(); for (let i = 0; i < 20000; i++) S.validate(withHours(), cur);
check('L4 20,000 validations are fast', Date.now() - t0 < 3000);
const input = withHours({ alternating: true }); const copy = JSON.stringify(input); S.validate(input, cur);
check('L4 the input object is never changed', JSON.stringify(input) === copy);

// L5 extreme
const junk = [null, undefined, NaN, Infinity, {}, [], [1], 'x'.repeat(1000000), '9'.repeat(100000), '\u0000', '4\u00000', '４０', '٤٠', '😀', '40\n', '\t40', Symbol('s').toString(), 1e308, -1e308, 40, true];
let noThrow = true, junkOk = true;
try {
  for (const j of junk) for (const [k] of HOURS) {
    const res = S.validate(withHours({ [k]: j }), cur);
    if (res.ok && !(typeof j === 'number' && j === 40) && !(j === '40\n') && !(j === '\t40') && !(j === null || j === undefined)) junkOk = false;
  }
} catch (e) { noThrow = false; }
check('L5 junk in the hours boxes never throws', noThrow);
check('L5 junk is refused (only a plain 40, trimmed 40, or an absent box passes)', junkOk);
let throwsOn = false; try { S.validate(null, null); S.validate(undefined, undefined); S.validate('x', 5); S.validate([], []); } catch (e) { throwsOn = true; }
check('L5 validate on a missing or odd input object never throws', !throwsOn);
check('L5 validate(null) still refuses (rate is required)', S.validate(null, null).ok === false);
console.log(failed === 0 ? passed + '/' + passed + ' passed' : passed + ' passed, ' + failed + ' FAILED');
process.exit(failed === 0 ? 0 : 1);