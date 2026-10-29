// Run:  node ledger.test.js     (from apps/financial-tracker)
const fs = require('fs'), path = require('path');
const L = require('./ledger.js');
let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const A = (id, kind, role, openingCents, extra) => Object.assign({ id, name: id, kind, role: role || 'none', openingCents: openingCents || 0, openingDate: '2026-01-01', closed: false }, extra || {});
const mk = (txns, accts) => ({ schemaVersion: 2, accounts: accts || [A('vault', 'bank', 'vault', 100000), A('flex', 'bank', 'flex'), A('funds', 'savings', 'funds'), A('card', 'credit_card', 'none', 5000), A('car', 'loan', 'none', 200000)], transactions: txns || [] });
const T = (id, accountId, date, amountCents, extra) => Object.assign({ id, accountId, date, description: '', amountCents, type: 'normal' }, extra || {});
let n = 0; const ids = () => 'id' + (++n);

// ---------- L1 static ----------
const src = fs.readFileSync(path.join(__dirname, 'ledger.js'), 'utf8').replace(/\/\*[^]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\s\/\/ .*$/gm, '');
check('L1 ledger.js never reads the clock for dates', !/new Date|Date\.now\(\)\.toISOString|toISOString|getTimezoneOffset/.test(src.replace(/Date\.now\(\)\.toString\(36\)/, '')));
check('L1 ledger.js touches no files and no page', !/require\('fs'\)|require\('electron'\)|document\.|window\./.test(src));
check('L1 only depends on dates.js', (src.match(/require\(/g) || []).length === 1);

// ---------- L2 cents ----------
check('toCents basics', L.toCents('12.34') === 1234 && L.toCents(12.34) === 1234 && L.toCents('$1,234.50') === 123450 && L.toCents('-5') === -500 && L.toCents('.5') === 50);
check('toCents rounds to the nearest cent, no float drift', L.toCents(0.1 + 0.2) === 30 && L.toCents(1.005) === 101 && L.toCents(19.99 * 3) === 5997 && L.toCents('2.675') === 268);
check('toCents bad input is null', [null, undefined, '', 'abc', '1.2.3', NaN, Infinity, {}, [], true, '1e5x', '--5'].every(x => L.toCents(x) === null));
check('toCents refuses absurd sizes', L.toCents(1e20) === null && L.toCents('999999999999999999') === null);
check('toCents never returns -0', Object.is(L.toCents(-0.001), 0));
check('fromCents', L.fromCents(1234) === 12.34 && L.fromCents(-5) === -0.05 && Number.isNaN(L.fromCents(1.5)));

// ---------- L2 balances ----------
const d1 = mk([T('a', 'vault', '2026-03-01', -2500), T('b', 'vault', '2026-03-02', 10000), T('c', 'card', '2026-03-03', -3000), T('e', 'card', '2026-03-04', 1000)]);
check('bank balance = opening + entries', L.balanceCents(d1, 'vault', '2026-12-31') === 107500);
check('credit card: spending raises what is owed, a payment lowers it', L.balanceCents(d1, 'card', '2026-12-31') === 5000 + 3000 - 1000);
check('a future-dated entry counts only from its date', L.balanceCents(d1, 'vault', '2026-03-01') === 97500 && L.balanceCents(d1, 'vault', '2026-02-28') === 100000 && L.balanceCents(d1, 'vault', '2026-03-02') === 107500);
check('an entry older than the opening date is ignored', L.balanceCents(mk([T('x', 'vault', '2025-12-31', -999)]), 'vault', '2026-06-01') === 100000);
check('an entry ON the opening date counts', L.balanceCents(mk([T('x', 'vault', '2026-01-01', -999)]), 'vault', '2026-06-01') === 99001);
check('unknown account / bad date give null', L.balanceCents(d1, 'nope', '2026-01-01') === null && L.balanceCents(d1, 'vault', '2026-02-30') === null && L.balanceCents(d1, 'vault', undefined) === null);
check('no typed balance exists: editing the order of entries changes nothing', L.balanceCents(mk(d1.transactions.slice().reverse()), 'vault', '2026-12-31') === 107500);
check('allBalances lists every account', Object.keys(L.allBalances(d1, '2026-12-31')).sort().join() === 'car,card,flex,funds,vault');
check('net worth: holdings minus debts', L.netWorthCents(d1, '2026-12-31') === 107500 + 0 + 0 - 7000 - 200000);
check('net worth with an overdrawn bank account counts it as negative', L.netWorthCents(mk([T('o', 'flex', '2026-02-01', -4000)], null), '2026-12-31') === 100000 - 4000 - 5000 - 200000);

// ---------- L2 transfers (the old direction bug) ----------
const tr = (from, to, c, date) => L.addTransfer(mk(), { fromId: from, toId: to, amountCents: c, date: date || '2026-05-01', makeId: ids });
const t1 = tr('vault', 'car', 50000);
check('transfer makes two linked entries that cancel', t1.ok && t1.data.transactions.length === 2 && t1.data.transactions[0].amountCents === -t1.data.transactions[1].amountCents && t1.data.transactions[0].linkedId === t1.data.transactions[1].id && t1.data.transactions[1].linkedId === t1.data.transactions[0].id);
check('PAYING a loan from the bank LOWERS the loan (old bug: it raised it)', L.balanceCents(t1.data, 'car', '2026-12-31') === 150000 && L.balanceCents(t1.data, 'vault', '2026-12-31') === 50000);
const t2 = tr('vault', 'card', 2000);
check('paying a card lowers what is owed', L.balanceCents(t2.data, 'card', '2026-12-31') === 3000);
const t3 = tr('card', 'vault', 2000);
check('cash advance from a card raises what is owed', L.balanceCents(t3.data, 'card', '2026-12-31') === 7000 && L.balanceCents(t3.data, 'vault', '2026-12-31') === 102000);
check('transfer between two banks leaves net worth unchanged', L.netWorthCents(tr('vault', 'flex', 12345).data, '2026-12-31') === L.netWorthCents(mk(), '2026-12-31'));
check('transfer from a bank to a card/loan also leaves net worth unchanged', L.netWorthCents(t1.data, '2026-12-31') === L.netWorthCents(mk(), '2026-12-31') && L.netWorthCents(t2.data, '2026-12-31') === L.netWorthCents(mk(), '2026-12-31'));
check('transfer does not change its input', (() => { const d = mk(); const s = JSON.stringify(d); L.addTransfer(d, { fromId: 'vault', toId: 'flex', amountCents: 5, date: '2026-05-01', makeId: ids }); return JSON.stringify(d) === s; })());
const bad = (o) => L.addTransfer(mk(), Object.assign({ fromId: 'vault', toId: 'flex', amountCents: 100, date: '2026-05-01', makeId: ids }, o));
check('transfer refusals', !bad({ fromId: 'zzz' }).ok && !bad({ toId: 'vault' }).ok && !bad({ amountCents: 0 }).ok && !bad({ amountCents: -5 }).ok && !bad({ amountCents: 1.5 }).ok && !bad({ amountCents: NaN }).ok && !bad({ amountCents: 1e15 }).ok && !bad({ date: '2026-02-30' }).ok && !bad({ date: 'x' }).ok && !bad({ makeId: () => 'same' }).ok);
check('transfer to or from a closed account is refused', !L.addTransfer(mk([], [A('vault', 'bank', 'vault'), A('flex', 'bank', 'flex'), A('funds', 'savings', 'funds'), A('old', 'bank', 'none', 0, { closed: true })]), { fromId: 'vault', toId: 'old', amountCents: 5, date: '2026-05-01', makeId: ids }).ok);
check('a transfer dated in the future only counts from its date', L.balanceCents(tr('vault', 'flex', 700, '2026-09-01').data, 'flex', '2026-08-31') === 0 && L.balanceCents(tr('vault', 'flex', 700, '2026-09-01').data, 'flex', '2026-09-01') === 700);

// ---------- L2 receivable (money a friend owes you) ----------
const rec = mk([T('r1', 'brex', '2026-02-01', 50000)], [A('vault', 'bank', 'vault', 100000), A('flex', 'bank', 'flex'), A('funds', 'savings', 'funds'), A('brex', 'receivable', 'none', 100000)]);
check('receivable balance goes UP when you lend more, like a bank', L.balanceCents(rec, 'brex', '2026-12-31') === 150000);
check('receivable counts as an ASSET in net worth', L.netWorthCents(rec, '2026-12-31') === 100000 + 150000 && L.validate(rec).length === 0);
const lend = L.addTransfer(rec, { fromId: 'vault', toId: 'brex', amountCents: 20000, date: '2026-05-01', makeId: ids }).data;
check('lending from VAULT raises BREX and lowers VAULT (old code got this backwards)', L.balanceCents(lend, 'brex', '2026-12-31') === 170000 && L.balanceCents(lend, 'vault', '2026-12-31') === 80000 && L.netWorthCents(lend, '2026-12-31') === L.netWorthCents(rec, '2026-12-31'));
const back2 = L.addTransfer(lend, { fromId: 'brex', toId: 'vault', amountCents: 70000, date: '2026-06-01', makeId: ids }).data;
check('a repayment lowers BREX and raises VAULT; paid in full it can be closed', L.balanceCents(back2, 'brex', '2026-12-31') === 100000 && L.balanceCents(back2, 'vault', '2026-12-31') === 150000 && L.closeAccount(L.addTransfer(back2, { fromId: 'brex', toId: 'vault', amountCents: 100000, date: '2026-07-01', makeId: ids }).data, 'brex', '2026-12-31').ok);
check('a receivable is not a debt', !L.isDebt('receivable') && L.KINDS.includes('receivable'));

// ---------- L2 delete / close / validate ----------
const del1 = L.deleteTransaction(t1.data, t1.data.transactions[0].id, true), del2 = L.deleteTransaction(t1.data, t1.data.transactions[0].id, false);
check('deleting a transfer with both halves removes both', del1.ok && del1.data.transactions.length === 0 && del1.removed === 2);
check('deleting one half only leaves the partner (validate then complains)', del2.ok && del2.data.transactions.length === 1 && L.validate(del2.data).some(p => /partner missing/.test(p)));
check('delete of an unknown id is refused', !L.deleteTransaction(t1.data, 'nope', true).ok);
check('close refused for a special role', !L.closeAccount(mk(), 'vault', '2026-06-01').ok);
check('close refused while a balance remains', !L.closeAccount(mk(), 'car', '2026-06-01').ok);
const paid = mk([T('p', 'car', '2026-06-01', 200000)]);
const cl = L.closeAccount(paid, 'car', '2026-06-01');
check('a loan paid to exactly $0 can be closed, history kept', cl.ok && cl.data.accounts.find(a => a.id === 'car').closed === true && cl.data.transactions.length === 1 && L.balanceCents(cl.data, 'car', '2026-06-01') === 0);
check('validate: a good file has no problems', L.validate(mk()).length === 0 && L.validate(t1.data).length === 0);
check('validate catches the real mistakes', L.validate(mk([T('a', 'zzz', '2026-01-02', 5)])).length > 0 && L.validate(mk([T('a', 'vault', '2026-01-02', 5.5)])).length > 0 && L.validate(mk([T('a', 'vault', '2026-13-02', 5)])).length > 0 && L.validate(mk([T('a', 'vault', '2026-01-02', 5), T('a', 'vault', '2026-01-02', 5)])).length > 0 && L.validate(mk([], [A('vault', 'bank', 'vault'), A('flex', 'bank', 'flex')])).some(p => /funds/.test(p)) && L.validate(mk([], [A('v', 'bank', 'vault'), A('v2', 'bank', 'vault'), A('f', 'bank', 'flex'), A('u', 'savings', 'funds')])).some(p => /twice/.test(p)) && L.validate(mk([], [A('a', 'bank', 'vault', 1.5)])).length > 0 && L.validate(null).length > 0 && L.validate({}).length > 0);

// ---------- L4 sustained ----------
let big = []; for (let i = 0; i < 50000; i++) big.push(T('b' + i, i % 2 ? 'vault' : 'flex', '2026-0' + (1 + (i % 9)) + '-1' + (i % 9), (i % 7) - 3));
const t0 = Date.now(); const bd = mk(big);
const v = L.balanceCents(bd, 'vault', '2026-12-31'), f = L.balanceCents(bd, 'flex', '2026-12-31');
check('L4 50,000 entries are summed correctly and fast', v + f === 100000 + big.reduce((s, t) => s + t.amountCents, 0) && Date.now() - t0 < 2000, (Date.now() - t0) + 'ms');
check('L4 1,000 cents-additions never drift (0.01 x 1000 = $10.00 exactly)', L.balanceCents(mk(Array.from({ length: 1000 }, (_, i) => T('c' + i, 'flex', '2026-02-01', 1))), 'flex', '2026-12-31') === 1000);
let dd = mk(); for (let i = 0; i < 300; i++) dd = L.addTransfer(dd, { fromId: i % 2 ? 'flex' : 'vault', toId: 'funds', amountCents: 100 + i, date: '2026-05-01', makeId: ids }).data;
check('L4 300 transfers in a row: file stays valid and net worth never moves', L.validate(dd).length === 0 && L.netWorthCents(dd, '2026-12-31') === L.netWorthCents(mk(), '2026-12-31'));

// ---------- L5 hostile ----------
check('L5 junk rows are ignored, not crashed on', (() => { try { const d = mk([null, 5, 'x', [], { accountId: 'vault' }, T('z', 'vault', '2026-02-01', 1e400), T('y', 'vault', 'bad', 5), T('w', 'vault', '2026-02-01', '5'), T('ok', 'vault', '2026-02-01', 7)]); return L.balanceCents(d, 'vault', '2026-12-31') === 100007; } catch (e) { return false; } })());
check('L5 junk accounts are ignored', (() => { try { const d = { accounts: [null, 3, { id: 5 }, A('vault', 'bank', 'vault', 'x')], transactions: 'nope' }; return L.balanceCents(d, 'vault', '2026-01-02') === 0 && L.allBalances(d, '2026-01-02').vault === 0 && L.validate(d).length > 0; } catch (e) { return false; } })());
check('L5 null / empty data never throws', (() => { try { L.balanceCents(null, 'a', '2026-01-01'); L.netWorthCents({}, '2026-01-01'); L.allBalances(undefined, '2026-01-01'); L.addTransfer(null, {}); L.addTransfer(mk(), null); L.deleteTransaction({}, 'x'); L.closeAccount({}, 'x', 'y'); return true; } catch (e) { return false; } })());
check('L5 a hostile description is capped, not trusted', L.addTransfer(mk(), { fromId: 'vault', toId: 'flex', amountCents: 5, date: '2026-05-01', description: 'x'.repeat(1e6), makeId: ids }).data.transactions[0].description.length === 200);
check('L5 largest allowed amount stays an exact integer', Number.isSafeInteger(L.balanceCents(mk([T('m', 'vault', '2026-02-01', L.MAX_CENTS)]), 'vault', '2026-12-31')));
check('L5 default ids are unique', (() => { const s = new Set(); let d = mk(); for (let i = 0; i < 500; i++) d = L.addTransfer(d, { fromId: 'vault', toId: 'flex', amountCents: 1, date: '2026-05-01' }).data; d.transactions.forEach(t => s.add(t.id)); return s.size === 1000; })());

console.log(failed === 0 ? passed + '/' + passed + ' passed' : passed + '/' + (passed + failed) + ' passed, ' + failed + ' FAILED');
process.exit(failed === 0 ? 0 : 1);