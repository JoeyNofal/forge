// Run:  node dateweeks.test.js     (from apps/financial-tracker)
// Tests the Sunday-to-Saturday week helpers in dates.js (weekStart, weeksBetween, isLongWeek).
// Runs once per time zone (a child process per zone), because the math must never move with the clock.
const fs = require('fs'), path = require('path');
const { spawnSync } = require('child_process');

const ZONES = {
  'America/Indiana/Indianapolis': 240, 'UTC': 0, 'America/Los_Angeles': 420, 'Pacific/Auckland': -720,
  'Asia/Kolkata': -330, 'Pacific/Kiritimati': -840, 'Pacific/Pago_Pago': 660, 'Australia/Lord_Howe': -630, 'America/Sao_Paulo': 180
};

function core(zone) {
  const D = require('./dates.js');
  let passed = 0, failed = 0; const fails = [];
  const check = (name, cond, extra) => { if (cond) passed++; else { failed++; fails.push(name + (extra ? ' -> ' + extra : '')); } };
  const src = fs.readFileSync(path.join(__dirname, 'dates.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\s\/\/ .*$/gm, '');
  const DAY = 86400000;
  const utcDay = s => Math.round(Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / DAY);   // independent day count

  check('zone really in effect', new Date(2026, 6, 1).getTimezoneOffset() === ZONES[zone], zone);

  // L1 static
  check('L1 the three helpers are exported', typeof D.weekStart === 'function' && typeof D.weeksBetween === 'function' && typeof D.isLongWeek === 'function');
  const weekLines = src.split('\n').filter(l => /function (weekStart|weeksBetween|isLongWeek)/.test(l)).join('\n');
  check('L1 the three helpers were found in the code', (weekLines.match(/function /g) || []).length === 3);
  check('L1 the helpers use no clock time or Date objects', !/new Date|Date\.|getHours|getTime|setDate/.test(weekLines));

  // L2 weekStart
  check('Friday 2026-03-13 starts its week on Sunday 2026-03-08', D.weekStart('2026-03-13') === '2026-03-08');
  check('a Sunday is its own week start', D.weekStart('2026-03-08') === '2026-03-08');
  check('a Saturday belongs to the Sunday before', D.weekStart('2026-03-14') === '2026-03-08');
  check('the next Sunday starts a new week', D.weekStart('2026-03-15') === '2026-03-15');
  let allSeven = true;
  for (let i = 0; i < 7; i++) if (D.weekStart(D.addDays('2026-03-08', i)) !== '2026-03-08') allSeven = false;
  check('all seven days Sun..Sat give the same week start', allSeven);
  check('crosses a year boundary (2026-01-01 -> 2025-12-28)', D.weekStart('2026-01-01') === '2025-12-28');
  check('crosses a leap-day boundary (2024-03-01 -> 2024-02-25)', D.weekStart('2024-03-01') === '2024-02-25');
  check('US daylight-saving start Sunday 2026-03-08 is its own week start', D.weekStart('2026-03-08') === '2026-03-08' && D.weekStart('2026-03-11') === '2026-03-08');
  check('US daylight-saving end week (2026-11-07 -> 2026-11-01)', D.weekStart('2026-11-07') === '2026-11-01');
  check('accepts a Date object', D.weekStart(new Date(2026, 2, 13, 23, 30)) === '2026-03-08');

  // L2 weeksBetween
  check('same week = 0 (Sunday to Saturday)', D.weeksBetween('2026-03-08', '2026-03-14') === 0);
  check('Saturday to the next Sunday = 1', D.weeksBetween('2026-03-14', '2026-03-15') === 1);
  check('Friday to the Friday after = 1', D.weeksBetween('2026-03-13', '2026-03-20') === 1);
  check('Friday to the Friday before = -1', D.weeksBetween('2026-03-13', '2026-03-06') === -1);
  check('52 weeks across both daylight-saving changes = 52', D.weeksBetween('2026-03-13', D.addDays('2026-03-13', 364)) === 52);
  check('104 weeks = 104', D.weeksBetween('2026-01-04', D.addDays('2026-01-04', 728)) === 104);

  // L2 isLongWeek (start date is a Friday on purpose: the old setting was a Friday date)
  const start = '2026-03-13';
  check('the week containing the start date is LONG', D.isLongWeek(start, '2026-03-13') === true);
  check('the whole start week is long (Sunday)', D.isLongWeek(start, '2026-03-08') === true);
  check('the whole start week is long (Saturday)', D.isLongWeek(start, '2026-03-14') === true);
  check('the next week is SHORT', D.isLongWeek(start, '2026-03-15') === false && D.isLongWeek(start, '2026-03-21') === false);
  check('then long again', D.isLongWeek(start, '2026-03-22') === true && D.isLongWeek(start, '2026-03-28') === true);
  let alt = true;
  for (let w = 0; w < 60; w++) if (D.isLongWeek(start, D.addDays(start, 7 * w)) !== (w % 2 === 0)) alt = false;
  check('60 weeks in a row alternate long, short, long ...', alt);
  check('a Sunday start date works the same way', D.isLongWeek('2026-03-08', '2026-03-08') === true && D.isLongWeek('2026-03-08', '2026-03-15') === false);
  check('a Saturday start date: its own week is long', D.isLongWeek('2026-03-14', '2026-03-09') === true);
  check('before the start the pattern continues backwards', D.isLongWeek(start, '2026-03-04') === false && D.isLongWeek(start, '2026-02-25') === true);
  check('accepts Date objects', D.isLongWeek(new Date(2026, 2, 13), new Date(2026, 2, 22, 23, 59)) === true);
  // the pay-day rule: a Friday pays the week containing the Friday one week earlier
  check('pay Fri 2026-03-20 pays the week of 03-08 .. 03-14 (long)', D.isLongWeek(start, D.addDays('2026-03-20', -7)) === true);
  check('pay Fri 2026-03-27 pays the week of 03-15 .. 03-21 (short)', D.isLongWeek(start, D.addDays('2026-03-27', -7)) === false);
  check('pay Fri 2026-04-03 pays a long week', D.isLongWeek(start, D.addDays('2026-04-03', -7)) === true);

  // L4 sustained: compare with a separate day-count calculation over ~30 years of days
  let agree = true, firstBad = '';
  const base = utcDay('2026-03-08');
  for (let i = -3650; i <= 7300 && agree; i++) {
    const day = D.addDays('2026-03-13', i);
    const ws = D.weekStart(day);
    const wk = Math.floor((utcDay(day) - base) / 7);
    const expectLong = Math.abs(wk) % 2 === 0;
    if (D.dayOfWeek(ws) !== 0 || utcDay(day) - utcDay(ws) < 0 || utcDay(day) - utcDay(ws) > 6 || D.isLongWeek(start, day) !== expectLong || D.weeksBetween(start, day) !== wk) { agree = false; firstBad = day; }
  }
  check('L4 ~30 years of days agree with an independent day count', agree, firstBad);
  const t0 = Date.now();
  for (let i = 0; i < 20000; i++) D.isLongWeek(start, D.addDays(start, i % 5000));
  check('L4 20,000 calls are fast', Date.now() - t0 < 2000);

  // L5 extreme / junk: null, never a crash, never a guess
  const junk = [null, undefined, {}, [], 'x', '', '2026-02-30', '2026-13-01', new Date(NaN), () => 1, Symbol('s'), 1n, Object.create(null), '9'.repeat(100000), new Date(8.64e15)];
  let noThrow = true, allNull = true;
  try {
    for (const j of junk) {
      if (D.weekStart(j) !== null) allNull = false;
      if (D.weeksBetween(j, '2026-03-13') !== null || D.weeksBetween('2026-03-13', j) !== null) allNull = false;
      if (D.isLongWeek(j, '2026-03-13') !== null || D.isLongWeek('2026-03-13', j) !== null) allNull = false;
    }
  } catch (e) { noThrow = false; }
  check('L5 junk input never throws', noThrow);
  check('L5 junk input gives null (not true/false)', allNull);
  check('L5 the earliest and latest supported days do not crash or lie', (() => { try { const a = D.weekStart('0001-01-01'), b = D.weekStart('9999-12-31'); return (a === null || D.dayOfWeek(a) === 0) && (b === null || D.dayOfWeek(b) === 0); } catch (e) { return false; } })());
  check('L5 a result is a real boolean', typeof D.isLongWeek(start, start) === 'boolean');
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