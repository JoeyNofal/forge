// Run:  node ledger-correct.test.js     (from apps/financial-tracker)
const fs = require('fs'), path = require('path');
const L = require('./ledger.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const mk = () => ({ schemaVersion: 2, settings: { a: 1 }, accounts: [
  { id: 'vault', name: 'VAULT', kind: 'bank', role: 'vault', openingCents: 10000, openingDate: '2026-01-01', closed: false },
  { id: 'flex', name: 'FLEX', kind: 'bank', role: 'flex', openingCents: 0, openingDate: '2026-01-01', closed: false },
  { id: 'funds', name: 'FUNDS', kind: 'savings', role: 'funds', openingCents: 0, openingDate: '2026-01-01', closed: false },
  { id: 'cc', name: 'FREEDOM', kind: 'credit_card', role: 'none', openingCents: 5000, openingDate: '2026-01-01', closed: false },
  { id: 'loan', name: 'LOAN', kind: 'loan', role: 'none', openingCents: 250000, openingDate: '2026-01-01', closed: false },
  { id: 'brex', name: 'BREX', kind: 'receivable', role: 'none', openingCents: 164000, openingDate: '2026-01-01', closed: false },
  { id: 'late', name: 'LATE', kind: 'bank', role: 'none', openingCents: 0, openingDate: '2026-12-01', closed: false },
  { id: 'old', name: 'OLD', kind: 'bank', role: 'none', openingCents: 700, openingDate: '2026-01-01', closed: true }],
  transactions: [{ id: 'x1', accountId: 'vault', date: '2026-02-01', description: 'a', amountCents: 500, type: 'transaction' }] });
const D = '2026-10-29';
let n = 0; const ids = () => 'id' + (++n);
const run = (data, targets, o) => L.correctBalances(data, targets, D, Object.assign({ makeId: ids }, o));

// L1 static
const src = fs.readFileSync(path.join(__dirname, 'ledger.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
check('L1 ledger.js still touches no files and no page', !/require\('fs'\)|document\.|window\./.test(src));

// L2 each account kind lands on the typed number
const d = mk(), snap = JSON.stringify(d);
const r = run(d, [{ accountId: 'vault', balanceCents: 12345 }, { accountId: 'cc', balanceCents: 0 }, { accountId: 'loan', balanceCents: 200000 }, { accountId: 'brex', balanceCents: 150000 }, { accountId: 'funds', balanceCents: -250 }]);
check('ok, a NEW object, 5 entries added, original untouched', r.ok && r.data !== d && r.changed === 5 && r.data.transactions.length === 6 && JSON.stringify(d) === snap);
const b = (id) => L.balanceCents(r.data, id, D);
check('bank 105.00 -> 123.45', b('vault') === 12345);
check('card owed 50.00 -> 0.00', b('cc') === 0);
check('loan owed 2500.00 -> 2000.00', b('loan') === 200000);
check('receivable 1640.00 -> 1500.00', b('brex') === 150000);
check('a negative number is allowed (overdrawn FUNDS)', b('funds') === -250);
const e = r.data.transactions.filter(t => t.type === 'correction');
check('exact entry shape: id, account, today, the fixed name, cents, type correction; no typed balance', e.length === 5 && e.every(t => JSON.stringify(Object.keys(t).sort()) === JSON.stringify(['accountId', 'amountCents', 'date', 'description', 'id', 'type']) && t.description === 'Manual Balance Correction' && t.date === D));
const cc = e.find(t => t.accountId === 'cc'), vt = e.find(t => t.accountId === 'vault');
check('signs: card paid down by 50.00 is +5000 cash flow; vault up by 18.45 is +1845', cc.amountCents === 5000 && vt.amountCents === 12345 - 10500, JSON.stringify([cc, vt]));
const lo = e.find(t => t.accountId === 'loan');
check('loan owed 100.00 less = +10000 cash flow', lo.amountCents === 50000, String(lo.amountCents));
check('result is a valid file and keeps other keys', L.validate(r.data).length === 0 && r.data.settings.a === 1 && r.data.schemaVersion === 2);

// L2 unchanged accounts get nothing
const same = run(d, [{ accountId: 'vault', balanceCents: 10500 }, { accountId: 'cc', balanceCents: 5000 }]);
check('already on its number: ok, changed 0, same data, no entry', same.ok && same.changed === 0 && same.data === d);
const mix = run(d, [{ accountId: 'vault', balanceCents: 10500 }, { accountId: 'flex', balanceCents: 100 }]);
check('only the changed account gets an entry', mix.ok && mix.changed === 1 && mix.data.transactions.length === 2 && mix.data.transactions[1].accountId === 'flex');

// L2 dates and future entries
const f = mk(); f.transactions.push({ id: 'fut', accountId: 'vault', date: '2027-01-01', description: 'later', amountCents: 1000, type: 'transaction' });
const rf = run(f, [{ accountId: 'vault', balanceCents: 20000 }]);
check('a future-dated entry does not count today, so today lands on the typed number', rf.ok && L.balanceCents(rf.data, 'vault', D) === 20000 && L.balanceCents(rf.data, 'vault', '2027-01-01') === 21000);
const bd = L.correctBalances(d, [{ accountId: 'vault', balanceCents: 1 }], '2026-02-30', { makeId: ids });
check('an impossible date is refused', !bd.ok && /date/.test(bd.error));

// L5 refusals: all or nothing, nothing changes
const bad = [
  ['unknown account', [{ accountId: 'nope', balanceCents: 1 }]],
  ['closed account that would change', [{ accountId: 'old', balanceCents: 1 }]],
  ['listed twice', [{ accountId: 'vault', balanceCents: 1 }, { accountId: 'vault', balanceCents: 2 }]],
  ['fractional cents', [{ accountId: 'vault', balanceCents: 1.5 }]],
  ['NaN', [{ accountId: 'vault', balanceCents: NaN }]],
  ['string', [{ accountId: 'vault', balanceCents: '100' }]],
  ['absurd size', [{ accountId: 'vault', balanceCents: 9e13 + 1 }]],
  ['null target', [null]],
  ['empty list', []],
  ['not a list', 'vault'],
  ['dated before the account opened (entry would not count)', [{ accountId: 'late', balanceCents: 500 }]],
  ['one good + one bad = nothing at all', [{ accountId: 'vault', balanceCents: 1 }, { accountId: 'nope', balanceCents: 1 }]]
];
for (const [name, t] of bad) { const x = run(d, t); check('refused: ' + name, !x.ok && typeof x.error === 'string' && JSON.stringify(d) === snap, JSON.stringify(x).slice(0, 120)); }
const closedSame = run(d, [{ accountId: 'old', balanceCents: 700 }]);
check('a closed account already on that number is not an error (no entry)', closedSame.ok && closedSame.changed === 0);
check('ids that collide with existing ones are refused for that reason', (() => { const x = L.correctBalances(d, [{ accountId: 'vault', balanceCents: 1 }], D, { makeId: () => 'x1' }); return !x.ok && /unique id/.test(x.error); })());
check('two entries given the same id are refused for that reason', (() => { const x = L.correctBalances(d, [{ accountId: 'vault', balanceCents: 1 }, { accountId: 'flex', balanceCents: 1 }], D, { makeId: () => 'same' }); return !x.ok && /unique id/.test(x.error); })());
check('an account listed twice is refused for that reason', (() => { const x = run(d, [{ accountId: 'vault', balanceCents: 1 }, { accountId: 'vault', balanceCents: 1 }]); return !x.ok && /twice/.test(x.error); })());
const broken = mk(); broken.transactions.push({ id: 'ghost', accountId: 'nowhere', date: '2026-03-01', description: 'x', amountCents: 5, type: 'transaction' });
check('a file that is already invalid is refused, not made worse', (() => { const x = run(broken, [{ accountId: 'vault', balanceCents: 1 }]); return !x.ok && /valid file/.test(x.error); })());
check('a file with no transactions list still works', L.correctBalances({ accounts: mk().accounts }, [{ accountId: 'vault', balanceCents: 1 }], D, { makeId: ids }).ok);
check('data null does not throw', (() => { try { return L.correctBalances(null, [{ accountId: 'vault', balanceCents: 1 }], D).ok === false; } catch (x) { return false; } })());

// L4 many corrections one after another keep landing exactly (cents, no float drift)
let cur = mk(), ok = true;
for (let i = 0; i < 300; i++) { const target = (i * 7919) % 100000 - 500; const x = run(cur, [{ accountId: 'cc', balanceCents: target }, { accountId: 'vault', balanceCents: target + 1 }]); if (!x.ok || L.balanceCents(x.data, 'cc', D) !== target || L.balanceCents(x.data, 'vault', D) !== target + 1) { ok = false; break; } cur = x.data; }
check('L4 300 rounds of corrections always land exactly and the file stays valid', ok && L.validate(cur).length === 0);
const defaultIds = L.correctBalances(mk(), [{ accountId: 'vault', balanceCents: 1 }, { accountId: 'flex', balanceCents: 1 }], D);
check('built-in ids are unique', defaultIds.ok && new Set(defaultIds.data.transactions.map(t => t.id)).size === 3);

console.log(passed + '/' + (passed + failed) + ' passed');
process.exit(failed ? 1 : 0);