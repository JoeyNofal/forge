// Run:  node migrate-report.test.js     (from apps/financial-tracker)
const fs = require('fs'), path = require('path'), os = require('os'), crypto = require('crypto'), cp = require('child_process');
const R = require('./migrate-report.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const tx = (accountId, date, amount, balance, extra) => Object.assign({ id: accountId + date + amount, accountId, date, description: 'x', amount, balance, type: 'normal' }, extra || {});
const get = (rep, id) => rep.accounts.find(a => a.id === id);

// ---------- L1 static ----------
const src = fs.readFileSync(path.join(__dirname, 'migrate-report.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
check('L1 the report never writes, deletes or renames anything', !/writeFile|appendFile|unlink|rename|rmSync|mkdir|createWriteStream|copyFile/.test(src));
check('L1 the report never reads the clock', !/new Date|Date\.now/.test(src));

// ---------- L2 conventions ----------
const bank = { accounts: { vault: 0 }, transactions: [tx('vault', '2026-01-05', 100, 1100), tx('vault', '2026-01-06', -50, 1050), tx('vault', '2026-01-07', 25.5, 1075.5)] };
const a1 = get(R.analyze(bank), 'vault');
check('bank: convention same, opening derived (1000), no mismatches, no adjustment', /^same/.test(a1.convention) && a1.opening === 100000 && a1.mismatches.length === 0 && a1.adjustment === 0 && a1.lastByDate === 107550 && a1.summed === 107550);
const card = { accounts: { cc: 0 }, transactions: [tx('cc', '2026-01-05', -30, 130), tx('cc', '2026-01-06', -20, 150), tx('cc', '2026-01-07', 60, 90)] };
const a2 = get(R.analyze(card), 'cc');
check('card: convention opposite, opening derived (100), consistent', /^opposite/.test(a2.convention) && a2.opening === 10000 && a2.mismatches.length === 0 && a2.adjustment === 0 && a2.lastByDate === 9000);
const loan = { accounts: { car_loan: 0 }, transactions: [tx('car_loan', '2026-01-05', 500, 9500), tx('car_loan', '2026-01-06', 500, 9000)] };
check('loan paid with positive amounts and falling balance is read as opposite', /^opposite/.test(get(R.analyze(loan), 'car_loan').convention));
const tb = { accounts: {}, transactions: [tx('vault', '2026-01-05', 0.1, 1.1), tx('vault', '2026-01-06', 0.2, 1.3)] };
check('cents compare: 1.1 + 0.2 = 1.3 is NOT a mismatch (no float noise)', get(R.analyze(tb), 'vault').mismatches.length === 0);

// ---------- L2 the real problems ----------
const back = { accounts: { vault: 0 }, transactions: [tx('vault', '2026-03-10', 100, 1100), tx('vault', '2026-03-12', -40, 1060), tx('vault', '2026-03-11', -10, 1050)] };
const a3 = get(R.analyze(back), 'vault');
check('a backdated entry: the typed chain is fine, so no mismatch is listed', a3.mismatches.length === 0);
check('a backdated entry: page shows $1060 (latest by date) but the true sum is $1050', a3.lastByDate === 106000 && a3.lastByOrder === 105000 && a3.summed === 105000 && a3.adjustment === 1000);
const gap = { accounts: {}, transactions: [tx('flex', '2026-01-01', 10, 110), tx('flex', '2026-01-02', 10, 150), tx('flex', '2026-01-03', 10, 160)] };
const a4 = get(R.analyze(gap), 'flex');
check('a typed balance that does not fit shows typed, expected and gap exactly', a4.mismatches.length === 1 && a4.mismatches[0].typed === 15000 && a4.mismatches[0].expected === 12000 && a4.mismatches[0].gap === 3000);
check('the adjustment needed equals shown balance minus summed amounts', a4.adjustment === a4.lastByDate - a4.summed && a4.summed === 13000 && a4.lastByDate === 16000 && a4.adjustment === 3000);
check('stored accounts{} value is compared', get(R.analyze({ accounts: { flex: 99 }, transactions: gap.transactions }), 'flex').storedValue === 9900);
check('array-format accounts and accounts with no entries are listed', (() => { const r = R.analyze({ accounts: [{ id: 'a', balance: 1 }, { id: 'b' }], transactions: [] }); return r.accounts.length === 2 && r.accounts.every(x => x.entries === 0) && /no entries/.test(R.format(r)); })());
check('string amounts and balances are understood', get(R.analyze({ accounts: {}, transactions: [tx('v', '2026-01-01', '10.50', '110.50'), tx('v', '2026-01-02', '$5', '115.5')] }), 'v').mismatches.length === 0);

// ---------- L2 formatting ----------
const txt = R.format(R.analyze(gap), false);
check('report text names the account, convention, opening, adjustment and mismatch', /FLEX: 3 entries/.test(txt) && /sign convention: same/.test(txt) && /opening balance \(derived\): \$100\.00/.test(txt) && /migration adjustment needed: \$30\.00/.test(txt) && /typed \$150\.00/.test(txt) && /math says \$120\.00/.test(txt));
check('only 10 mismatches are listed unless --all', (() => { const many = { accounts: {}, transactions: Array.from({ length: 30 }, (_, i) => tx('v', '2026-01-' + String(i + 1).padStart(2, '0'), 1, 100 + i * 5)) }; return /and 19 more/.test(R.format(R.analyze(many), false)) && !/more \(run/.test(R.format(R.analyze(many), true)); })());

// ---------- L4 / L5 ----------
let big = []; for (let i = 0; i < 50000; i++) big.push(tx('v' + (i % 3), '2026-01-01', 1, i));
const t0 = Date.now(); R.format(R.analyze({ accounts: {}, transactions: big }), false);
check('L4 50,000 entries are analysed fast', Date.now() - t0 < 3000, (Date.now() - t0) + 'ms');
check('L5 junk never crashes', (() => { try { R.format(R.analyze({ accounts: 'x', transactions: [null, 4, 'a', [], { accountId: 'z' }, { accountId: 'z', amount: 'abc', balance: 5 }, tx('z', null, 1, 1), tx('z', 5, 1, 2)] })); R.format(R.analyze(null)); R.format(R.analyze([])); R.format(R.analyze({})); R.format(R.analyze({ accounts: { a: 1 }, transactions: 'no' })); return true; } catch (e) { console.log(e); return false; } })());
check('L5 unusable rows are counted, not used', get(R.analyze({ accounts: {}, transactions: [{ accountId: 'z', amount: 'abc', balance: 5 }, tx('z', '2026-01-01', 1, 2)] }), 'z').unusable === 1);
check('L5 a one-entry account does not crash and says unknown convention', /unknown/.test(get(R.analyze({ accounts: {}, transactions: [tx('q', '2026-01-01', 5, 5)] }), 'q').convention));

// ---------- the command line leaves the file untouched ----------
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mr-')), f = path.join(tmp, 'old.json');
fs.writeFileSync(f, JSON.stringify(gap, null, 2));
const hash = () => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const h0 = hash(), before = fs.readdirSync(tmp).join();
const outp = cp.execFileSync('node', [path.join(__dirname, 'migrate-report.js'), f], { encoding: 'utf8' });
check('CLI prints the report and leaves the file and folder exactly as they were', /FLEX: 3 entries/.test(outp) && hash() === h0 && fs.readdirSync(tmp).join() === before);
fs.writeFileSync(f, '{ not json');
const bad = cp.spawnSync('node', [path.join(__dirname, 'migrate-report.js'), f], { encoding: 'utf8' });
check('CLI on a broken file says so, exit 1, does not touch it', bad.status === 1 && /Could not read/.test(bad.stdout) && fs.readFileSync(f, 'utf8') === '{ not json');
check('CLI with no path prints usage', /Usage/.test(cp.spawnSync('node', [path.join(__dirname, 'migrate-report.js')], { encoding: 'utf8' }).stdout));
fs.rmSync(tmp, { recursive: true, force: true });

console.log(failed === 0 ? passed + '/' + passed + ' passed' : passed + '/' + (passed + failed) + ' passed, ' + failed + ' FAILED');
process.exit(failed === 0 ? 0 : 1);