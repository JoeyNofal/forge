// Run:  node ledger-accounts.test.js     (from apps/financial-tracker)
const fs = require('fs'), path = require('path');
const L = require('./ledger.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const mk = () => ({ schemaVersion: 2, settings: { a: 1 }, accounts: [
  { id: 'vault', name: 'VAULT', kind: 'bank', role: 'vault', openingCents: 10000, openingDate: '2026-01-01', closed: false },
  { id: 'flex', name: 'FLEX', kind: 'bank', role: 'flex', openingCents: 0, openingDate: '2026-01-01', closed: false },
  { id: 'funds', name: 'FUNDS', kind: 'savings', role: 'funds', openingCents: 0, openingDate: '2026-01-01', closed: false },
  { id: 'cc', name: 'FREEDOM', kind: 'credit_card', role: 'none', openingCents: 5000, openingDate: '2026-01-01', closed: false },
  { id: 'car', name: 'Car Loan', kind: 'loan', role: 'none', openingCents: 0, openingDate: '2026-01-01', closed: false },
  { id: 'old', name: 'Old Card', kind: 'credit_card', role: 'none', openingCents: 0, openingDate: '2026-01-01', closed: true }],
  transactions: [{ id: 'x1', accountId: 'vault', date: '2026-02-01', description: 'a', amountCents: 500, type: 'transaction' }] });
const D = '2026-11-07';
let n = 0; const mkId = () => 'new' + (++n);

// L1 static
const src = fs.readFileSync(path.join(__dirname, 'ledger.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
check('L1 ledger.js still touches no files and no page', !/require\('fs'\)|document\.|window\./.test(src));

// RENAME
const d = mk(), snap = JSON.stringify(d);
let r = L.renameAccount(d, 'cc', '  Chase   Freedom ');
check('rename: ok, new object, name tidied (trimmed, spaces collapsed), original untouched', r.ok && r.changed === true && r.data !== d && r.data.accounts.find(a => a.id === 'cc').name === 'Chase Freedom' && JSON.stringify(d) === snap);
const cc2 = r.data.accounts.find(a => a.id === 'cc'), cc1 = d.accounts.find(a => a.id === 'cc');
check('rename changes only the name (id, kind, role, opening, closed all the same)', JSON.stringify(Object.assign({}, cc2, { name: 'x' })) === JSON.stringify(Object.assign({}, cc1, { name: 'x' })));
check('other accounts and all entries unchanged', JSON.stringify(r.data.accounts.filter(a => a.id !== 'cc')) === JSON.stringify(d.accounts.filter(a => a.id !== 'cc')) && JSON.stringify(r.data.transactions) === JSON.stringify(d.transactions) && r.data.settings.a === 1);
r = L.renameAccount(d, 'vault', 'Main Savings');
check('VAULT can be renamed; it keeps its role and id (so everything that uses the role still works)', r.ok && r.data.accounts[0].name === 'Main Savings' && r.data.accounts[0].role === 'vault' && r.data.accounts[0].id === 'vault' && L.validate(r.data).length === 0);
r = L.renameAccount(d, 'flex', 'flex');
check('changing only the capital letters of its own name is allowed', r.ok && r.data.accounts[1].name === 'flex');
r = L.renameAccount(d, 'cc', 'FREEDOM');
check('renaming to the very same name is ok and changes nothing (same object, changed false)', r.ok && r.changed === false && r.data === d);
r = L.renameAccount(d, 'cc', 'line\none\ttab\u0000x');
check('line breaks, tabs and control characters become single spaces', r.ok && r.data.accounts.find(a => a.id === 'cc').name === 'line one tab x', r.ok && r.data.accounts.find(a => a.id === 'cc').name);
r = L.renameAccount(d, 'cc', 'Visa\u00a0\u2003 Card');
check('odd spaces (non-breaking, wide) pasted into a name become one normal space', r.ok && r.data.accounts.find(a => a.id === 'cc').name === 'Visa Card', r.ok && JSON.stringify(r.data.accounts.find(a => a.id === 'cc').name));
const refusals = [
  ['unknown account', () => L.renameAccount(d, 'nope', 'X')],
  ['empty name', () => L.renameAccount(d, 'cc', '')],
  ['spaces only', () => L.renameAccount(d, 'cc', '   \n ')],
  ['41 characters', () => L.renameAccount(d, 'cc', 'x'.repeat(41))],
  ['not text (number)', () => L.renameAccount(d, 'cc', 5)],
  ['not text (null)', () => L.renameAccount(d, 'cc', null)],
  ['same as another account (exact)', () => L.renameAccount(d, 'cc', 'VAULT')],
  ['same as another account (different case and spacing)', () => L.renameAccount(d, 'cc', '  vault ')],
  ['same as a CLOSED account', () => L.renameAccount(d, 'cc', 'old card')],
  ['no data', () => L.renameAccount(null, 'cc', 'X')]
];
for (const [name, f] of refusals) { let x; try { x = f(); } catch (e) { x = { ok: true, thrown: e.message }; } check('rename refused: ' + name, x.ok === false && typeof x.error === 'string' && JSON.stringify(d) === snap, JSON.stringify(x).slice(0, 100)); }
check('40 characters is the longest allowed', L.renameAccount(d, 'cc', 'y'.repeat(40)).ok);

// ADD
const nw0 = L.netWorthCents(d, D);
let a = L.addAccount(d, { name: ' Capital One ', kind: 'credit_card', owedCents: 12345, date: D, makeId: mkId });
check('add card: ok, a NEW object, original untouched, id returned', a.ok && a.data !== d && a.id === 'new1' && JSON.stringify(d) === snap && a.data.accounts.length === d.accounts.length + 1);
const na = a.data.accounts[a.data.accounts.length - 1];
check('exact shape: id, tidy name, kind, role none, opening = owed, opening date, open', JSON.stringify(na) === JSON.stringify({ id: 'new1', name: 'Capital One', kind: 'credit_card', role: 'none', openingCents: 12345, openingDate: D, closed: false }), JSON.stringify(na));
check('what is owed shows as the balance from that day, and net worth drops by the same amount', L.balanceCents(a.data, 'new1', D) === 12345 && L.netWorthCents(a.data, D) === nw0 - 12345);
check('an entry or transfer dated BEFORE the new account started is refused (it would silently not count)', (() => { const e1 = L.addTransaction(a.data, { accountId: 'new1', date: '2026-11-06', description: 'early', amountCents: 100, makeId: mkId }); const e2 = L.addTransfer(a.data, { fromId: 'vault', toId: 'new1', amountCents: 100, date: '2026-11-06', description: 't', makeId: mkId }); return !e1.ok && /started on 2026-11-07/.test(e1.error) && !e2.ok && /started on/.test(e2.error); })());
check('an entry or transfer dated on the start day or later is accepted', L.addTransaction(a.data, { accountId: 'new1', date: D, description: 'same day', amountCents: 100, makeId: mkId }).ok && L.addTransfer(a.data, { fromId: 'vault', toId: 'new1', amountCents: 100, date: '2026-12-01', description: 't', makeId: mkId }).ok);
check('the result is a valid file', L.validate(a.data).length === 0);
a = L.addAccount(d, { name: 'Student Loan', kind: 'loan', owedCents: 0, date: D, makeId: mkId });
check('a loan with 0 owed is fine', a.ok && L.balanceCents(a.data, a.id, D) === 0);
const zc = L.addAccount(d, { name: 'Z', kind: 'credit_card', owedCents: 5000, date: D, makeId: mkId });
const paid = L.addTransaction(zc.data, { accountId: zc.id, date: D, description: 'pay', amountCents: 2000, makeId: mkId });
check('an entry on the new card works like any other (payment of 20.00 -> owes 30.00)', zc.ok && paid.ok && L.balanceCents(paid.data, zc.id, D) === 3000, JSON.stringify(paid).slice(0, 100));
const addBad = [
  ['bank kind', { kind: 'bank' }], ['savings kind', { kind: 'savings' }], ['receivable kind', { kind: 'receivable' }], ['no kind', { kind: undefined }],
  ['negative owed', { owedCents: -1 }], ['fractional cents', { owedCents: 1.5 }], ['NaN', { owedCents: NaN }], ['text', { owedCents: '100' }], ['absurd size', { owedCents: 9e13 + 1 }],
  ['bad date', { date: '2026-02-30' }], ['no date', { date: undefined }], ['empty name', { name: '' }], ['long name', { name: 'q'.repeat(41) }],
  ['duplicate name', { name: 'freedom' }], ['duplicate of a closed account', { name: 'OLD CARD' }],
  ['id already used', { makeId: () => 'cc' }], ['id junk', { makeId: () => 5 }], ['id empty', { makeId: () => '' }]
];
for (const [name, o] of addBad) { const x = L.addAccount(d, Object.assign({ name: 'Fresh', kind: 'credit_card', owedCents: 100, date: D, makeId: mkId }, o)); check('add refused: ' + name, x.ok === false && typeof x.error === 'string' && JSON.stringify(d) === snap, JSON.stringify(x).slice(0, 100)); }
check('add with no data / no accounts list never throws and is refused', (() => { try { return !L.addAccount(null, { name: 'A', kind: 'loan', owedCents: 1, date: D }).ok && !L.addAccount({}, { name: 'A', kind: 'loan', owedCents: 1, date: D }).ok && !L.addAccount(d).ok; } catch (e) { return false; } })());
const dflt = L.addAccount(d, { name: 'A', kind: 'loan', owedCents: 1, date: D }), dflt2 = L.addAccount(dflt.data, { name: 'B', kind: 'loan', owedCents: 1, date: D });
check('built-in ids are unique and contain no odd characters', dflt.ok && dflt2.ok && dflt.id !== dflt2.id && /^[A-Za-z0-9]+$/.test(dflt.id));

// CLOSE (existing function) + the new future-entry guard, and REOPEN
let c = L.closeAccount(d, 'car', D);
check('a card or loan on exactly 0 can be closed', c.ok && c.data.accounts.find(x => x.id === 'car').closed === true && JSON.stringify(d) === snap);
const fut = L.addTransaction(d, { accountId: 'car', date: '2027-01-15', description: 'later', amountCents: 100, makeId: mkId }).data;
check('a loan that is on 0 today but has an entry dated LATER cannot be closed (its balance would change while hidden)', (() => { const x = L.closeAccount(fut, 'car', D); return !x.ok && /after/.test(x.error); })());
check('an entry dated today does not block closing', (() => { const t = L.addTransaction(d, { accountId: 'car', date: D, description: 'zero', amountCents: 100, makeId: mkId }).data; const t2 = L.addTransaction(t, { accountId: 'car', date: D, description: 'back', amountCents: -100, makeId: mkId }).data; return L.closeAccount(t2, 'car', D).ok; })());
check('VAULT, FLEX and FUNDS can never be closed, even at 0', !L.closeAccount(d, 'flex', D).ok && !L.closeAccount(d, 'funds', D).ok);
c = L.reopenAccount(L.closeAccount(d, 'car', D).data, 'car');
check('reopen: the account is open again and the file equals the original', c.ok && JSON.stringify(c.data) === snap);
check('reopen refused when the account is open or unknown', !L.reopenAccount(d, 'cc').ok && !L.reopenAccount(d, 'nope').ok && !L.reopenAccount(null, 'cc').ok);
const ro = L.reopenAccount(d, 'old');
check('a closed account reopens and keeps its history', ro.ok && ro.data.accounts.find(x => x.id === 'old').closed === false && L.validate(ro.data).length === 0);

// L4 many operations in a row keep the file valid and the names unique
let cur = mk(), ok = true, count = 0;
for (let i = 0; i < 200; i++) {
  const x = L.addAccount(cur, { name: 'Acct ' + i, kind: i % 2 ? 'loan' : 'credit_card', owedCents: i * 100, date: D, makeId: mkId });
  if (!x.ok) { ok = false; break; } cur = x.data; count++;
  const y = L.renameAccount(cur, x.id, 'Renamed ' + i); if (!y.ok) { ok = false; break; } cur = y.data;
  if (i % 3 === 0) { const t = L.addTransaction(cur, { accountId: x.id, date: D, description: 'p', amountCents: i * 100, makeId: mkId }); if (i > 0 && t.ok) { cur = t.data; const z = L.closeAccount(cur, x.id, D); if (!z.ok) { ok = false; break; } cur = z.data; const w = L.reopenAccount(cur, x.id); if (!w.ok) { ok = false; break; } cur = w.data; } }
}
const names = cur.accounts.map(a => a.name.toLowerCase());
check('L4 200 adds + renames + closes + reopens: always ok, file valid, every name different', ok && count === 200 && L.validate(cur).length === 0 && new Set(names).size === names.length, String(count));

console.log(passed + '/' + (passed + failed) + ' passed');
process.exit(failed ? 1 : 0);