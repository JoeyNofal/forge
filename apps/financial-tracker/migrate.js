// migrate.js - converts an OLD (v1) Financial Tracker file to the v2 ledger format, IN MEMORY.
// convert() never touches a file. The command line prints a preview and writes nothing.
//   Run:  node migrate.js <path-to-old-file>
//   Save: node migrate.js <path-to-old-file> --write <new-file.json>   (new file only, never overwrites)
//
// Rules (agreed in B2):
//  * banks / savings / receivable (BREX): amounts carry over unchanged.
//  * credit cards and loans: regular entries recorded "change in amount owed", so their sign is
//    flipped into cash flow; transfers were already written as cash flow and keep their sign.
//  * EXCEPT a transfer on a card/loan whose typed balance moved the WRONG way (the old direction
//    bug): you had already fixed the number by hand, so it is kept exactly as the old page counted
//    it (flagged with a note, not linked to its partner).
//  * old transfers had no link between their two halves: unambiguous pairs (same date and
//    description, equal and opposite amounts, different accounts) are linked.
//  * opening balance = typed balance of the first typed entry minus what the entries up to it do.
//  * if the converted math does not end on the number the old page showed, ONE labeled
//    "Migration adjustment" entry is added, dated at that account's last entry.
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./ledger.js');
const D = require('./dates.js');

const DEFS = {
  vault: { name: 'VAULT', kind: 'bank', role: 'vault' },
  flex: { name: 'FLEX', kind: 'bank', role: 'flex' },
  funds: { name: 'FUNDS', kind: 'savings', role: 'funds' },
  cc: { name: 'FREEDOM (Chase)', kind: 'credit_card', role: 'none' },
  cc2: { name: 'SAVOR (Capital One)', kind: 'credit_card', role: 'none' },
  car_loan: { name: 'Car Loan', kind: 'loan', role: 'none' },
  brex: { name: 'BREX', kind: 'receivable', role: 'none' },
};
const ADJ_TEXT = 'Migration adjustment (old typed balances did not match the math)';
const money = (c) => (c < 0 ? '-' : '') + '$' + (Math.abs(c) / 100).toFixed(2);
const okDate = (s) => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && D.parseDate(s) !== null;

function convert(old, opts) {
  const today = opts && opts.today;
  if (!okDate(today)) return { ok: false, error: 'a valid "today" (YYYY-MM-DD) is required' };
  if (!old || typeof old !== 'object' || Array.isArray(old)) return { ok: false, error: 'file is not a JSON object' };
  if (Number(old.schemaVersion) >= 2) return { ok: false, error: 'file is already version 2' };
  const txns = Array.isArray(old.transactions) ? old.transactions : [];
  const stored = {};
  if (Array.isArray(old.accounts)) old.accounts.forEach(a => { if (a && typeof a.id === 'string') stored[a.id] = L.toCents(a.balance); });
  else if (old.accounts && typeof old.accounts === 'object') Object.keys(old.accounts).forEach(k => { stored[k] = L.toCents(old.accounts[k]); });

  const ids = Object.keys(DEFS);
  const add = (id) => { if (typeof id === 'string' && id && !ids.includes(id)) ids.push(id); };
  Object.keys(stored).forEach(add);
  txns.forEach(t => t && typeof t === 'object' && add(t.accountId));

  const rep = { accounts: [], problems: [], skipped: [], unlinked: 0, renamedIds: 0, paired: 0, unpaired: 0, directionBug: [], oldNetWorth: 0, newNetWorth: null, validateProblems: [] };
  const kindOf = (id) => (DEFS[id] ? DEFS[id].kind : 'bank');
  const roleOf = (id) => (DEFS[id] ? DEFS[id].role : 'none');
  const debtOf = (id) => L.isDebt(kindOf(id));

  // pass 1: parse every entry
  const byAcct = {}, byOldId = {};
  txns.forEach((t, i) => {
    if (!t || typeof t !== 'object' || typeof t.accountId !== 'string') { rep.skipped.push({ i, why: 'not an entry' }); return; }
    const amt = L.toCents(t.amount), date = typeof t.date === 'string' ? t.date.slice(0, 10) : '';
    if (amt === null || !okDate(date)) { rep.skipped.push({ i, account: t.accountId, why: amt === null ? 'bad amount' : 'bad date' }); return; }
    const row = { i, id: typeof t.id === 'string' && t.id ? t.id : null, account: t.accountId, date, amt, bal: L.toCents(t.balance), type: typeof t.type === 'string' && t.type ? t.type : 'transaction', desc: String(t.description == null ? '' : t.description).slice(0, 200), linked: typeof t.linkedId === 'string' ? t.linkedId : null };
    (byAcct[row.account] = byAcct[row.account] || []).push(row);
    if (row.id && !byOldId[row.id]) byOldId[row.id] = row;
  });

  // sign rule per entry (needs the typed balance of the previous typed entry of the same account)
  for (const id of Object.keys(byAcct)) {
    const debt = debtOf(id);
    let prev = null;
    for (const r of byAcct[id]) {
      r.bug = false;
      if (debt && r.type === 'transfer' && r.bal !== null && prev !== null && r.amt !== 0 && r.bal - prev === r.amt) { r.bug = true; r.before = prev; }
      r.v2amt = debt ? ((r.type === 'transfer' && !r.bug) ? r.amt : -r.amt) : r.amt;
      if (r.bal !== null) prev = r.bal;
    }
  }

  // new unique ids; transfer partners must exist and cancel
  const used = new Set();
  const all = [].concat(...ids.map(id => byAcct[id] || [])).sort((a, b) => a.i - b.i);
  for (const r of all) {
    let nid = r.id || ('m' + r.i);
    if (used.has(nid)) { nid = nid + '~' + r.i; rep.renamedIds++; }
    used.add(nid); r.nid = nid;
  }
  for (const r of all) {
    r.link = null;
    if (r.type === 'transfer' && r.linked) {
      const p = byOldId[r.linked];
      if (p && p !== r && p.linked === r.id && p.amt + r.amt === 0 && !p.bug && !r.bug) r.link = p.nid; else rep.unlinked++;
    }
  }
  // old transfers had no links: pair the unambiguous ones
  const cand = all.filter(r => r.type === 'transfer' && !r.link && !r.linked && !r.bug && r.amt !== 0);
  const groups = {};
  for (const r of cand) { const k = r.date + '|' + r.desc.trim().toLowerCase() + '|' + Math.abs(r.amt); (groups[k] = groups[k] || []).push(r); }
  for (const k of Object.keys(groups)) {
    const g = groups[k];
    if (g.length === 2 && g[0].account !== g[1].account && g[0].amt + g[1].amt === 0) { g[0].link = g[1].nid; g[1].link = g[0].nid; rep.paired++; }
  }
  rep.unpaired = cand.filter(r => !r.link).length;

  const out = Object.assign({}, old);
  delete out.accounts; delete out.transactions;
  const accounts = [], v2txns = [], lastDates = {};
  const firstDates = all.map(r => r.date).sort();
  const earliest = firstDates.length ? firstDates[0] : today;

  for (const id of ids) {
    const rows = byAcct[id] || [];
    const kind = kindOf(id), debt = debtOf(id);
    const eff = (r) => L.effectCents(kind, r.v2amt);
    const typedIdx = rows.findIndex(r => r.bal !== null);
    let opening;
    if (typedIdx >= 0) { let s = 0; for (let k = 0; k <= typedIdx; k++) s += eff(rows[k]); opening = rows[typedIdx].bal - s; }
    else opening = Number.isSafeInteger(stored[id]) ? stored[id] : 0;
    const dates = rows.map(r => r.date).sort();
    const openingDate = dates.length ? dates[0] : earliest;
    accounts.push({ id, name: DEFS[id] ? DEFS[id].name : id, kind, role: roleOf(id), openingCents: opening, openingDate, closed: false });
    if (!DEFS[id]) rep.problems.push('unknown account "' + id + '" was kept as an ordinary bank account');
    for (const r of rows) {
      const e = { id: r.nid, accountId: id, date: r.date, description: r.desc, amountCents: r.v2amt, type: r.type };
      if (r.link) e.linkedId = r.link;
      if (r.bug) e.note = 'Old app moved this balance the wrong way; kept as the old page counted it.';
      v2txns.push(e);
    }
    // the number the old page showed: latest typed balance by date (ties: entry order), else the stored value
    const typed = rows.filter(r => r.bal !== null).sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.i - b.i));
    const page = typed.length ? typed[typed.length - 1].bal : (Number.isSafeInteger(stored[id]) ? stored[id] : 0);
    rep.oldNetWorth += debt ? -page : page;
    rep.accounts.push({ id, name: accounts[accounts.length - 1].name, kind, role: roleOf(id), opening, openingDate, entries: rows.length, page, v2Balance: null, adjustment: 0, adjustmentDate: null });
    lastDates[id] = dates.length ? dates[dates.length - 1] : null;
    for (const r of rows) if (r.bug) rep.directionBug.push({ account: id, date: r.date, desc: r.desc.slice(0, 28), amount: r.amt, before: r.before, after: r.bal });
  }
  const data = Object.assign(out, { schemaVersion: 2, accounts, transactions: v2txns });
  for (const info of rep.accounts) {
    const asOf = lastDates[info.id] || today;
    info.v2Balance = L.balanceCents(data, info.id, asOf);
    const effect = info.page - info.v2Balance;
    if (effect !== 0) {
      info.adjustment = effect; info.adjustmentDate = asOf;
      data.transactions.push({ id: 'migration-adjust-' + info.id, accountId: info.id, date: asOf, description: ADJ_TEXT, amountCents: L.isDebt(info.kind) ? -effect : effect, type: 'migration_adjustment' });
    }
  }
  rep.validateProblems = L.validate(data);
  rep.newNetWorth = L.netWorthCents(data, '2199-12-31');
  rep.netWorthMatches = Number.isSafeInteger(rep.newNetWorth) && rep.newNetWorth === rep.oldNetWorth;
  return { ok: true, data, report: rep };
}

function format(r) {
  const lines = [];
  for (const a of r.accounts) {
    lines.push('');
    lines.push(a.name + '  (' + a.kind + (a.role !== 'none' ? ', role ' + a.role : '') + '): ' + a.entries + ' entries, opening ' + money(a.opening) + ' on ' + a.openingDate);
    lines.push('  converted math ends at ' + money(a.v2Balance) + '; old page showed ' + money(a.page));
    lines.push('  ' + (a.adjustment === 0 ? 'no adjustment needed' : 'ADJUSTMENT entry ' + money(a.adjustment) + ' dated ' + a.adjustmentDate));
  }
  lines.push('');
  lines.push('Wrong-way transfers on cards/loans, KEPT exactly as the old page counted them (' + r.directionBug.length + '):');
  r.directionBug.forEach(b => lines.push('  ' + b.date + '  ' + b.account + '  ' + b.desc.padEnd(28) + ' amount ' + money(b.amount) + '  balance went ' + money(b.before) + ' -> ' + money(b.after)));
  if (r.skipped.length) lines.push('Skipped entries (' + r.skipped.length + '): ' + r.skipped.slice(0, 10).map(s => (s.account || '?') + ' #' + s.i + ' ' + s.why).join('; '));
  lines.push('Old transfers paired automatically: ' + r.paired + '; left as plain entries (no clear partner): ' + r.unpaired);
  if (r.unlinked) lines.push('Transfers whose partner was missing or did not match (now plain entries): ' + r.unlinked);
  if (r.renamedIds) lines.push('Entries that shared an id (given new ids): ' + r.renamedIds);
  r.problems.forEach(p => lines.push('NOTE: ' + p));
  lines.push('');
  lines.push('Net worth from the old page numbers: ' + money(r.oldNetWorth) + '   from the converted file: ' + (Number.isSafeInteger(r.newNetWorth) ? money(r.newNetWorth) : 'unavailable') + '   ' + (r.netWorthMatches ? 'MATCH' : 'DO NOT MATCH'));
  lines.push('Shape check of the converted file: ' + (r.validateProblems.length ? r.validateProblems.length + ' problems: ' + r.validateProblems.slice(0, 5).join('; ') : 'no problems'));
  lines.push('(preview only: nothing was written)');
  return lines.join('\n');
}

// Save a converted file as a NEW file, then read it back and re-check it.
// Never overwrites anything; never touches the old file; removes only a file it just made and could not verify.
function writeConverted(res, outPath, opts) {
  if (!res || !res.ok || !res.data || !res.report) return { ok: false, error: 'nothing to write' };
  const rep = res.report;
  if (!rep.netWorthMatches) return { ok: false, error: 'net worth does not match the old page numbers' };
  if (rep.validateProblems.length) return { ok: false, error: 'the converted file has shape problems' };
  if (typeof outPath !== 'string' || !outPath) return { ok: false, error: 'no output path given' };
  const out = path.resolve(outPath);
  const norm = (p) => (process.platform === 'win32' ? p.toLowerCase() : p);
  if (opts && opts.inputPath && norm(path.resolve(opts.inputPath)) === norm(out)) return { ok: false, error: 'the output file cannot be the input file' };
  if (!/\.json$/i.test(out)) return { ok: false, error: 'the output file name must end in .json' };
  if (!fs.existsSync(path.dirname(out))) return { ok: false, error: 'the output folder does not exist' };
  const text = JSON.stringify(res.data, null, 2) + '\n';
  try { fs.writeFileSync(out, text, { flag: 'wx', encoding: 'utf8' }); }
  catch (e) { return { ok: false, error: e && e.code === 'EEXIST' ? 'that file already exists (it will not be overwritten)' : 'could not write: ' + (e && e.message) }; }
  // read it back and check it against the old page numbers
  const fails = [];
  try {
    const back = JSON.parse(fs.readFileSync(out, 'utf8'));
    if (JSON.stringify(back) !== JSON.stringify(res.data)) fails.push('the saved file differs from what was converted');
    if (L.validate(back).length) fails.push('the saved file fails the shape check');
    for (const a of rep.accounts) if (L.balanceCents(back, a.id, '2199-12-31') !== a.page) fails.push(a.name + ' does not end on the old page number');
    if (L.netWorthCents(back, '2199-12-31') !== rep.oldNetWorth) fails.push('net worth of the saved file does not match');
  } catch (e) { fails.push('the saved file could not be read back: ' + (e && e.message)); }
  if (fails.length) {
    let removed = false;
    try { fs.unlinkSync(out); removed = true; } catch (e) { removed = false; }
    return { ok: false, error: 'verification failed: ' + fails.join('; '), removed };
  }
  return { ok: true, path: out, bytes: Buffer.byteLength(text), accounts: res.data.accounts.length, entries: res.data.transactions.length };
}

if (require.main === module) {
  const args = process.argv.slice(2);
  const wi = args.indexOf('--write');
  const outArg = wi >= 0 ? args[wi + 1] : null;
  const skip = wi >= 0 ? wi + 1 : -1;
  const file = args.find((a, i) => !a.startsWith('--') && i !== skip);
  if (!file || (wi >= 0 && !outArg)) { console.log('Usage: node migrate.js <path-to-old-file> [--write <new-file.json>]'); process.exit(2); }
  let old;
  try { old = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { console.log('Could not read the file as JSON: ' + e.message); process.exit(1); }
  const res = convert(old, { today: D.todayStr() });
  if (!res.ok) { console.log('Cannot convert: ' + res.error); process.exit(1); }
  console.log(format(res.report).replace('(preview only: nothing was written)', wi >= 0 ? '' : '(preview only: nothing was written)'));
  if (wi >= 0) {
    const w = writeConverted(res, outArg, { inputPath: file });
    if (!w.ok) { console.log('NOT WRITTEN: ' + w.error + (w.removed ? ' (the new file was removed again)' : '')); process.exit(1); }
    console.log('WRITTEN and VERIFIED: ' + w.path + '  (' + w.accounts + ' accounts, ' + w.entries + ' entries, ' + w.bytes + ' bytes). The old file was not touched.');
  }
}
module.exports = { convert, format, writeConverted, DEFS, ADJ_TEXT };