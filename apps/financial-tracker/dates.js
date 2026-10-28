// dates.js - date helpers for the Financial Tracker.
// A date here is ALWAYS a plain calendar date written 'YYYY-MM-DD' (no time zone, no clock time).
// Why: new Date('2026-03-13') is midnight UTC, which is the evening of the 12th in Indiana,
// and toISOString() turns "today after 8pm" into tomorrow. Neither can happen here.
// Works both in the page (window.FTDates) and in Node (require).
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.FTDates = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const DAY_MS = 86400000;
  const pad = (n, w) => String(n).padStart(w || 2, '0');

  function daysInMonth(y, m) { return new Date(Date.UTC(y, m, 0)).getUTCDate(); } // m = 1..12
  function validYMD(y, m, d) {
    return Number.isInteger(y) && Number.isInteger(m) && Number.isInteger(d) &&
      y >= 1900 && y <= 2200 && m >= 1 && m <= 12 && d >= 1 && d <= daysInMonth(y, m);
  }
  // Accepts 'YYYY-MM-DD' (a trailing time part is ignored) or a Date (read in LOCAL time).
  function parts(v) {
    if (Object.prototype.toString.call(v) === '[object Date]') {   // also true for a Date made in another window
      if (isNaN(v.getTime())) return null;
      const p = { y: v.getFullYear(), m: v.getMonth() + 1, d: v.getDate() };
      return validYMD(p.y, p.m, p.d) ? p : null;
    }
    if (typeof v !== 'string' || v.length > 40) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ][^]*)?$/.exec(v.trim());
    if (!m) return null;
    const p = { y: +m[1], m: +m[2], d: +m[3] };
    return validYMD(p.y, p.m, p.d) ? p : null;
  }
  function ymd(y, m, d) { return pad(y, 4) + '-' + pad(m) + '-' + pad(d); }
  function utc(p) { return Date.UTC(p.y, p.m - 1, p.d); }

  function toDateStr(v) { const p = parts(v); return p ? ymd(p.y, p.m, p.d) : null; }
  function todayStr(now) { return toDateStr(now || new Date()); }
  function parseDate(v) { const p = parts(v); return p ? new Date(p.y, p.m - 1, p.d) : null; }  // local midnight
  function fmtDate(v) { const p = parts(v); return p ? MONTHS[p.m - 1] + ' ' + p.d + ', ' + p.y : '—'; }
  function fmtDateInput(v) { return toDateStr(v) || ''; }
  function addDays(v, n) {
    const p = parts(v);
    if (!p || !Number.isInteger(n) || Math.abs(n) > 1000000) return null;
    const t = new Date(utc(p) + n * DAY_MS);
    return validYMD(t.getUTCFullYear(), t.getUTCMonth() + 1, t.getUTCDate()) ? ymd(t.getUTCFullYear(), t.getUTCMonth() + 1, t.getUTCDate()) : null;
  }
  function daysBetween(a, b) { const pa = parts(a), pb = parts(b); return pa && pb ? Math.round((utc(pb) - utc(pa)) / DAY_MS) : null; }
  function dayOfWeek(v) { const p = parts(v); return p ? new Date(utc(p)).getUTCDay() : null; } // 0 = Sunday
  // A bill due on the 31st in a 30-day month is due on the last day of that month.
  function dueDateInMonth(year, month, day) {
    if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) return null;
    if (year < 1900 || year > 2200 || month < 1 || month > 12 || day < 1) return null;
    return ymd(year, month, Math.min(day, daysInMonth(year, month)));
  }
  function compare(a, b) { const x = toDateStr(a), y = toDateStr(b); return x && y ? (x < y ? -1 : x > y ? 1 : 0) : null; }

  return { toDateStr, todayStr, parseDate, fmtDate, fmtDateInput, addDays, daysBetween, dayOfWeek, dueDateInMonth, compare };
});