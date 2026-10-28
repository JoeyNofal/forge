// Run:  node dates.test.js     (from apps/financial-tracker)
// Runs every check once per time zone (a child process per zone), including zones behind and
// ahead of UTC, 30-minute and 14-hour offsets, and daylight-saving days.
const fs = require('fs'), path = require('path');
const { spawnSync } = require('child_process');

// zone -> what new Date(2026, 6, 1).getTimezoneOffset() must be (proves the zone is really in effect)
const ZONES = {
  'America/Indiana/Indianapolis': 240, 'UTC': 0, 'America/Los_Angeles': 420, 'Pacific/Auckland': -720,
  'Asia/Kolkata': -330, 'Pacific/Kiritimati': -840, 'Pacific/Pago_Pago': 660, 'Australia/Lord_Howe': -630, 'America/Sao_Paulo': 180
};

function core(zone) {
  const D = require('./dates.js');
  let passed = 0, failed = 0; const fails = [];
  const check = (name, cond, extra) => { if (cond) passed++; else { failed++; fails.push(name + (extra ? ' -> ' + extra : '')); } };
  const src = fs.readFileSync(path.join(__dirname, 'dates.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\s\/\/ .*$/gm, '');  // code only, no comments

  check('zone really in effect', new Date(2026, 6, 1).getTimezoneOffset() === ZONES[zone], zone + ' offset ' + new Date(2026, 6, 1).getTimezoneOffset());
  // L1 static
  check('L1 no toISOString / toLocale / Date.parse / getTimezoneOffset in dates.js', !/toISOString|toLocale|Date\.parse|getTimezoneOffset/.test(src));
  check('L1 never builds a Date from a bare string', !/new Date\(\s*['"`]/.test(src) && !/new Date\(\s*v\s*\)/.test(src));

  // L2 the two real bugs
  check('evening is still today (11:30pm)', D.todayStr(new Date(2026, 9, 26, 23, 30)) === '2026-10-26');
  check('evening is still today (23:59:59.999)', D.todayStr(new Date(2026, 9, 26, 23, 59, 59, 999)) === '2026-10-26');
  check('just after midnight is the new day', D.todayStr(new Date(2026, 9, 27, 0, 0, 1)) === '2026-10-27');
  check('fmtDateInput(now) in the evening is today', D.fmtDateInput(new Date(2026, 0, 31, 22, 0)) === '2026-01-31');
  check('a stored date shows the SAME day (not the day before)', D.fmtDate('2026-03-13') === 'Mar 13, 2026' && D.fmtDate('2026-01-01') === 'Jan 1, 2026' && D.fmtDate('2026-12-31') === 'Dec 31, 2026');
  let same = true, rt = true, n = 0;
  for (let dt = new Date(2020, 0, 1); dt.getFullYear() < 2041; dt = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate() + 1)) {
    n++;
    if (D.fmtDate(dt) !== dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })) same = false;
    const s = D.toDateStr(dt); if (D.toDateStr(D.parseDate(s)) !== s || D.fmtDate(s) !== D.fmtDate(dt)) rt = false;
  }
  check('fmtDate matches the old display format for every day 2020-2040 (' + n + ' days)', same);
  check('string -> Date -> string round trip for every day 2020-2040', rt);

  // L2 parsing
  check('valid dates parse', ['2026-03-13', '2028-02-29', '2000-02-29', '1900-01-01', '2200-12-31'].every(s => D.toDateStr(s) === s));
  check('trailing time part is ignored', D.toDateStr('2026-03-13T23:59:59') === '2026-03-13' && D.toDateStr(' 2026-03-13 ') === '2026-03-13' && D.toDateStr('2026-03-13 10:00') === '2026-03-13');
  for (const bad of ['2026-02-30', '2026-02-29', '1900-02-29', '2100-02-29', '2026-13-01', '2026-00-10', '2026-03-00', '2026-03-32', '2026-3-13', '2026/03/13', '13-03-2026', 'abc', '', ' ', null, undefined, 5, {}, [], true, '1899-12-31', '2201-01-01', '0000-01-01', '9999-99-99', '２０２６-０３-１３', new Date(NaN), '2026-03-13'.repeat(10)])
    check('rejects ' + JSON.stringify(bad), D.toDateStr(bad) === null && D.fmtDate(bad) === '—' && D.fmtDateInput(bad) === '' && D.parseDate(bad) === null);
  check('leap years', D.toDateStr('2000-02-29') && !D.toDateStr('2100-02-29') && D.toDateStr('2024-02-29') && !D.toDateStr('2025-02-29'));
  check('Date objects are read in local time', D.toDateStr(new Date(2026, 2, 13, 0, 0, 0)) === '2026-03-13' && D.toDateStr(new Date(2026, 2, 13, 23, 59, 59)) === '2026-03-13');

  // L2 arithmetic
  check('addDays across month, year and leap day', D.addDays('2026-01-31', 1) === '2026-02-01' && D.addDays('2026-12-31', 1) === '2027-01-01' && D.addDays('2028-02-28', 1) === '2028-02-29' && D.addDays('2026-02-28', 1) === '2026-03-01' && D.addDays('2026-03-01', -1) === '2026-02-28');
  check('addDays over daylight-saving days', D.addDays('2026-03-07', 1) === '2026-03-08' && D.addDays('2026-03-08', 1) === '2026-03-09' && D.addDays('2026-10-31', 1) === '2026-11-01' && D.addDays('2026-11-01', 1) === '2026-11-02' && D.addDays('2026-03-28', 1) === '2026-03-29' && D.addDays('2026-10-24', 1) === '2026-10-25');
  check('addDays zero, big, and bad input', D.addDays('2026-03-13', 0) === '2026-03-13' && D.addDays('2026-03-13', 365) === '2027-03-13' && D.addDays('2026-03-13', 1.5) === null && D.addDays('2026-03-13', NaN) === null && D.addDays('2026-03-13', '5') === null && D.addDays('bad', 1) === null && D.addDays('2026-03-13', 1e9) === null && D.addDays('2200-12-31', 1) === null && D.addDays('1900-01-01', -1) === null);
  check('daysBetween across daylight saving is whole days', D.daysBetween('2026-03-01', '2026-04-01') === 31 && D.daysBetween('2026-11-01', '2026-11-02') === 1 && D.daysBetween('2026-03-08', '2026-03-09') === 1 && D.daysBetween('2026-10-25', '2026-10-26') === 1 && D.daysBetween('2026-01-01', '2027-01-01') === 365 && D.daysBetween('2028-01-01', '2029-01-01') === 366);
  check('daysBetween same day is 0, reversed is negative, bad is null', D.daysBetween('2026-03-13', '2026-03-13') === 0 && D.daysBetween('2026-03-13', '2026-03-10') === -3 && D.daysBetween('x', '2026-03-10') === null && D.daysBetween('2026-03-10', undefined) === null);
  check('dayOfWeek is right (0 = Sunday)', D.dayOfWeek('2000-01-01') === 6 && D.dayOfWeek('2026-03-13') === 5 && D.dayOfWeek('2028-02-29') === 2 && D.dayOfWeek('2026-10-26') === 1 && D.dayOfWeek('2026-11-01') === 0 && D.dayOfWeek('2026-03-08') === 0 && D.dayOfWeek('nope') === null);
  check('dueDateInMonth clamps to the last day of the month', D.dueDateInMonth(2026, 2, 31) === '2026-02-28' && D.dueDateInMonth(2028, 2, 31) === '2028-02-29' && D.dueDateInMonth(2026, 4, 31) === '2026-04-30' && D.dueDateInMonth(2026, 1, 31) === '2026-01-31' && D.dueDateInMonth(2026, 12, 15) === '2026-12-15' && D.dueDateInMonth(2026, 2, 28) === '2026-02-28' && D.dueDateInMonth(2026, 2, 29) === '2026-02-28');
  for (const [y, m, d] of [[2026, 13, 1], [2026, 0, 1], [2026, 5, 0], [2026, 5, -1], [2026, 5, 1.5], [NaN, 5, 1], [2026, NaN, 1], ['2026', 5, 1], [2026, 5, undefined], [1800, 5, 1], [2300, 5, 1]])
    check('dueDateInMonth rejects ' + [y, m, d].join('/'), D.dueDateInMonth(y, m, d) === null);
  check('compare', D.compare('2026-03-13', '2026-03-14') === -1 && D.compare('2026-03-14', '2026-03-13') === 1 && D.compare('2026-03-13', '2026-03-13T10:00') === 0 && D.compare('x', '2026-03-13') === null);

  // L4 sustained: 200,000 random dates
  let seed = 12345; const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  let allOk = true;
  for (let i = 0; i < 200000; i++) {
    const s = D.addDays('2000-01-01', Math.floor(rnd() * 65000));
    const k = Math.floor(rnd() * 8001) - 4000;
    const t = D.addDays(s, k);
    if (!s || !t || D.daysBetween(s, t) !== k || D.addDays(t, -k) !== s || D.toDateStr(D.parseDate(s)) !== s) { allOk = false; break; }
  }
  check('L4 200,000 random add/subtract/round-trip checks all consistent', allOk);
  let dow = true; for (let i = 0; i < 70; i++) { const w = D.dayOfWeek(D.addDays('2026-10-25', i)); if (w !== i % 7) dow = false; }
  check('L4 weekdays cycle correctly over 10 weeks', dow);

  // L5 extreme
  const t0 = Date.now();
  check('L5 a 1,000,000-character string is rejected fast', D.toDateStr('x'.repeat(1000000)) === null && Date.now() - t0 < 500);
  check('L5 control characters and unicode are rejected', D.toDateStr('2026-03-13\u0000junk') === '2026-03-13' || D.toDateStr('2026-03-13\u0000junk') === null);
  check('L5 absurd Date objects', D.toDateStr(new Date(8.64e15)) === null && D.toDateStr(new Date(-8.64e15)) === null);
  check('L5 functions never throw on odd input', (() => { try { for (const x of [null, undefined, {}, [], () => 1, Symbol('s'), 1n, Object.create(null)]) { D.toDateStr(x); D.fmtDate(x); D.addDays(x, 1); D.addDays('2026-01-01', x); D.daysBetween(x, x); D.dayOfWeek(x); D.compare(x, x); D.todayStr(x === undefined ? undefined : new Date(NaN)); } return true; } catch (e) { return false; } })());
  check('L5 todayStr() with no argument gives a valid date', /^\d{4}-\d{2}-\d{2}$/.test(D.todayStr()));
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
  console.log(bad === 0 ? total + '/' + total + ' passed (' + Object.keys(ZONES).length + ' time zones)' : (total) + ' passed, ' + bad + ' FAILED');
  process.exit(bad === 0 ? 0 : 1);
}