// Run:  node session.test.js      (from the apps/financial-tracker folder)
const fs = require('fs'), os = require('os'), path = require('path');
const { parseDotEnv, readDotEnvValue, pickDataPath, DataSession } = require('./session.js');
const ds = require('./datastore.js');

let passed = 0, failed = 0;
function check(name, cond, extra) { if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); } }
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ft-sess-'));
let n = 0;
function fresh(name) { const d = path.join(root, 's' + (n++)); fs.mkdirSync(d); return path.join(d, name || 'financial-tracker-data.json'); }
const good = (k) => JSON.stringify({ accounts: { vault: 1 }, transactions: Array.from({ length: k === undefined ? 3 : k }, (_, i) => ({ id: 'a' + i, amount: i })), settings: {} });
const read = (p) => fs.readFileSync(p, 'utf8');

// ---------- L1 static ----------
const src = fs.readFileSync(path.join(__dirname, 'session.js'), 'utf8');
check('L1 no direct file writes in session.js', !/writeFileSync|createWriteStream|appendFile|renameSync|unlinkSync|rmSync/.test(src));
check('L1 no hardcoded drive paths', !/[A-Z]:\\\\/.test(src) && !/D:\//.test(src));
check('L1 no secrets words', !/sk-ant|AIza|apiKey/i.test(src));
check('L1 only datastore + fs required', (src.match(/require\(/g) || []).length === 2);

// ---------- L2 parseDotEnv ----------
const e1 = parseDotEnv('FINANCIAL_DATA_PATH=D:\\Projects\\data\\f.json\r\nOTHER=1\r\n');
check('L2 plain value, CRLF, backslashes kept', e1.FINANCIAL_DATA_PATH === 'D:\\Projects\\data\\f.json' && e1.OTHER === '1');
check('L2 double quotes stripped, backslash-n stays literal', parseDotEnv('P="D:\\new\\t.json"').P === 'D:\\new\\t.json');
check('L2 single quotes', parseDotEnv("P='a b.json'").P === 'a b.json');
check('L2 spaces around =', parseDotEnv('  P =  x.json  ').P === 'x.json');
check('L2 comments and blank lines ignored', Object.keys(parseDotEnv('# hi\n\n  # x=1\nA=2')).join() === 'A');
check('L2 export prefix', parseDotEnv('export A=2').A === '2');
check('L2 inline comment removed for unquoted', parseDotEnv('A=file.json # note').A === 'file.json');
check('L2 hash inside path kept (no space before #)', parseDotEnv('A=D:/a#b/f.json').A === 'D:/a#b/f.json');
check('L2 = inside value kept', parseDotEnv('A=x=y').A === 'x=y');
check('L2 last duplicate wins', parseDotEnv('A=1\nA=2').A === '2');
check('L2 BOM tolerated', parseDotEnv('\uFEFFA=1').A === '1');
check('L2 empty value is ""', parseDotEnv('A=').A === '');
check('L2 junk lines ignored', Object.keys(parseDotEnv('nonsense\n=novalue\n1BAD=2\nA B=3')).length === 0);
check('L2 non-string input safe', JSON.stringify(parseDotEnv(null)) === '{}' && JSON.stringify(parseDotEnv(undefined)) === '{}' && JSON.stringify(parseDotEnv(5)) === '{}');
let envf = fresh('.env'); fs.writeFileSync(envf, 'FINANCIAL_DATA_PATH=C:/x/f.json\n');
check('L2 readDotEnvValue reads a file', readDotEnvValue(envf, 'FINANCIAL_DATA_PATH') === 'C:/x/f.json');
check('L2 readDotEnvValue: missing file -> null', readDotEnvValue(path.join(root, 'nope', '.env'), 'A') === null);
check('L2 readDotEnvValue: missing key -> null', readDotEnvValue(envf, 'NOPE') === null);
check('L2 readDotEnvValue: empty value -> null', (fs.writeFileSync(envf, 'A=\n'), readDotEnvValue(envf, 'A')) === null);
check('L2 .env beats a stale system variable (Lesson #12)', pickDataPath('C:/right.json', { FINANCIAL_DATA_PATH: 'C:/stale.json' }, 'C:/fb.json') === 'C:/right.json');
check('L2 system variable used when .env has none', pickDataPath(null, { FINANCIAL_DATA_PATH: 'C:/sys.json' }, 'C:/fb.json') === 'C:/sys.json');
check('L2 fallback last', pickDataPath(null, {}, 'C:/fb.json') === 'C:/fb.json');
check('L2 blank .env value ignored', pickDataPath('   ', {}, 'C:/fb.json') === 'C:/fb.json');

// ---------- L2 DataSession ----------
let p = fresh(); fs.writeFileSync(p, good(4));
let s = new DataSession(p, { minIntervalMs: 0 });
check('L2 before open nothing can be saved', s.save(good(1)).ok === false && read(p) === good(4));
let r = s.open();
check('L2 open ok -> ready + saveAllowed', r.status === 'ok' && s.info().state === 'ready' && s.info().saveAllowed === true);
check('L2 save works and persists', s.save(good(5)).ok === true && ds.loadData(p).data.transactions.length === 5);

p = fresh(); s = new DataSession(p);
r = s.open();
check('L2 missing -> state missing, saving off', r.status === 'missing' && s.info().state === 'missing' && !s.info().saveAllowed);
check('L2 missing: save refused and nothing created', s.save(good(1)).ok === false && !fs.existsSync(p));
r = s.createNew(good(0));
check('L2 createNew from missing works, then saving is on', r.ok === true && s.info().saveAllowed && s.save(good(2)).ok === true);
check('L2 createNew refused when not missing', new DataSession(p).createNew(good(0)).ok === false);
const sNo = new DataSession(p); sNo.open();
check('L2 createNew refused on a ready session', sNo.createNew(good(0)).ok === false);

for (const [label, content, status] of [['truncated JSON', '{"transactions": [ {"id":1}, ', 'corrupt'], ['empty file', '', 'corrupt'], ['array', '[1]', 'invalid'], ['bad transactions', '{"transactions":"x"}', 'invalid']]) {
  p = fresh(); fs.writeFileSync(p, content); s = new DataSession(p);
  s.open();
  check('L2 ' + label + ' -> ' + status + ', saving off', s.info().state === status && !s.info().saveAllowed);
  check('L2 ' + label + ': save refused, original file byte-identical', s.save(good(9)).ok === false && read(p) === content);
  check('L2 ' + label + ': createNew refused', s.createNew(good(0)).ok === false && read(p) === content);
}

// ---------- L2 switching files ----------
const pA = fresh(); fs.writeFileSync(pA, good(2)); const pB = fresh(); fs.writeFileSync(pB, good(7)); const pBad = fresh(); fs.writeFileSync(pBad, '{bad');
s = new DataSession(pA); s.open();
r = s.openOther(pBad);
check('L2 openOther with a corrupt file: refused, old session intact', r.status === 'corrupt' && s.info().path === pA && s.info().saveAllowed && s.save(good(3)).ok === true);
r = s.openOther(pB);
check('L2 openOther good file switches and saves go there', r.status === 'ok' && s.info().path === pB && s.save(good(8)).ok === true && ds.loadData(pB).data.transactions.length === 8 && ds.loadData(pA).data.transactions.length === 3);
for (const bad of [null, undefined, '', 5, {}]) check('L2 openOther(' + JSON.stringify(bad) + ') refused, no crash', s.openOther(bad).status === 'error' && s.info().path === pB);
s = new DataSession(pBad); s.open();
check('L2 problem session recovers by opening a good file', s.openOther(pA).status === 'ok' && s.info().saveAllowed && s.info().state === 'ready');

// ---------- L4 sustained ----------
p = fresh(); fs.writeFileSync(p, good(1)); s = new DataSession(p, { minIntervalMs: 0, keep: 5 }); s.open();
let ok = 0; for (let i = 0; i < 300; i++) { if (s.save(good(i + 1)).ok) ok++; }
check('L4 300 saves through a session all ok', ok === 300 && ds.loadData(p).data.transactions.length === 300);
check('L4 backups capped', ds.listBackups(path.join(path.dirname(p), 'backups'), 'financial-tracker-data').length === 5);
let refused = 0; const pc = fresh(); fs.writeFileSync(pc, '{x'); const sc = new DataSession(pc); sc.open();
for (let i = 0; i < 300; i++) { if (!sc.save(good(i + 1)).ok) refused++; }
check('L4 300 saves on a corrupt-file session all refused, file untouched', refused === 300 && read(pc) === '{x');
// open/save interleaving on one file, many sessions
p = fresh(); fs.writeFileSync(p, good(10)); let allGood = true;
for (let i = 0; i < 100; i++) { const x = new DataSession(p, { minIntervalMs: 600000 }); x.open(); if (!x.save(good(10 + (i % 5))).ok) allGood = false; }
check('L4 100 open+save cycles stay consistent', allGood && ds.loadData(p).status === 'ok');

// ---------- L5 extreme ----------
s = new DataSession(null); r = s.open();
check('L5 no path -> error state, saving off, no crash', r.status === 'error' && !s.info().saveAllowed && s.save(good(1)).ok === false);
const weird = path.join(root, 'w w', 'Café ☕', 'data file.json'); fs.mkdirSync(path.dirname(weird), { recursive: true }); fs.writeFileSync(weird, good(2));
s = new DataSession(weird); s.open();
check('L5 spaces and unicode in the path work', s.info().saveAllowed && s.save(good(3)).ok && ds.loadData(weird).data.transactions.length === 3);
p = fresh(); fs.writeFileSync(p, good(2)); s = new DataSession(p); s.open();
for (const bad of [undefined, null, '', '   ', 'undefined', '[]', 'null', {}, 5]) check('L5 save(' + JSON.stringify(bad) + ') refused without throwing', s.save(bad).ok === false);
check('L5 data intact after all the bad saves', ds.loadData(p).data.transactions.length === 2);
s.open(); s.open();
check('L5 opening twice is harmless', s.info().state === 'ready');
fs.writeFileSync(p, '{broken-by-someone-else');
r = s.save(good(6));
check('L5 file broken after a good open: the unreadable original is kept, data restored', r.ok === true && ds.loadData(p).data.transactions.length === 6 && fs.readdirSync(path.dirname(p)).some(f => f.includes('.unreadable-')));
p = fresh(); fs.mkdirSync(p); s = new DataSession(p); s.open();
check('L5 path is a folder: not saveable, no crash', !s.info().saveAllowed && s.save(good(1)).ok === false);
const hugeEnv = 'A=' + 'x'.repeat(200000) + '\n'.repeat(50000);
check('L5 huge .env parses without trouble', parseDotEnv(hugeEnv).A.length === 200000);
check('L5 100,000 junk lines in .env parse fast', (() => { const t = Date.now(); parseDotEnv('junk\n'.repeat(100000)); return Date.now() - t < 2000; })());

console.log(failed === 0 ? passed + '/' + passed + ' passed' : passed + '/' + (passed + failed) + ' passed, ' + failed + ' FAILED');
fs.rmSync(root, { recursive: true, force: true });
process.exit(failed === 0 ? 0 : 1);