// Run:  node ledger-delete.test.js     (from apps/financial-tracker)
const L = require('./ledger.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
let n = 0; const mkid = () => 'id' + (++n);
const base = () => ({ schemaVersion: 2, accounts: [
  { id: 'vault', name: 'VAULT', kind: 'bank', role: 'vault', openingCents: 100000, openingDate: '2026-01-01', closed: false },
  { id: 'flex', name: 'FLEX', kind: 'bank', role: 'flex', openingCents: 0, openingDate: '2026-01-01', closed: false },
  { id: 'funds', name: 'FUNDS', kind: 'savings', role: 'funds', openingCents: 0, openingDate: '2026-01-01', closed: false },
  { id: 'cc', name: 'FREEDOM', kind: 'credit_card', role: 'none', openingCents: 30000, openingDate: '2026-01-01', closed: false }],
  transactions: [{ id: 'e1', accountId: 'vault', date: '2026-02-01', description: 'a', amountCents: -500, type: 'transaction' }, { id: 'e2', accountId: 'flex', date: '2026-02-02', description: 'b', amountCents: 700, type: 'transaction' }, { id: 'm1', accountId: 'vault', date: '2026-02-03', description: 'Migration adjustment', amountCents: 10, type: 'migration_adjustment' }] });
const ASOF = '2026-12-31';
const withT = L.addTransfer(base(), { fromId: 'vault', toId: 'cc', amountCents: 10000, date: '2026-03-01', description: 'pay card', makeId: mkid }).data;
const [h1, h2] = withT.transactions.slice(-2);
const snap = JSON.stringify(withT);

// L2 ordinary entries
const r1 = L.deleteTransactions(withT, ['e1'], false);
check('an ordinary entry is deleted, in a NEW data object, input untouched', r1.ok && r1.removed === 1 && r1.data !== withT && r1.data.transactions.length === withT.transactions.length - 1 && JSON.stringify(withT) === snap);
check('the balance moves back by exactly that entry (VAULT +5.00)', L.balanceCents(r1.data, 'vault', ASOF) === L.balanceCents(withT, 'vault', ASOF) + 500);
const r2 = L.deleteTransactions(withT, ['e1', 'e2', 'e1'], false);
check('several at once (a repeated id counts once)', r2.ok && r2.removed === 2 && !r2.data.transactions.some(t => t.id === 'e1' || t.id === 'e2'));

// L2 transfers
check('deleting an ordinary entry leaves other transfers fully linked', (() => { const k = r1.data.transactions.filter(t => t.id === h1.id || t.id === h2.id); return k.length === 2 && k[0].linkedId === k[1].id && k[1].linkedId === k[0].id && L.validate(r1.data).length === 0; })());
const b = L.deleteTransactions(withT, [h1.id], true);
check('both sides: deleting one half and asking for both removes the pair, balances return', b.ok && b.removed === 2 && !b.data.transactions.some(t => t.id === h1.id || t.id === h2.id) && L.balanceCents(b.data, 'vault', ASOF) === 100000 - 500 + 10 && L.balanceCents(b.data, 'cc', ASOF) === 30000 && L.validate(b.data).length === 0, JSON.stringify(L.validate(b.data)));
const o = L.deleteTransactions(withT, [h1.id], false);
const surv = o.data.transactions.find(t => t.id === h2.id);
check('one side only: the other half stays, its link is cleared, and the file stays VALID', o.ok && o.removed === 1 && !!surv && !('linkedId' in surv) && !('transferId' in surv) && L.validate(o.data).length === 0, JSON.stringify(L.validate(o.data)));
check('one side only: the survivor still counts in its account (card owes 200.00)', L.balanceCents(o.data, 'cc', ASOF) === 20000 && L.balanceCents(o.data, 'vault', ASOF) === 100000 - 500 + 10);
const both = L.deleteTransactions(withT, [h1.id, h2.id], false);
check('selecting both halves removes both even without "both sides"', both.ok && both.removed === 2 && L.validate(both.data).length === 0);
const both2 = L.deleteTransactions(withT, [h1.id, h2.id], true);
check('selecting both halves AND both sides removes both once', both2.ok && both2.removed === 2);

// L5 refusals change nothing
for (const [name, ids] of [['an unknown id', ['nope']], ['one good id and one unknown', ['e1', 'nope']], ['an empty list', []], ['not a list', 'e1'], ['null', null]]) {
  const x = L.deleteTransactions(withT, ids, false);
  check('refused: ' + name, x.ok === false && typeof x.error === 'string' && x.data === undefined);
}
check('a migration adjustment cannot be deleted (and nothing else in the same request is deleted)', (() => { const x = L.deleteTransactions(withT, ['e1', 'm1'], false); return x.ok === false && /migration/.test(x.error); })());
check('junk data never throws', (() => { try { return L.deleteTransactions(null, ['a']).ok === false && L.deleteTransactions({}, ['a']).ok === false && L.deleteTransactions({ transactions: [null, 5, { id: 'q' }] }, ['q']).ok === true; } catch (e) { return false; } })());
check('the input was never changed by any of the above', JSON.stringify(withT) === snap);

// L4 many transfers: delete half of them each way
let cur = base(); const pairs = [];
for (let i = 0; i < 400; i++) { const r = L.addTransfer(cur, { fromId: i % 2 ? 'vault' : 'flex', toId: i % 3 ? 'funds' : 'cc', amountCents: 100 + i, date: '2026-04-01', makeId: mkid }); cur = r.data; pairs.push(cur.transactions.slice(-2)); }
const ids1 = pairs.filter((_, i) => i % 2 === 0).map(p => p[0].id), ids2 = pairs.filter((_, i) => i % 2 === 1).map(p => p[1].id);
const d1 = L.deleteTransactions(cur, ids1, true), d2 = L.deleteTransactions(d1.data, ids2, false);
check('400 transfers: 200 pairs deleted together, 200 deleted one side only: counts right, file valid', d1.ok && d1.removed === 400 && d2.ok && d2.removed === 200 && d2.data.transactions.length === base().transactions.length + 200 && L.validate(d2.data).length === 0, JSON.stringify(L.validate(d2.data).slice(0, 2)));
check('the existing single delete is unchanged', L.deleteTransaction(withT, h1.id, true).removed === 2);
console.log(passed + '/' + (passed + failed) + ' passed');
process.exit(failed ? 1 : 0);