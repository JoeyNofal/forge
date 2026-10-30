// Run:  node ledger-add.test.js     (from apps/financial-tracker)
const fs = require('fs'), path = require('path');
const L = require('./ledger.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const mk = () => ({ schemaVersion: 2, settings: { a: 1 }, accounts: [
  { id: 'vault', name: 'VAULT', kind: 'bank', role: 'vault', openingCents: 10000, openingDate: '2026-01-01', closed: false },
  { id: 'flex', name: 'FLEX', kind: 'bank', role: 'flex', openingCents: 0, openingDate: '2026-01-01', closed: false },
  { id: 'funds', name: 'FUNDS', kind: 'savings', role: 'funds', openingCents: 0, openingDate: '2026-01-01', closed: false },
  { id: 'cc', name: 'FREEDOM', kind: 'credit_card', role: 'none', openingCents: 5000, openingDate: '2026-01-01', closed: false },
  { id: 'old', name: 'OLD', kind: 'bank', role: 'none', openingCents: 0, openingDate: '2026-01-01', closed: true }],
  transactions: [{ id: 'x1', accountId: 'vault', date: '2026-02-01', description: 'a', amountCents: 500, type: 'transaction' }] });
const ASOF = '2026-12-31';
const ok = (data, o) => L.addTransaction(data, Object.assign({ accountId: 'vault', date: '2026-03-01', description: 'Groceries', amountCents: -4500 }, o));

// L1 static: pure
const src = fs.readFileSync(path.join(__dirname, 'ledger.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
check('L1 ledger.js still touches no files and no page', !/require\('fs'\)|document\.|window\./.test(src));

// L2 the normal case
const d = mk(), snap = JSON.stringify(d);
const r = ok(d);
check('an entry is added: ok, an id, type transaction, cents kept, in a NEW data object', r.ok && typeof r.id === 'string' && r.data !== d && r.data.transactions.length === 2 && JSON.stringify(d) === snap);
const t = r.data.transactions[1];
check('the new entry has exactly the expected fields (no typed balance, no dollar amount)', JSON.stringify(Object.keys(t).sort()) === JSON.stringify(['accountId', 'amountCents', 'date', 'description', 'id', 'type']) && t.amountCents === -4500 && t.type === 'transaction' && t.id === r.id);
check('bank balance: 100.00 + 5.00 - 45.00 = 60.00', L.balanceCents(r.data, 'vault', ASOF) === 6000);
const rc = ok(d, { accountId: 'cc', amountCents: -3000 });
check('card: spending 30.00 (negative) raises what is owed from 50.00 to 80.00', rc.ok && L.balanceCents(rc.data, 'cc', ASOF) === 8000);
const rp = ok(d, { accountId: 'cc', amountCents: 2000 });
check('card: a 20.00 payment (positive) lowers what is owed to 30.00', rp.ok && L.balanceCents(rp.data, 'cc', ASOF) === 3000);
check('the result passes the file shape check', L.validate(r.data).length === 0 && L.validate(rc.data).length === 0);
check('other file keys survive', r.data.settings.a === 1 && r.data.schemaVersion === 2);

// L2 dates
const fut = ok(d, { date: '2027-01-15' });
check('a future-dated entry counts only from its date', L.balanceCents(fut.data, 'vault', '2026-06-01') === 10500 && L.balanceCents(fut.data, 'vault', '2027-01-15') === 6000);

// L2/L5 refusals (each one returns an error and changes nothing)
const bad = [
  ['unknown account', { accountId: 'nope' }], ['closed account', { accountId: 'old' }], ['zero amount', { amountCents: 0 }],
  ['fractional cents', { amountCents: 1.5 }], ['NaN', { amountCents: NaN }], ['Infinity', { amountCents: Infinity }], ['a string amount', { amountCents: '100' }], ['null amount', { amountCents: null }],
  ['absurdly large', { amountCents: L.MAX_CENTS + 1 }], ['absurdly negative', { amountCents: -(L.MAX_CENTS + 1) }],
  ['impossible date', { date: '2026-02-30' }], ['wrong date format', { date: '03/01/2026' }], ['no date', { date: undefined }],
  ['empty description', { description: '' }], ['blank description', { description: '   ' }], ['non-string description', { description: 42 }], ['no description', { description: undefined }]];
for (const [name, o] of bad) { const x = ok(d, o); check('refused: ' + name, x.ok === false && typeof x.error === 'string' && x.data === undefined); }
check('refused: an id that already exists', ok(d, { makeId: () => 'x1' }).ok === false);
check('refused: an id that is not text', ok(d, { makeId: () => 7 }).ok === false && ok(d, { makeId: () => '' }).ok === false);
check('refused: no data / junk data does not crash', (() => { try { return L.addTransaction(null, {}).ok === false && L.addTransaction({}, {}).ok === false && L.addTransaction(mk(), undefined).ok === false; } catch (e) { return false; } })());

// L2 text handling
check('description is trimmed and capped at 200 characters', ok(d, { description: '  hi  ' }).data.transactions[1].description === 'hi' && ok(d, { description: 'x'.repeat(500) }).data.transactions[1].description.length === 200);
check('emoji / odd characters are kept as typed', ok(d, { description: 'Café ☕ "quotes" <b>' }).data.transactions[1].description === 'Café ☕ "quotes" <b>');
const empty = mk(); delete empty.transactions;
check('a file with no transactions list still works', ok(empty).ok && ok(empty).data.transactions.length === 1);
check('typing 0.1 + 0.2 style amounts stays exact in cents', ok(d, { amountCents: L.toCents('0.10') }).ok && L.balanceCents(ok(ok(d, { amountCents: L.toCents('0.10') }).data, { amountCents: L.toCents('0.20') }).data, 'vault', ASOF) === 10500 + 30);

// L4 many adds in a row
let cur = mk(), sum = 0, ids = new Set(), allOk = true;
for (let i = 0; i < 3000; i++) { const c = (i % 7) * 13 - 40 || 1; const x = ok(cur, { amountCents: c, date: '2026-0' + (1 + i % 9) + '-1' + (i % 9) }); if (!x.ok) { allOk = false; break; } cur = x.data; sum += c; ids.add(x.id); }
check('3000 entries in a row: all accepted, ids all different, balance equals the exact sum', allOk && ids.size === 3000 && L.balanceCents(cur, 'vault', ASOF) === 10000 + 500 + sum && L.validate(cur).length === 0);
console.log(passed + '/' + (passed + failed) + ' passed');
process.exit(failed ? 1 : 0);