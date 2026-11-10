// settingscheck.js - checks the Settings page boxes before anything is saved.
// Pure functions: no page, no files, no clock. Input is what was TYPED (text);
// output is either the clean settings values or the first bad box.
// Rules: a blank box counts as 0, except the boxes marked "required".
// All or nothing: the caller saves nothing unless ok is true.
// Overtime / night shift are typed as percentages (150) and stored as
// multipliers (1.5).
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.FTSettingsCheck = factory();
})(typeof self !== 'undefined' ? self : this, function () {

const MAX = 1000000;
// key = name in the raw input, to = settings key, label = name shown in the message
const BOXES = [
  { key: 'rate',         to: 'regularRate',           label: 'Hourly Rate',                 kind: 'money', required: true, exclusiveMin: 0, max: MAX },
  { key: 'ot',           to: 'overtimeMultiplier',    label: 'OT Multiplier (%)',           kind: 'percentMult', min: 0, max: MAX },
  { key: 'ns',           to: 'nightshiftMultiplier',  label: 'Nightshift Multiplier (%)',   kind: 'percentMult', min: 0, max: MAX },
  { key: 'benefits',     to: 'benefitsDeduction',     label: 'Benefits Deduction',          kind: 'money', min: 0, max: MAX },
  { key: 'other',        to: 'otherDeductions',       label: 'Other Deductions',            kind: 'money', min: 0, max: MAX },
  { key: 'ret',          to: 'retirementPercent',     label: 'Retirement (%)',              kind: 'money', min: 0, max: 100 },
  { key: 'flexfloor',    to: 'flexFloor',             label: 'FLEX Floor',                  kind: 'money', min: 0, max: MAX },
  { key: 'vaultmonths',  to: 'vaultBufferMonths',     label: 'VAULT Buffer Months',         kind: 'whole', min: 0 },
  { key: 'carloan',      to: 'carLoanMonthlyTarget', optionalBox: true,  label: 'Car Loan Monthly Target',     kind: 'money', min: 0, max: MAX },
  { key: 'carmin',       to: 'carFundMinimum',        label: 'Car Fund Minimum',            kind: 'money', min: 0, max: MAX, optionalBox: true },
  { key: 'cartarget',    to: 'carFundTarget',         label: 'Car Fund Target',             kind: 'money', min: 0, max: MAX, optionalBox: true },
  { key: 'carloaninitial', to: 'carLoanInitial', optionalBox: true,      label: 'Car Loan Initial Balance',    kind: 'money', min: 0, max: MAX },
  { key: 'cclimit',      to: 'ccLimit',               label: 'FREEDOM Credit Limit',        kind: 'money', min: 0, max: MAX },
  { key: 'ccdue',        to: 'ccPaymentDueDay',       label: 'FREEDOM Payment Due Day',     kind: 'whole', required: true, min: 1, max: 31 },
  { key: 'ccstmt',       to: 'ccStatementDay',        label: 'FREEDOM Statement Day',       kind: 'whole', required: true, min: 1, max: 31 },
  { key: 'cc2limit',     to: 'cc2Limit',              label: 'SAVOR Credit Limit',          kind: 'money', min: 0, max: MAX },
  { key: 'cc2due',       to: 'cc2PaymentDueDay',      label: 'SAVOR Payment Due Day',       kind: 'whole', required: true, min: 1, max: 31 },
  { key: 'cc2stmt',      to: 'cc2StatementDay',       label: 'SAVOR Statement Day',         kind: 'whole', required: true, min: 1, max: 31 },
  { key: 'brexstart',    to: 'brexStartingBalance',   label: 'BREX Starting Balance',       kind: 'money', min: 0, max: MAX },
  { key: 'sundaystart',  to: 'alternatingSundayStart', label: 'Alternating Sunday Start Date', kind: 'date' }
];

const NUMBER_RE = /^[+-]?(\d+(\.\d{1,2})?|\.\d{1,2})$/;   // at most 2 decimals, no letters, no e-notation
const WHOLE_RE = /^\+?\d+$/;

function fmtNum(n) { return n.toLocaleString('en-US'); }
function realDate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return false;
  const y = +m[1], mo = +m[2], d = +m[3];
  if (mo < 1 || mo > 12 || d < 1) return false;
  const dim = [31, (y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1];
  return d <= dim;
}
function clean(x) { return Number(x.toPrecision(12)); }
function rangeText(b) {
  if (b.kind === 'whole') return b.max === undefined ? 'a whole number, 0 or more' : 'a whole number from ' + b.min + ' to ' + b.max;
  if (b.exclusiveMin !== undefined) return 'more than ' + b.exclusiveMin + ' (up to ' + fmtNum(b.max) + ')';
  return 'from ' + b.min + ' to ' + fmtNum(b.max);
}

// raw: { rate: '35.21', ot: '150', ... }  (text as typed; undefined = that box is not on the page)
// current: the saved settings (only used for the date box, which keeps its old value when blank)
function validate(raw, current) {
  raw = raw || {}; current = current || {};
  const values = {};
  for (const b of BOXES) {
    let t = raw[b.key];
    if (t === undefined || t === null) {
      if (b.optionalBox) continue;
      t = '';
    }
    t = String(t).trim();
    if (b.kind === 'date') {
      if (t === '') { if (current[b.to] !== undefined) values[b.to] = current[b.to]; continue; }
      if (!realDate(t)) return { ok: false, box: b.label, message: b.label + ': not a real date (use the date picker).' };
      values[b.to] = t; continue;
    }
    if (t === '') {
      if (b.required) return { ok: false, box: b.label, message: b.label + ': cannot be blank.' };
      t = '0';
    }
    const re = b.kind === 'whole' ? WHOLE_RE : NUMBER_RE;
    if (!re.test(t)) {
      return { ok: false, box: b.label, message: b.label + ': ' + (b.kind === 'whole' ? 'must be a whole number' : 'must be a number with at most 2 decimals') + ' (you typed "' + t.slice(0, 30) + '").' };
    }
    let n = Number(t);
    if (n === 0) n = 0; // turns -0 into 0
    if (b.kind === 'whole' && !Number.isSafeInteger(n)) return { ok: false, box: b.label, message: b.label + ': that number is too large.' };
    const low = b.exclusiveMin !== undefined ? n <= b.exclusiveMin : n < b.min;
    const high = b.max !== undefined && n > b.max;
    if (low || high) return { ok: false, box: b.label, message: b.label + ': must be ' + rangeText(b) + '.' };
    values[b.to] = b.kind === 'percentMult' ? clean(n / 100) : n;
  }
  return { ok: true, values };
}

// 1.5 -> '150', 1.505 -> '150.5'  (what the percent box shows)
function toPercentText(multiplier) {
  const n = Number(multiplier);
  if (!Number.isFinite(n)) return '';
  return String(clean(n * 100));
}

return { BOXES, MAX, validate, toPercentText };
});