// v2view.js - turns a v2 data file into the shape the existing pages read (READ-ONLY bridge for step B3a).
// Pure: no clock, no files, no page. Works in the page and in Node.
//   page amounts are in dollars; page balances are the running balance after each entry
//   (credit cards / loans: positive = amount owed, as the old page showed).
//   "Migration adjustment" entries are kept OUT of the normal transaction list and returned
//   separately as migrationEntries (the Ledgers page shows them in one collapsed row).
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./ledger.js'));
  else root.FTV2View = factory(root.FTLedger);
})(typeof self !== 'undefined' ? self : this, function (L) {
  function isV2(raw) { return !!raw && typeof raw === 'object' && !Array.isArray(raw) && raw.schemaVersion === 2; }

  // Old-page sign for one entry. Banks / savings / receivables: the cash flow itself.
  // Cards / loans: the old page showed the change in what is OWED, so a normal entry flips;
  // a transfer keeps its sign unless it was one of the kept wrong-way entries (those carry a note).
  function pageAmountCents(kind, t) {
    if (!L.isDebt(kind)) return t.amountCents;
    if (t.type === 'transfer' && !t.note) return t.amountCents;
    return -t.amountCents;
  }

  function toPageData(v2, asOf) {
    const accounts = Array.isArray(v2.accounts) ? v2.accounts.filter(a => a && typeof a.id === 'string') : [];
    const all = Array.isArray(v2.transactions) ? v2.transactions : [];
    const out = Object.assign({}, v2);
    delete out.schemaVersion;
    const balances = {}, txns = [], mig = [];
    for (const a of accounts) {
      const b = L.balanceCents(v2, a.id, asOf);
      balances[a.id] = b === null ? 0 : L.fromCents(b);
      const open = typeof a.openingDate === 'string' ? a.openingDate : '0000-00-00';
      const rows = [];
      all.forEach((t, i) => { if (t && typeof t === 'object' && t.accountId === a.id && Number.isSafeInteger(t.amountCents) && typeof t.date === 'string') rows.push({ t, i }); });
      rows.sort((x, y) => (x.t.date < y.t.date ? -1 : x.t.date > y.t.date ? 1 : x.i - y.i));
      let run = Number.isSafeInteger(a.openingCents) ? a.openingCents : 0;
      for (const { t } of rows) {
        if (t.date >= open) run += L.effectCents(a.kind, t.amountCents);
        const e = { id: t.id, accountId: t.accountId, date: t.date, description: t.description || '', amount: L.fromCents(pageAmountCents(a.kind, t)), balance: L.fromCents(run), type: t.type || 'transaction' };
        if (t.linkedId) e.linkedId = t.linkedId;
        if (t.note) e.note = t.note;
        (t.type === 'migration_adjustment' ? mig : txns).push(e);
      }
    }
    out.accounts = balances;
    out.transactions = txns;
    out.migrationEntries = mig;
    return out;
  }

  return { isV2, toPageData, pageAmountCents };
});