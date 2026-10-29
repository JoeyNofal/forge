// migrate-report.js - READ-ONLY report on an OLD-format (v1) Financial Tracker file.
// Shows, per account: the derived opening balance, which sign convention the old
// typed balances follow, and every entry whose typed balance does not match the math.
// It never writes anything.
//   Run:  node migrate-report.js <path-to-file> [--all]
'use strict';
const fs = require('fs');
const L = require('./ledger.js');

const money = (c) => (c < 0 ? '-' : '') + '$' + (Math.abs(c) / 100).toFixed(2);
const day = (d) => (typeof d === 'string' ? d.slice(0, 10) : '?');

function analyze(data) {
  const out = { accounts: [], problems: [] };
  if (!data || typeof data !== 'object') { out.problems.push('file is not a JSON object'); return out; }
  const txns = Array.isArray(data.transactions) ? data.transactions : [];
  const ids = [];
  const add = (id) => { if (typeof id === 'string' && id && !ids.includes(id)) ids.push(id); };
  if (Array.isArray(data.accounts)) data.accounts.forEach(a => a && add(a.id));
  else if (data.accounts && typeof data.accounts === 'object') Object.keys(data.accounts).forEach(add);
  txns.forEach(t => t && typeof t === 'object' && add(t.accountId));

  for (const id of ids) {
    const rows = [];
    let unusable = 0;
    txns.forEach((t, i) => {
      if (!t || typeof t !== 'object' || t.accountId !== id) return;
      const amt = L.toCents(t.amount), bal = L.toCents(t.balance);
      if (amt === null || bal === null) { unusable++; return; }
      rows.push({ i, date: day(t.date), desc: String(t.description == null ? '' : t.description), amt, bal, type: t.type });
    });
    const a = { id, entries: rows.length, unusable, first: null, last: null, convention: 'unknown', opening: null, lastByDate: null, lastByOrder: null, summed: null, adjustment: null, mismatches: [], storedValue: null };
    if (data.accounts && !Array.isArray(data.accounts)) { const sv = L.toCents(data.accounts[id]); a.storedValue = sv; }
    if (rows.length) {
      let same = 0, opp = 0;
      const pairs = [];
      for (let k = 1; k < rows.length; k++) {
        const delta = rows[k].bal - rows[k - 1].bal, amt = rows[k].amt;
        const isSame = delta === amt, isOpp = delta === -amt;
        if (amt !== 0) { if (isSame) same++; else if (isOpp) opp++; }
        pairs.push({ row: rows[k], prev: rows[k - 1], delta });
      }
      const sign = opp > same ? -1 : 1;
      a.convention = same + opp === 0 ? 'unknown (too few entries)' : sign === 1 ? 'same (balance moves with the amount)' : 'opposite (balance moves against the amount)';
      for (const p of pairs) {
        if (p.delta !== sign * p.row.amt) a.mismatches.push({ date: p.row.date, desc: p.row.desc, amount: p.row.amt, typed: p.row.bal, expected: p.prev.bal + sign * p.row.amt, gap: p.row.bal - (p.prev.bal + sign * p.row.amt) });
      }
      const f = rows[0];
      a.opening = f.bal - sign * f.amt;
      a.summed = a.opening + sign * rows.reduce((s, r) => s + r.amt, 0);
      const byDate = rows.slice().sort((x, y) => (x.date < y.date ? -1 : x.date > y.date ? 1 : x.i - y.i));
      a.first = byDate[0].date; a.last = byDate[byDate.length - 1].date;
      a.lastByDate = byDate[byDate.length - 1].bal;
      a.lastByOrder = rows[rows.length - 1].bal;
      a.adjustment = a.lastByDate - a.summed;
    }
    out.accounts.push(a);
  }
  return out;
}

function format(rep, all) {
  const lines = [];
  rep.problems.forEach(p => lines.push('PROBLEM: ' + p));
  for (const a of rep.accounts) {
    lines.push('');
    lines.push(a.id.toUpperCase() + ': ' + a.entries + ' entries' + (a.unusable ? ' (+' + a.unusable + ' unusable)' : '') + (a.first ? ', ' + a.first + ' to ' + a.last : ''));
    if (!a.entries) { lines.push('  no entries'); continue; }
    lines.push('  sign convention: ' + a.convention);
    lines.push('  opening balance (derived): ' + money(a.opening));
    lines.push('  balance the old page shows (latest by date): ' + money(a.lastByDate));
    if (a.lastByOrder !== a.lastByDate) lines.push('  last entry typed (by entry order): ' + money(a.lastByOrder) + '  <-- differs');
    if (a.storedValue !== null) lines.push('  stored accounts{} value: ' + money(a.storedValue) + (a.storedValue !== a.lastByDate ? '  <-- differs (the page ignores it)' : ''));
    lines.push('  balance if only the amounts are added up: ' + money(a.summed));
    lines.push('  migration adjustment needed: ' + money(a.adjustment) + (a.adjustment === 0 ? '  (none)' : ''));
    lines.push('  entries whose typed balance does not fit: ' + a.mismatches.length);
    const show = all ? a.mismatches : a.mismatches.slice(0, 10);
    for (const m of show) lines.push('    ' + m.date + '  ' + m.desc.slice(0, 28).padEnd(28) + ' amount ' + money(m.amount) + '  typed ' + money(m.typed) + '  math says ' + money(m.expected) + '  gap ' + money(m.gap));
    if (a.mismatches.length > show.length) lines.push('    ... and ' + (a.mismatches.length - show.length) + ' more (run with --all)');
  }
  return lines.join('\n');
}

if (require.main === module) {
  const file = process.argv[2];
  if (!file) { console.log('Usage: node migrate-report.js <path-to-file> [--all]'); process.exit(2); }
  let data;
  try { data = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { console.log('Could not read the file as JSON: ' + e.message); process.exit(1); }
  console.log(format(analyze(data), process.argv.includes('--all')));
}
module.exports = { analyze, format };