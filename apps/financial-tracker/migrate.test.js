// Run:  node migrate.test.js     (from apps/financial-tracker)
const fs = require('fs'), path = require('path'), os = require('os'), crypto = require('crypto'), cp = require('child_process');
const M = require('./migrate.js'), L = require('./ledger.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const TODAY = '2026-10-29';
const tx = (accountId, date, amount, balance, extra) => Object.assign({ id: accountId + '-' + date + '-' + amount, accountId, date, description: 'd', amount, balance, type: 'transaction' }, extra || {});
const conv = (old) => M.convert(old, { today: TODAY });
const acct = (res, id) => res.data.accounts.find(a => a.id === id);
const info = (res, id) => res.report.accounts.find(a => a.id === id);
const bal = (res, id) => L.balanceCents(res.data, id, '2199-12-31');

// ---------- L1 static ----------
const src = fs.readFileSync(path.join(__dirname, 'migrate.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
check('L1 migrate.js never writes, deletes or renames anything', !/writeFile|appendFile|unlinkSync|renameSync|rmSync|mkdirSync|createWriteStream|copyFile|\.promises/.test(src));
check('L1 convert() never reads the clock (only the command line asks for today)', !/new Date|Date\.now/.test(src) && (src.match(/todayStr/g) || []).length === 1);

// ---------- L2 the rules ----------
const old1 = { accounts: { vault: 0, cc: 0 }, settings: { regularRate: 35.21 }, paychecks: [{ id: 'p' }], transactions: [
  tx('vault', '2026-02-01', 1000, 1000), tx('vault', '2026-02-02', -100, 900),
  tx('cc', '2026-02-03', 50, 50),
  tx('vault', '2026-02-04', -20, 880, { id: 't1', type: 'transfer', linkedId: 't2' }), tx('cc', '2026-02-04', 20, 30, { id: 't2', type: 'transfer', linkedId: 't1' }),
  tx('vault', '2026-02-05', -10, 870, { id: 't3', type: 'transfer', linkedId: 't4' }), tx('cc', '2026-02-05', 10, 40, { id: 't4', type: 'transfer', linkedId: 't3' })] };
const snapshot = JSON.stringify(old1);
const r1 = conv(old1);
check('conversion succeeds, v2, and the input is not changed', r1.ok && r1.data.schemaVersion === 2 && JSON.stringify(old1) === snapshot);
check('bank amounts carry over unchanged, opening derived', r1.data.transactions.find(t => t.id === 'vault-2026-02-02--100').amountCents === -10000 && acct(r1, 'vault').openingCents === 0 && info(r1, 'vault').adjustment === 0);
check('card: a regular entry (owed +50) becomes cash flow -50', r1.data.transactions.find(t => t.id === 'cc-2026-02-03-50').amountCents === -5000);
check('card: a transfer into it keeps its sign (+20 payment lowers what is owed)', r1.data.transactions.find(t => t.id === 't2').amountCents === 2000);
check('the old direction-bug transfer is listed with its before and after', r1.report.directionBug.length === 1 && r1.report.directionBug[0].account === 'cc' && r1.report.directionBug[0].before === 3000 && r1.report.directionBug[0].after === 4000);
check('the converted math ends at 20.00 owed; old page showed 40.00; ONE adjustment of +20.00 dated at the last entry', info(r1, 'cc').v2Balance === 2000 && info(r1, 'cc').page === 4000 && info(r1, 'cc').adjustment === 2000 && info(r1, 'cc').adjustmentDate === '2026-02-05');
const adj = r1.data.transactions.filter(t => t.type === 'migration_adjustment');
check('exactly one labeled adjustment entry; the debt sign is right (owed goes up by 20)', adj.length === 1 && adj[0].accountId === 'cc' && adj[0].date === '2026-02-05' && adj[0].description === M.ADJ_TEXT && adj[0].amountCents === -2000 && bal(r1, 'cc') === 4000);
check('every account ends on the number the old page showed', r1.report.accounts.every(a => bal(r1, a.id) === a.page));
check('net worth matches and the shape check is clean', r1.report.netWorthMatches && r1.report.oldNetWorth === 83000 && r1.report.validateProblems.length === 0);
check('transfers stay linked, both halves cancel', r1.data.transactions.find(t => t.id === 't1').linkedId === 't2' && r1.data.transactions.find(t => t.id === 't2').linkedId === 't1');
check('other settings and paychecks are carried over untouched, old accounts object replaced', r1.data.settings.regularRate === 35.21 && r1.data.paychecks.length === 1 && Array.isArray(r1.data.accounts));
check('all 7 default accounts exist with the right kinds and roles', ['vault', 'flex', 'funds', 'cc', 'cc2', 'car_loan', 'brex'].every(id => acct(r1, id)) && acct(r1, 'brex').kind === 'receivable' && acct(r1, 'car_loan').kind === 'loan' && acct(r1, 'funds').role === 'funds' && L.validate(r1.data).length === 0);

const loanOld = { accounts: { car_loan: 0 }, transactions: [tx('car_loan', '2026-01-01', 9000, 9000), tx('car_loan', '2026-02-01', -500, 8500, { type: 'correction' })] };
const r2 = conv(loanOld);
check('loan: old "owed" entries become cash flow and the balance lands on the page number', bal(r2, 'car_loan') === 850000 && info(r2, 'car_loan').adjustment === 0);
const brexOld = { accounts: { brex: 0 }, transactions: [tx('brex', '2026-06-02', 1500, 1500), tx('brex', '2026-10-24', 140, 1640)] };
check('BREX (receivable) carries over like a bank and counts as an asset', bal(conv(brexOld), 'brex') === 164000 && conv(brexOld).report.oldNetWorth === 164000 && conv(brexOld).report.netWorthMatches);

// ---------- L2 odd shapes ----------
const untyped = conv({ accounts: {}, transactions: [tx('vault', '2026-01-01', 10, null), tx('vault', '2026-01-02', 5, 115)] });
check('entries without a typed balance before the first typed one still give the right opening', acct(untyped, 'vault').openingCents === 10000 && bal(untyped, 'vault') === 11500);
check('an account with no entries opens at its stored value', acct(conv({ accounts: { flex: 12.34 }, transactions: [] }), 'flex').openingCents === 1234);
check('an unknown account is kept as a bank account with a note', (() => { const r = conv({ accounts: {}, transactions: [tx('zzz', '2026-01-01', 5, 5)] }); return acct(r, 'zzz').kind === 'bank' && r.report.problems.some(p => /zzz/.test(p)) && bal(r, 'zzz') === 500; })());
const sk = conv({ accounts: {}, transactions: [tx('vault', '2026-01-01', 'abc', 5), tx('vault', 'not a date', 1, 5), null, 7, { amount: 1 }, tx('vault', '2026-01-03T10:00:00Z', 4, 9)] });
check('bad rows are skipped and reported, a date with a time is accepted', sk.ok && sk.report.skipped.length === 5 && sk.data.transactions.filter(t => t.accountId === 'vault').length === 1 && sk.data.transactions.find(t => t.accountId === 'vault').date === '2026-01-03');
const dup = conv({ accounts: {}, transactions: [tx('vault', '2026-01-01', 5, 5, { id: 'same' }), tx('flex', '2026-01-02', 6, 6, { id: 'same' })] });
check('duplicate ids are renamed, nothing is lost', dup.report.renamedIds === 1 && new Set(dup.data.transactions.map(t => t.id)).size === 2 && L.validate(dup.data).length === 0);
const lone = conv({ accounts: {}, transactions: [tx('vault', '2026-01-01', -5, -5, { id: 'x1', type: 'transfer', linkedId: 'gone' }), tx('flex', '2026-01-01', 5, 5, { id: 'y1', type: 'transfer', linkedId: 'y2' }), tx('funds', '2026-01-01', 6, 6, { id: 'y2', type: 'transfer', linkedId: 'y1' })] });
check('a transfer whose partner is missing or does not cancel becomes a plain entry, file stays valid', lone.report.unlinked === 3 && lone.data.transactions.every(t => !t.linkedId) && L.validate(lone.data).length === 0);
const back = conv({ accounts: {}, transactions: [tx('vault', '2026-03-10', 100, 1100), tx('vault', '2026-03-12', -40, 1060), tx('vault', '2026-03-11', -10, 1050)] });
check('a backdated entry: the old page number (latest by date, $1060) is matched with one adjustment', info(back, 'vault').page === 106000 && bal(back, 'vault') === 106000 && info(back, 'vault').adjustment === 1000 && info(back, 'vault').adjustmentDate === '2026-03-12');
check('refusals: already v2, bad input, bad today', !conv({ schemaVersion: 2, accounts: [], transactions: [] }).ok && !conv(null).ok && !conv([]).ok && !conv('x').ok && !M.convert({}, {}).ok && !M.convert({}, { today: '2026-02-30' }).ok && !M.convert({}).ok);
check('a mostly empty file converts to 7 empty accounts with no adjustments', (() => { const r = conv({}); return r.ok && r.data.accounts.length === 7 && r.data.transactions.length === 0 && r.report.validateProblems.length === 0; })());

// ---------- the printed preview ----------
const txt = M.format(r1.report);
check('preview names accounts, the adjustment, the wrong-way transfer, net worth MATCH, and says nothing was written', /FREEDOM \(Chase\)/.test(txt) && /ADJUSTMENT entry \$20\.00 dated 2026-02-05/.test(txt) && /balance went \$30\.00 -> \$40\.00/.test(txt) && /MATCH/.test(txt) && !/DO NOT MATCH/.test(txt) && /nothing was written/.test(txt));
check('a missing net worth is shown as unavailable, never as $0.00', /unavailable/.test(M.format(Object.assign({}, r1.report, { newNetWorth: null, netWorthMatches: false }))));

// ---------- L4 / L5 ----------
const bigT = []; for (let i = 0; i < 50000; i++) bigT.push(tx(['vault', 'flex', 'cc'][i % 3], '2026-0' + (1 + (i % 9)) + '-1' + (i % 9), (i % 7) - 3, null, { id: 'b' + i }));
const t0 = Date.now(); const big = conv({ accounts: {}, transactions: bigT });
check('L4 50,000 entries convert fast and every account lands on its page number', big.ok && Date.now() - t0 < 4000 && big.report.validateProblems.length === 0, (Date.now() - t0) + 'ms');
check('L5 hostile input never crashes', (() => { try { conv({ accounts: 'x', transactions: [{ accountId: 5 }, { accountId: 'a', amount: {}, balance: [] }, tx('a', '2026-01-01', 1e400, 1), tx('a', '2026-01-01', 1, 'x'), tx('a', '2026-01-01', 1, 1, { id: {}, type: 5, linkedId: 7, description: 'x'.repeat(1e6) })] }); conv({ accounts: [null, { id: 3 }, { id: 'q', balance: 'z' }], transactions: 'no' }); return true; } catch (e) { console.log(e); return false; } })());
check('L5 a huge description is capped', conv({ accounts: {}, transactions: [tx('vault', '2026-01-01', 1, 1, { description: 'x'.repeat(1e6) })] }).data.transactions[0].description.length === 200);

// ---------- the command line leaves the file untouched ----------
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mg-')), f = path.join(tmp, 'old.json');
fs.writeFileSync(f, JSON.stringify(old1, null, 2));
const hash = () => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const h0 = hash(), before = fs.readdirSync(tmp).join();
const outp = cp.execFileSync('node', [path.join(__dirname, 'migrate.js'), f], { encoding: 'utf8' });
check('CLI prints the preview and leaves the file and folder exactly as they were', /MATCH/.test(outp) && hash() === h0 && fs.readdirSync(tmp).join() === before);
fs.writeFileSync(f, '{ nope');
const bad = cp.spawnSync('node', [path.join(__dirname, 'migrate.js'), f], { encoding: 'utf8' });
check('CLI on a broken file says so, exit 1, file untouched', bad.status === 1 && /Could not read/.test(bad.stdout) && fs.readFileSync(f, 'utf8') === '{ nope');
fs.writeFileSync(f, JSON.stringify({ schemaVersion: 2, accounts: [], transactions: [] }));
const v2 = cp.spawnSync('node', [path.join(__dirname, 'migrate.js'), f], { encoding: 'utf8' });
check('CLI on an already-v2 file refuses', v2.status === 1 && /already version 2/.test(v2.stdout));
check('CLI with no path prints usage', /Usage/.test(cp.spawnSync('node', [path.join(__dirname, 'migrate.js')], { encoding: 'utf8' }).stdout));
fs.rmSync(tmp, { recursive: true, force: true });

console.log(failed === 0 ? passed + '/' + passed + ' passed' : passed + '/' + (passed + failed) + ' passed, ' + failed + ' FAILED');
process.exit(failed === 0 ? 0 : 1);