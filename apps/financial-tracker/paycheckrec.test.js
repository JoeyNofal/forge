// Run:  node paycheckrec.test.js     (from apps/financial-tracker)
const fs = require('fs'), path = require('path');
const R = require('./paycheckrec.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const base = { netPay: 1000, flex: 400, currentFunds: 2000, currentVault: 5000, vaultTarget: 10000, baselineFunds: 2000 };
const rec = (o) => R.recommend(Object.assign({}, base, o));
const C = (x) => Math.round(x * 100);

const src = fs.readFileSync(path.join(__dirname, 'paycheckrec.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
check('L1 pure: no files, clock, page or randomness', !/require\('fs'\)|new Date|Date\.now|document\.|window\.|Math\.random/.test(src));

// L2 the order: FLEX, then savings, then VAULT
let r = rec({});
check('normal case: pay 1000, FLEX 400, FUNDS must rise 100 (to 2100), the other 500 goes to VAULT (it is 5000 short)', r.flex === 400 && r.toSavings === 100 && r.toFunds === 100 && r.toVault === 500 && r.extra === 0 && r.savingsTarget === 2100 && r.baselineFunds === 2000, JSON.stringify(r));
check('the three transfers add up to the pay exactly', C(r.flex) + C(r.toFunds) + C(r.toVault) === 100000);
r = rec({ currentFunds: 2060 });
check('FUNDS is already 60 above last time: only 40 more is needed', r.toSavings === 40 && r.toVault === 560 && r.toFunds === 40, JSON.stringify(r));
r = rec({ currentFunds: 2100 });
check('FUNDS exactly at last time + 100: on track, nothing for savings', r.toSavings === 0 && /on track/.test(r.savingsNote) && r.toVault === 600);
r = rec({ currentFunds: 5000 });
check('FUNDS far above last time: on track, no negative amounts', r.toSavings === 0 && r.toVault === 600 && r.toFunds === 0 && /on track/.test(r.savingsNote));
r = rec({ currentFunds: 1000 });
check('FUNDS well below last time (needs 1100): takes all the money left after FLEX, none for VAULT', r.toSavings === 600 && r.toFunds === 600 && r.toVault === 0 && /\+\$600\.00/.test(r.savingsNote) && /no money left/.test(r.vaultNote), JSON.stringify(r));
r = rec({ currentVault: 9900 });
check('VAULT only 100 short: VAULT gets 100, the other 400 goes to FUNDS (answer: extra to FUNDS)', r.toSavings === 100 && r.toVault === 100 && r.extra === 400 && r.toFunds === 500 && /extra \$400\.00/.test(r.extraNote), JSON.stringify(r));
r = rec({ currentVault: 10000 });
check('VAULT exactly at target: nothing to VAULT, all the rest to FUNDS', r.toVault === 0 && r.toFunds === 600 && /at target/.test(r.vaultNote) && r.extra === 500);
r = rec({ currentVault: 20000 });
check('VAULT over target: same', r.toVault === 0 && r.toFunds === 600);
r = rec({ vaultTarget: 0 });
check('VAULT target 0: everything left goes to FUNDS', r.toVault === 0 && r.toFunds === 600);
r = rec({ vaultTarget: -50 });
check('a negative VAULT target is treated as 0', r.toVault === 0 && r.toFunds === 600);

// L2 pay smaller than the FLEX allowance
r = rec({ netPay: 300 });
check('pay below the FLEX allowance: all of it goes to FLEX, nothing else', r.flex === 300 && r.toFunds === 0 && r.toVault === 0);
r = rec({ netPay: 0 });
check('zero pay: all zeros, no crash', r.flex === 0 && r.toFunds === 0 && r.toVault === 0);
r = rec({ netPay: -100 });
check('negative pay is treated as 0', r.flex === 0 && r.toFunds === 0 && r.toVault === 0);
r = rec({ netPay: 450 });
check('pay barely above FLEX: the 50 left goes to savings first', r.flex === 400 && r.toSavings === 50 && r.toVault === 0 && r.toFunds === 50);

// L2 no earlier approved paycheck
r = rec({ baselineFunds: null });
check('no earlier approved paycheck: compared with FUNDS now, so 100 goes to FUNDS, and the note says why', r.toSavings === 100 && r.baselineFunds === null && /no earlier approved paycheck/.test(r.savingsNote) && r.savingsTarget === 2100);
check('undefined baseline works the same', rec({ baselineFunds: undefined }).toSavings === 100);
r = rec({ baselineFunds: 0 });
check('a baseline of 0 is a real baseline (not "missing"): FUNDS 2000 is far above 100', r.toSavings === 0 && r.baselineFunds === 0);
r = rec({ currentFunds: -50, baselineFunds: 200 });
check('a negative FUNDS balance (overdrawn) still gets a sensible plan: needs 350', r.toSavings === 350 && r.toFunds === 350 && r.toVault === 250, JSON.stringify(r));

// L2 cents are exact
r = R.recommend({ netPay: 0.3, flex: 0.1, currentFunds: 0, currentVault: 0, vaultTarget: 1, baselineFunds: 0 });
check('0.1 + 0.2 style amounts stay exact: FLEX 0.10, savings 0.20', r.flex === 0.1 && r.toSavings === 0.2 && r.toVault === 0, JSON.stringify(r));
r = R.recommend({ netPay: 1234.56, flex: 400.07, currentFunds: 99.99, currentVault: 0.01, vaultTarget: 5000, baselineFunds: 50.5 });
check('odd cents add up exactly', C(r.flex) + C(r.toFunds) + C(r.toVault) === 123456, JSON.stringify(r));

// L5 junk
for (const [name, o] of [['nothing at all', undefined], ['empty object', {}], ['null', null], ['strings and NaN', { netPay: 'abc', flex: NaN, currentFunds: undefined, currentVault: null, vaultTarget: {}, baselineFunds: 'x' }], ['infinity', { netPay: Infinity, flex: -Infinity, currentFunds: Infinity, currentVault: 1e999, vaultTarget: Infinity }], ['huge numbers', { netPay: 1e300, flex: 1e300, currentFunds: 1e300, currentVault: 1e300, vaultTarget: 1e300, baselineFunds: 1e300 }], ['numeric strings', { netPay: '1000', flex: '400', currentFunds: '2000', currentVault: '5000', vaultTarget: '10000', baselineFunds: '2000' }]]) {
  let out, threw = false; try { out = R.recommend(o); } catch (e) { threw = true; }
  const nums = out ? [out.flex, out.toFunds, out.toVault, out.toSavings, out.extra, out.savingsTarget] : [];
  check('junk input never throws and never gives NaN/Infinity: ' + name, !threw && nums.every(Number.isFinite) && out.flex >= 0 && out.toFunds >= 0 && out.toVault >= 0, JSON.stringify(out));
}
check('numeric strings work like numbers', JSON.stringify(R.recommend({ netPay: '1000', flex: '400', currentFunds: '2000', currentVault: '5000', vaultTarget: '10000', baselineFunds: '2000' })) === JSON.stringify(rec({})));
check('an empty-string baseline counts as missing, not as 0', R.recommend(Object.assign({}, base, { baselineFunds: '' })).baselineFunds === null);
check('the caller can supply its own money formatter', /USD 100\.00/.test(R.recommend(Object.assign({}, base, { fmt: (n) => 'USD ' + n.toFixed(2) })).savingsNote));

// L4 20,000 random cases: the rules always hold
let seed = 12345; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
let bad = 0, detail = '';
for (let i = 0; i < 20000; i++) {
  const o = { netPay: Math.round(rnd() * 400000) / 100, flex: Math.round(rnd() * 120000) / 100, currentFunds: Math.round((rnd() - 0.2) * 600000) / 100, currentVault: Math.round((rnd() - 0.1) * 2000000) / 100, vaultTarget: Math.round(rnd() * 2500000) / 100, baselineFunds: rnd() < 0.2 ? null : Math.round((rnd() - 0.1) * 600000) / 100 };
  const r = R.recommend(o);
  const total = C(r.flex) + C(r.toFunds) + C(r.toVault);
  const net = Math.max(0, C(o.netPay));
  const vShort = Math.max(0, C(o.vaultTarget) - C(o.currentVault));
  const okAll = total === net && r.flex >= 0 && r.toFunds >= 0 && r.toVault >= 0 && C(r.toVault) <= vShort && C(r.flex) <= Math.max(0, C(o.flex)) && C(r.toSavings) + C(r.extra) === C(r.toFunds) && (C(r.extra) === 0 || C(r.toVault) === vShort) && JSON.stringify(R.recommend(o)) === JSON.stringify(r);
  if (!okAll) { bad++; if (!detail) detail = JSON.stringify(o) + ' -> ' + JSON.stringify(r); }
}
check('20,000 random cases: transfers add up to the pay, nothing negative, VAULT never above its shortfall, extra only when VAULT is full, same answer every time', bad === 0, detail);
console.log(passed + '/' + (passed + failed) + ' passed');
process.exit(failed ? 1 : 0);