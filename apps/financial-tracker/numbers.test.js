// Run:  node numbers.test.js     (needs jsdom)
// numbers.js is a read-only helper: it prints the key money figures for a data file and must never change the file.
const fs = require('fs'), os = require('os'), path = require('path'), cp = require('child_process');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ft-numbers-'));
const write = (name, obj) => { const p = path.join(tmp, name); fs.writeFileSync(p, typeof obj === 'string' ? obj : JSON.stringify(obj)); return p; };
const run = (file) => cp.spawnSync('node', [path.join(__dirname, 'numbers.js')].concat(file === undefined ? [] : [file]), { encoding: 'utf8' });
const grab = (out, label) => { const m = new RegExp('^' + label + ' \\.+ ([\\d,.-]+)$', 'm').exec(out); return m ? Number(m[1].replace(/,/g, '')) : NaN; };

const v1 = { accounts: { vault: 5000, flex: 300, funds: 0, cc: 0, cc2: 0, car_loan: 0, brex: 0 }, settings: { vaultBufferMonths: 7 },
  fixedExpenses: [{ id: 'f1', name: 'Rent', amount: 1000, frequency: 'monthly' }, { id: 'f2', name: 'Fuel', amount: 40, frequency: 'weekly' }, { id: 'f3', name: 'Fun', amount: 20, frequency: 'weekly' }],
  groceries: { '2026-01': 430, '2026-02': 430 }, creditScores: [], paychecks: [],
  transactions: [{ id: 't1', accountId: 'vault', date: '2026-01-01', description: 'x', amount: 5000, balance: 5000, type: 'transaction' }] };
const f1 = write('v1.json', v1), before = fs.readFileSync(f1);
const r = run(f1);
check('exits 0 and says it is read only', r.status === 0 && /read only, nothing is saved/.test(r.stdout), r.stdout + r.stderr);
check('prints the file type', /File type: v1/.test(r.stdout));
check('groceries average per month = 430', grab(r.stdout, 'Groceries average per month') === 430, r.stdout);
check('monthly costs incl. groceries = 1,000 + 60 x 4.33 + 430 = 1,689.80', Math.abs(grab(r.stdout, 'Monthly costs incl. groceries') - 1689.8) < 0.005);
check('VAULT target = (1,689.80 x 7 + 1,500) rounded up = 14,000', grab(r.stdout, 'VAULT target') === 14000);
check('weekly fixed costs, FLEX allowance and both forecast figures are real numbers', ['Weekly fixed costs \\(Forecast\\)', 'FLEX weekly allowance', 'Forecast VAULT after week 1', 'Forecast VAULT after week 52'].every(l => Number.isFinite(grab(r.stdout, l))), r.stdout);
check('the file is byte-for-byte unchanged after the run', Buffer.compare(before, fs.readFileSync(f1)) === 0);
check('nothing else was created next to the file', fs.readdirSync(tmp).length === 1);

// v2
const M = require('./migrate.js');
const v2 = M.convert(JSON.parse(JSON.stringify(Object.assign({}, v1, { accounts: v1.accounts, transactions: [{ id: 't1', accountId: 'vault', date: '2026-01-01', description: 'x', amount: 5000, balance: 5000, type: 'transaction' }] }))), { today: '2026-10-29' }).data;
const f2 = write('v2.json', v2), b2 = fs.readFileSync(f2), r2 = run(f2);
check('a v2 file works too and is left unchanged', r2.status === 0 && /File type: v2/.test(r2.stdout) && grab(r2.stdout, 'VAULT target') === 14000 && Buffer.compare(b2, fs.readFileSync(f2)) === 0, r2.stdout + r2.stderr);

// failures are clear and harmless
let e = run();
check('no file name: usage message, exit code 2', e.status === 2 && /Usage/.test(e.stdout));
e = run(path.join(tmp, 'missing.json'));
check('missing file: clear message, exit code 1, nothing created', e.status === 1 && /Could not read that file/.test(e.stdout) && !fs.existsSync(path.join(tmp, 'missing.json')));
const bad = write('bad.json', '{ this is not json'), bb = fs.readFileSync(bad);
e = run(bad);
check('a broken file: clear message, exit code 1, file untouched', e.status === 1 && /Could not read that file/.test(e.stdout) && Buffer.compare(bb, fs.readFileSync(bad)) === 0);
const empty = write('empty.json', {}); e = run(empty);
check('an empty object does not crash with a stack trace', (e.status === 0 || e.status === 1) && !/at .*\(.*\.js:\d+/.test(e.stdout + e.stderr), e.stdout + e.stderr);

const src = fs.readFileSync(path.join(__dirname, 'numbers.js'), 'utf8');
check('L1 numbers.js never writes files', !/writeFile|appendFile|createWriteStream|rename|unlink|rmSync|mkdir/.test(src));
fs.rmSync(tmp, { recursive: true, force: true });
console.log(passed + '/' + (passed + failed) + ' passed');
process.exit(failed ? 1 : 0);