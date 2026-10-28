// bills.js - which fixed expenses fall due in the next N days. Pure (no clock, no Date objects):
// everything is plain 'YYYY-MM-DD' calendar dates via dates.js. Works in the page and in Node.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./dates.js'));
  else root.FTBills = factory(root.FTDates);
})(typeof self !== 'undefined' ? self : this, function (D) {
  const MAX_ITEMS = 100000;

  // Occurrences of "every `step` days, counted from `anchor`" that fall in [from, to].
  function everyNDays(anchor, step, from, to) {
    const out = [];
    let first = anchor;
    if (D.compare(anchor, from) < 0) {
      const k = Math.ceil(D.daysBetween(anchor, from) / step);
      first = D.addDays(anchor, k * step);
    }
    for (let d = first, i = 0; d && D.compare(d, to) <= 0 && i < 100; d = D.addDays(d, step), i++) out.push(d);
    return out;
  }

  function dueDayOf(e) {
    const n = typeof e.dueDay === 'string' && /^\s*\d+\s*$/.test(e.dueDay) ? parseInt(e.dueDay, 10) : e.dueDay;
    return Number.isInteger(n) && n >= 1 ? n : 1;   // missing or odd -> the 1st, like before
  }

  // expenses: the fixedExpenses list. today: 'YYYY-MM-DD'. Returns [{name, amount, date, freq}] sorted by date.
  function upcomingBills(expenses, today, days) {
    const from = D.toDateStr(today);
    const span = days === undefined ? 30 : days;
    if (!from || !Number.isInteger(span) || span < 0 || span > 400 || !Array.isArray(expenses)) return [];
    const to = D.addDays(from, span);
    const bills = [];
    for (const e of expenses.slice(0, MAX_ITEMS)) {
      if (!e || typeof e !== 'object') continue;
      const start = D.toDateStr(e.startDate), end = D.toDateStr(e.endDate);
      if (end && D.compare(end, from) < 0) continue;                 // already finished
      let dates = [];
      if (e.frequency === 'monthly') {
        const y0 = +from.slice(0, 4), m0 = +from.slice(5, 7);
        for (let k = 0; k < 4; k++) {
          const m = m0 + k, y = y0 + Math.floor((m - 1) / 12), mm = ((m - 1) % 12) + 1;
          const due = D.dueDateInMonth(y, mm, dueDayOf(e));
          if (due && D.compare(due, from) >= 0 && D.compare(due, to) <= 0) dates.push(due);
        }
      } else if (e.frequency === 'biweekly') {
        if (start) dates = everyNDays(start, 14, from, to);          // needs a start date to count from
      } else if (e.frequency === 'weekly') {
        dates = everyNDays(start || D.addDays(from, 1), 7, from, to); // no weekday known: counted from tomorrow, as before
      }
      for (const d of dates) {
        if (start && D.compare(d, start) < 0) continue;              // not started yet
        if (end && D.compare(d, end) > 0) continue;                  // already ended by then
        bills.push({ name: e.name, amount: e.amount, date: d, freq: e.frequency });
      }
    }
    return bills.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : String(a.name).localeCompare(String(b.name))));
  }

  return { upcomingBills };
});