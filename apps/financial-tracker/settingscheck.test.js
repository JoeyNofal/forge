// Run:  node settingscheck.test.js     (from apps/financial-tracker)
const fs = require('fs'), path = require('path');
const S = require('./settingscheck.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }

const src = fs.readFileSync(path.join(__dirname, 'settingscheck.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
check('L1 no file, clock or page access', !/require\('fs'\)|new Date|Date\.now|document\.|window\./.test(src));

const good = () => ({ rate: '35.21', ot: '150', ns: '110', benefits: '45.5', other: '0', ret: '5', flexfloor: '300', vaultmonths: '7',
  carloan: '1500', carmin: '1000', cartarget: '3000', carloaninitial: '5000', cclimit: '5000', ccdue: '15', ccstmt: '18',
  cc2limit: '7000', cc2due: '21', cc2stmt: '24', brexstart: '500', sundaystart: '2026-01-04' });
const cur = { alternatingSundayStart: '2025-12-28' };

// L2 good input
let r = S.validate(good(), cur);
check('good input is ok', r.ok === true);
check('percent to multiplier (150 -> 1.5, 110 -> 1.1)', r.values.overtimeMultiplier === 1.5 && r.values.nightshiftMultiplier === 1.1, JSON.stringify(r.values));
check('plain numbers carried', r.values.regularRate === 35.21 && r.values.vaultBufferMonths === 7 && r.values.ccPaymentDueDay === 15 && r.values.alternatingSundayStart === '2026-01-04');
check('175 -> 1.75 and 150.5 -> 1.505 exactly', S.validate({ ...good(), ot: '175' }, cur).values.overtimeMultiplier === 1.75 && S.validate({ ...good(), ot: '150.5' }, cur).values.overtimeMultiplier === 1.505);
check('10.1 -> exactly 0.101 (plain division gives 0.10099999999999999)', S.validate({ ...good(), ot: '10.1' }, cur).values.overtimeMultiplier === 0.101);
check('toPercentText: 1.5 -> 150, 1.505 -> 150.5, 1.1 -> 110, 1.15 -> 115', S.toPercentText(1.5) === '150' && S.toPercentText(1.505) === '150.5' && S.toPercentText(1.1) === '110' && S.toPercentText(1.15) === '115');
check('toPercentText junk -> empty', S.toPercentText(undefined) === '' && S.toPercentText('x') === '');

// zero and blank
r = S.validate({ ...good(), benefits: '', other: '0', ret: '0', flexfloor: '', vaultmonths: '0', carloan: '', ot: '' }, cur);
check('blank and 0 save as 0', r.ok && r.values.benefitsDeduction === 0 && r.values.otherDeductions === 0 && r.values.retirementPercent === 0 && r.values.flexFloor === 0 && r.values.vaultBufferMonths === 0 && r.values.carLoanMonthlyTarget === 0 && r.values.overtimeMultiplier === 0);
check('VAULT months has no upper limit', S.validate({ ...good(), vaultmonths: '5000' }, cur).ok && S.validate({ ...good(), vaultmonths: '5000' }, cur).values.vaultBufferMonths === 5000);
check('VAULT months absurdly large (not a safe integer) is refused', !S.validate({ ...good(), vaultmonths: '99999999999999999999' }, cur).ok);

// required boxes
for (const [k, label] of [['rate', 'Hourly Rate'], ['ccdue', 'FREEDOM Payment Due Day'], ['ccstmt', 'FREEDOM Statement Day'], ['cc2due', 'SAVOR Payment Due Day'], ['cc2stmt', 'SAVOR Statement Day']]) {
  r = S.validate({ ...good(), [k]: '  ' }, cur);
  check('blank ' + k + ' is refused and named', !r.ok && r.box === label && /blank/.test(r.message), JSON.stringify(r));
}
check('hourly rate 0 refused', !S.validate({ ...good(), rate: '0' }, cur).ok);
check('hourly rate 0.01 ok', S.validate({ ...good(), rate: '0.01' }, cur).ok);

// ranges
const bad = (k, v) => S.validate({ ...good(), [k]: v }, cur);
check('retirement 100 ok, 100.01 refused, -1 refused', bad('ret', '100').ok && !bad('ret', '100.01').ok && !bad('ret', '-1').ok);
check('retirement refusal names the box', bad('ret', '101').box === 'Retirement (%)' && /0 to 100/.test(bad('ret', '101').message));
check('days: 1 and 31 ok, 0 and 32 refused, 15.5 refused', bad('ccdue', '1').ok && bad('ccdue', '31').ok && !bad('ccdue', '0').ok && !bad('ccdue', '32').ok && !bad('ccdue', '15.5').ok);
check('VAULT months: 2.5 refused, -1 refused', !bad('vaultmonths', '2.5').ok && !bad('vaultmonths', '-1').ok);
check('money: 1,000,000 ok, 1,000,000.01 refused, negative refused', bad('flexfloor', '1000000').ok && !bad('flexfloor', '1000000.01').ok && !bad('flexfloor', '-0.01').ok);
check('percent: 0 ok, negative refused, 1,000,001 refused', bad('ns', '0').ok && !bad('ns', '-5').ok && !bad('ns', '1000001').ok);
check('more than 2 decimals refused for money', !bad('benefits', '10.123').ok);

// junk text
for (const v of ['abc', '1e9', '1e3', '0x10', 'Infinity', 'NaN', '--5', '1,000', '$30', '5 5', '.', '+', '']) {
  if (v === '') continue;
  check('junk "' + v + '" refused in money box', !bad('flexfloor', v).ok);
  check('junk "' + v + '" refused in whole box', !bad('vaultmonths', v).ok);
}
check('", 5" with spaces around is trimmed and ok', bad('flexfloor', '  250  ').ok && bad('flexfloor', '  250  ').values.flexFloor === 250);
check('".5" and "5." styles', bad('benefits', '.5').ok && bad('benefits', '.5').values.benefitsDeduction === 0.5 && !bad('benefits', '5.').ok);

// all or nothing, first bad box in page order
r = S.validate({ ...good(), ret: '500', benefits: 'zzz', ccdue: '40' }, cur);
check('two bad boxes: reports the first in page order, no values', !r.ok && r.box === 'Benefits Deduction' && r.values === undefined, JSON.stringify(r));
check('a bad result never carries partial values', !('values' in S.validate({ ...good(), cc2due: '0' }, cur)));

// optional boxes (car fund boxes missing on v2)
const v2 = good(); delete v2.carmin; delete v2.cartarget;
r = S.validate(v2, cur);
check('missing optional boxes are skipped, not set to 0', r.ok && !('carFundMinimum' in r.values) && !('carFundTarget' in r.values));
check('present optional boxes are checked', !S.validate({ ...good(), carmin: 'x' }, cur).ok);
check('a missing REQUIRED box (undefined) counts as blank and is refused', !S.validate({ ...good(), rate: undefined }, cur).ok);

// date box
check('blank date keeps the old date', S.validate({ ...good(), sundaystart: '' }, cur).values.alternatingSundayStart === '2025-12-28');
check('blank date and no old date: nothing set', !('alternatingSundayStart' in S.validate({ ...good(), sundaystart: '' }, {}).values));
for (const d of ['2026-02-30', '2026-13-01', '2026-00-10', '2026-1-4', 'tomorrow', '2026-04-31', '2026-01-00']) check('bad date ' + d + ' refused', !S.validate({ ...good(), sundaystart: d }, cur).ok);
check('leap day ok in 2028, refused in 2027', S.validate({ ...good(), sundaystart: '2028-02-29' }, cur).ok && !S.validate({ ...good(), sundaystart: '2027-02-29' }, cur).ok);

// input handling
check('no input at all: refuses (rate and days are required), never throws', (() => { try { return !S.validate().ok && !S.validate(null, null).ok; } catch (e) { return false; } })());
check('numbers (not text) are accepted as input', S.validate({ ...good(), flexfloor: 300, vaultmonths: 7 }, cur).ok);
check('input object is not changed', (() => { const g = good(); const copy = JSON.stringify(g); S.validate(g, cur); return JSON.stringify(g) === copy; })());
check('every settings key written is unique', new Set(S.BOXES.map(b => b.to)).size === S.BOXES.length && new Set(S.BOXES.map(b => b.key)).size === S.BOXES.length);

// L4/L5 stress: 20,000 random inputs never throw and ok results are always in range
let threw = 0, okc = 0;
const junkPool = ['', ' ', '0', '1', '-1', '5.5', 'abc', '1e5', '99999999999', '31', '32', '.1', '١٢٣', '\u0000', '5\n', 'NaN', '-0', '1000000', '100'];
let seed = 12345; const rnd = n => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) % n;
for (let i = 0; i < 20000; i++) {
  const g = good(); const k = Object.keys(g)[rnd(Object.keys(g).length)]; g[k] = junkPool[rnd(junkPool.length)];
  try { const x = S.validate(g, cur); if (x.ok) { okc++; for (const v of Object.values(x.values)) if (typeof v === 'number' && (!Number.isFinite(v) || v < 0)) threw++; } } catch (e) { threw++; }
}
check('20,000 random inputs: no throw, every accepted number finite and not negative', threw === 0, 'problems=' + threw + ' ok=' + okc);
check('"-0" never becomes -0', !Object.is(S.validate({ ...good(), benefits: '-0' }, cur).values.benefitsDeduction, -0));

console.log(passed + '/' + (passed + failed) + ' passed');
process.exit(failed ? 1 : 0);