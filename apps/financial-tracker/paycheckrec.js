// paycheckrec.js - the paycheck recommendation, as pure money math (no page, no clock, no files).
// Order (agreed with Joey): 1) FLEX gets its allowance, 2) FUNDS (plain savings) is topped up so it ends
// $100 higher than it was at the previous approved paycheck, 3) VAULT is filled up to its target,
// 4) anything left over goes to FUNDS. Everything is worked out in whole cents, so the three transfers
// always add up to the net pay exactly. Inputs and outputs are dollars.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.FTPayRec = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  const SAVINGS_STEP_CENTS = 10000;            // FUNDS should end $100 above where it was last time
  const LIMIT = Number.MAX_SAFE_INTEGER / 8;   // anything bigger than this is treated as junk (0)

  // Dollars (or junk) -> whole cents. Junk, infinity and absurd sizes become 0.
  function cents(x) {
    const n = typeof x === 'string' && x.trim() === '' ? NaN : Number(x);
    if (!Number.isFinite(n)) return 0;
    const c = Math.round(n * 100);
    return Math.abs(c) > LIMIT ? 0 : (c === 0 ? 0 : c);
  }
  const has = (x) => x !== null && x !== undefined && !(typeof x === 'string' && x.trim() === '') && Number.isFinite(Number(x)) && Math.abs(Math.round(Number(x) * 100)) <= LIMIT;

  // o: { netPay, flex, currentFunds, currentVault, vaultTarget, baselineFunds (null = no earlier approved paycheck), fmt }
  function recommend(o) {
    o = o || {};
    const fmt = typeof o.fmt === 'function' ? o.fmt : (n) => '$' + n.toFixed(2);
    const money = (c) => fmt(c / 100);
    const net = Math.max(0, cents(o.netPay));
    const flexWanted = Math.max(0, cents(o.flex));
    const toFlex = Math.min(net, flexWanted);
    let remaining = net - toFlex;

    const funds = cents(o.currentFunds), vault = cents(o.currentVault);
    const vaultTarget = Math.max(0, cents(o.vaultTarget));
    const hasBase = has(o.baselineFunds);
    const base = hasBase ? cents(o.baselineFunds) : funds;
    const savingsTarget = base + SAVINGS_STEP_CENTS;
    const shortfall = savingsTarget - funds;

    const toSavings = shortfall > 0 ? Math.min(remaining, shortfall) : 0;
    remaining -= toSavings;
    const vaultShort = Math.max(0, vaultTarget - vault);
    const toVault = Math.min(remaining, vaultShort);
    const extra = remaining - toVault;

    let savingsNote;
    if (toSavings > 0) savingsNote = hasBase ? 'Savings: +' + money(toSavings) + ' so FUNDS reaches ' + money(savingsTarget) + ' ($100 above the last approved paycheck)' : 'Savings: +' + money(toSavings) + ' (no earlier approved paycheck to compare with)';
    else if (shortfall <= 0) savingsNote = 'Savings: on track \u2713 (FUNDS is already at ' + money(savingsTarget) + ' or more)';
    else savingsNote = 'Savings: no money left after FLEX';
    let vaultNote;
    if (toVault > 0) vaultNote = 'VAULT buffer: +' + money(toVault) + ' toward ' + money(vaultTarget);
    else if (vaultShort === 0) vaultNote = 'VAULT: at target \u2713';
    else vaultNote = 'VAULT: no money left';
    const extraNote = extra > 0 ? 'VAULT is full: extra ' + money(extra) + ' goes to FUNDS' : '';

    return {
      flex: toFlex / 100, toFunds: (toSavings + extra) / 100, toVault: toVault / 100,
      toSavings: toSavings / 100, extra: extra / 100, savingsTarget: savingsTarget / 100, baselineFunds: hasBase ? base / 100 : null,
      savingsNote, vaultNote, extraNote
    };
  }

  return { recommend, SAVINGS_STEP_CENTS };
});