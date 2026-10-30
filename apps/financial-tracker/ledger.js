// ledger.js - money math for the Financial Tracker (data format v2).
// Pure functions: no clock, no files, no page. Money is whole CENTS (integers).
//
// SIGN RULE (one rule for every account): a transaction's amountCents is
// CASH FLOW. Negative = money going out, positive = money coming in.
//   bank / savings : balance = opening + sum(amounts)
//   credit_card / loan (AMOUNT OWED, positive = owed):
//                    balance = opening - sum(amounts)
//   (spending on a card is negative, so the debt grows; a payment is positive,
//    so the debt shrinks.)
//   receivable (money someone owes YOU, e.g. a friend you lent to) behaves like
//    a bank account and counts as an asset: lending more is positive, a
//    repayment is negative.
// A transaction counts from its own date onward (date <= asOf), and only if its
// date is on or after the account's openingDate (the opening balance already
// includes anything older).
'use strict';

(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./dates.js'));
  else root.FTLedger = factory(root.FTDates);
})(typeof self !== 'undefined' ? self : this, function (D) {

const KINDS = ['bank', 'savings', 'credit_card', 'loan', 'receivable'];
const ROLES = ['vault', 'flex', 'funds', 'none'];
const MAX_CENTS = 9e13; // $900 billion: anything larger is a typo, not money
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function isDebt(kind) { return kind === 'credit_card' || kind === 'loan'; }
function validDate(s) { return typeof s === 'string' && DATE_RE.test(s) && D.parseDate(s) !== null && D.fmtDateInput(D.parseDate(s)) === s; }

// "12.34", "$1,234.5", 12.345 -> cents (rounded to the nearest cent). Bad input -> null.
function toCents(x) {
  let n;
  if (typeof x === 'number') n = x;
  else if (typeof x === 'string') {
    const t = x.trim().replace(/[$,\s]/g, '');
    if (!/^-?\d+(\.\d+)?$|^-?\.\d+$/.test(t)) return null;
    n = Number(t);
  } else return null;
  if (!Number.isFinite(n)) return null;
  const c = Math.round(Math.abs(n) * 100 + 1e-9) * (n < 0 ? -1 : 1);
  if (Math.abs(c) > MAX_CENTS) return null;
  return c === 0 ? 0 : c;
}
function fromCents(c) { return Number.isSafeInteger(c) ? c / 100 : NaN; }

// What one transaction does to its account's balance.
function effectCents(kind, amountCents) { return isDebt(kind) ? -amountCents : amountCents; }

function findAccount(data, id) {
  const list = data && Array.isArray(data.accounts) ? data.accounts : [];
  for (const a of list) if (a && typeof a === 'object' && a.id === id) return a;
  return null;
}

// Balance of one account on a day (asOf 'YYYY-MM-DD'). Malformed rows are ignored.
function balanceCents(data, accountId, asOf) {
  const acct = findAccount(data, accountId);
  if (!acct || !validDate(asOf)) return null;
  let sum = Number.isSafeInteger(acct.openingCents) ? acct.openingCents : 0;
  const open = validDate(acct.openingDate) ? acct.openingDate : '0000-00-00';
  const txns = Array.isArray(data.transactions) ? data.transactions : [];
  for (const t of txns) {
    if (!t || typeof t !== 'object' || t.accountId !== accountId) continue;
    if (!Number.isSafeInteger(t.amountCents) || !validDate(t.date)) continue;
    if (t.date > asOf || t.date < open) continue;
    sum += effectCents(acct.kind, t.amountCents);
  }
  return sum;
}

function allBalances(data, asOf) {
  const out = {};
  const list = data && Array.isArray(data.accounts) ? data.accounts : [];
  for (const a of list) if (a && typeof a.id === 'string') out[a.id] = balanceCents(data, a.id, asOf);
  return out;
}

// Net worth = what you hold minus what you owe (closed accounts count too: they should be 0).
function netWorthCents(data, asOf) {
  let total = 0;
  const list = data && Array.isArray(data.accounts) ? data.accounts : [];
  for (const a of list) {
    if (!a || typeof a.id !== 'string') continue;
    const b = balanceCents(data, a.id, asOf);
    if (b === null) return null;
    total += isDebt(a.kind) ? -b : b;
  }
  return total;
}

let counter = 0;
function defaultId() { counter++; return 't' + Date.now().toString(36) + counter.toString(36) + Math.random().toString(36).slice(2, 8); }

// Two linked entries sharing a transfer id. Returns { ok:true, data } (a NEW data
// object; the input is untouched) or { ok:false, error }.
function addTransfer(data, opts) {
  const o = opts || {};
  const from = findAccount(data, o.fromId), to = findAccount(data, o.toId);
  if (!from || !to) return { ok: false, error: 'unknown account' };
  if (from.id === to.id) return { ok: false, error: 'cannot transfer to the same account' };
  if (from.closed || to.closed) return { ok: false, error: 'account is closed' };
  if (!Number.isSafeInteger(o.amountCents) || o.amountCents <= 0 || o.amountCents > MAX_CENTS) return { ok: false, error: 'amount must be a positive number of cents' };
  if (!validDate(o.date)) return { ok: false, error: 'bad date' };
  const mk = typeof o.makeId === 'function' ? o.makeId : defaultId;
  const id1 = mk(), id2 = mk();
  if (!id1 || !id2 || id1 === id2) return { ok: false, error: 'could not make ids' };
  const desc = typeof o.description === 'string' ? o.description.slice(0, 200) : '';
  const base = { date: o.date, description: desc, type: 'transfer', transferId: id1 };
  const out = Object.assign({}, data, { transactions: (Array.isArray(data.transactions) ? data.transactions : []).concat([
    Object.assign({ id: id1, accountId: from.id, amountCents: -o.amountCents, linkedId: id2 }, base),
    Object.assign({ id: id2, accountId: to.id, amountCents: o.amountCents, linkedId: id1 }, base),
  ]) });
  return { ok: true, data: out };
}

// One ordinary entry typed by amount only (cash flow: + money in, - money out). Returns
// { ok:true, data, id } (a NEW data object; the input is untouched) or { ok:false, error }.
function addTransaction(data, opts) {
  const o = opts || {};
  const a = findAccount(data, o.accountId);
  if (!a) return { ok: false, error: 'unknown account' };
  if (a.closed) return { ok: false, error: 'account is closed' };
  if (!Number.isSafeInteger(o.amountCents) || o.amountCents === 0 || Math.abs(o.amountCents) > MAX_CENTS) return { ok: false, error: 'amount must be a non-zero number of cents' };
  if (!validDate(o.date)) return { ok: false, error: 'bad date' };
  const desc = typeof o.description === 'string' ? o.description.trim().slice(0, 200) : '';
  if (!desc) return { ok: false, error: 'description is empty' };
  const txns = Array.isArray(data.transactions) ? data.transactions : [];
  const mk = typeof o.makeId === 'function' ? o.makeId : defaultId;
  const id = mk();
  if (typeof id !== 'string' || !id || txns.some(x => x && x.id === id)) return { ok: false, error: 'could not make a unique id' };
  const t = { id, accountId: a.id, date: o.date, description: desc, amountCents: o.amountCents, type: 'transaction' };
  return { ok: true, id, data: Object.assign({}, data, { transactions: txns.concat([t]) }) };
}

// Delete one entry. If it is half of a transfer, bothHalves:true removes the partner too.
function deleteTransaction(data, id, bothHalves) {
  const txns = Array.isArray(data.transactions) ? data.transactions : [];
  const t = txns.find(x => x && x.id === id);
  if (!t) return { ok: false, error: 'not found' };
  const gone = new Set([id]);
  if (bothHalves && t.linkedId) gone.add(t.linkedId);
  return { ok: true, data: Object.assign({}, data, { transactions: txns.filter(x => !(x && gone.has(x.id))) }), removed: gone.size, partner: t.linkedId || null };
}

// Close an account: only if it is not VAULT/FLEX/FUNDS and its balance is exactly 0.
function closeAccount(data, id, asOf) {
  const a = findAccount(data, id);
  if (!a) return { ok: false, error: 'unknown account' };
  if (a.role && a.role !== 'none') return { ok: false, error: 'this account has a special role and cannot be closed' };
  const b = balanceCents(data, id, asOf);
  if (b === null) return { ok: false, error: 'bad date' };
  if (b !== 0) return { ok: false, error: 'balance is not zero' };
  return { ok: true, data: Object.assign({}, data, { accounts: data.accounts.map(x => x === a ? Object.assign({}, x, { closed: true }) : x) }) };
}

// Problems with the file's shape (empty list = fine).
function validate(data) {
  const p = [];
  if (!data || typeof data !== 'object') return ['data is not an object'];
  if (!Array.isArray(data.accounts)) return ['accounts is not a list'];
  const ids = new Set(), roles = {};
  for (const a of data.accounts) {
    if (!a || typeof a !== 'object' || typeof a.id !== 'string' || !a.id) { p.push('account without an id'); continue; }
    if (ids.has(a.id)) p.push('duplicate account id ' + a.id);
    ids.add(a.id);
    if (!KINDS.includes(a.kind)) p.push(a.id + ': bad kind');
    if (!ROLES.includes(a.role || 'none')) p.push(a.id + ': bad role');
    if (a.role && a.role !== 'none') { if (roles[a.role]) p.push('role used twice: ' + a.role); roles[a.role] = 1; }
    if (!Number.isSafeInteger(a.openingCents)) p.push(a.id + ': openingCents is not whole cents');
    if (!validDate(a.openingDate)) p.push(a.id + ': bad openingDate');
  }
  for (const r of ['vault', 'flex', 'funds']) if (!roles[r]) p.push('missing role ' + r);
  const txns = Array.isArray(data.transactions) ? data.transactions : [];
  const tids = new Set();
  for (const t of txns) {
    if (!t || typeof t !== 'object' || typeof t.id !== 'string') { p.push('transaction without an id'); continue; }
    if (tids.has(t.id)) p.push('duplicate transaction id ' + t.id);
    tids.add(t.id);
    if (!ids.has(t.accountId)) p.push(t.id + ': unknown account');
    if (!Number.isSafeInteger(t.amountCents)) p.push(t.id + ': amountCents is not whole cents');
    if (!validDate(t.date)) p.push(t.id + ': bad date');
  }
  for (const t of txns) if (t && t.linkedId) {
    const q = txns.find(x => x && x.id === t.linkedId);
    if (!q || q.linkedId !== t.id) p.push(t.id + ': transfer partner missing');
    else if (q.amountCents + t.amountCents !== 0) p.push(t.id + ': transfer halves do not cancel');
  }
  return p;
}

return { KINDS, ROLES, MAX_CENTS, isDebt, toCents, fromCents, effectCents, findAccount, balanceCents, allBalances, netWorthCents, addTransfer, addTransaction, deleteTransaction, closeAccount, validate };
});