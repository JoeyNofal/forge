// Run:  node datastore.test.js      (from the apps/financial-tracker folder)
const fs = require('fs'), os = require('os'), path = require('path');
const { spawn } = require('child_process');
const ds = require('./datastore.js');

let passed = 0, failed = 0;
function check(name, cond, extra) {
  if (cond) passed++; else { failed++; console.log('FAIL: ' + name + (extra ? '  -> ' + extra : '')); }
}
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ft-test-'));
let n = 0;
function fresh() { const d = path.join(root, 'c' + (n++)); fs.mkdirSync(d); return path.join(d, 'financial-tracker-data.json'); }
const good = (k) => JSON.stringify({ accounts: { vault: 1 }, transactions: Array.from({ length: k === undefined ? 3 : k }, (_, i) => ({ id: 'a' + i, amount: i })), settings: {} }, null, 2);

(async () => {
  // ---------- L1 static ----------
  const src = fs.readFileSync(path.join(__dirname, 'datastore.js'), 'utf8');
  check('L1 no hardcoded D: path', !/[A-Z]:\\\\/.test(src) && !/D:\//.test(src));
  check('L1 no secrets words', !/sk-ant|AIza|apiKey/i.test(src));
  const writeCalls = src.match(/writeFileSync|createWriteStream/g) || [];
  check('L1 never writes straight to the real file (no writeFileSync)', writeCalls.length === 0);

  // ---------- L2 smoke ----------
  check('L2 env path wins', ds.resolveDataPath({ FINANCIAL_DATA_PATH: ' X.json ' }, 'F.json') === 'X.json');
  check('L2 fallback used when env empty', ds.resolveDataPath({ FINANCIAL_DATA_PATH: '  ' }, 'F.json') === 'F.json');
  check('L2 no path at all -> null', ds.resolveDataPath({}, null) === null);
  let p = fresh();
  check('L2 missing file reported, NOT created', ds.loadData(p).status === 'missing' && !fs.existsSync(p));
  check('L2 no path -> error', ds.loadData(null).status === 'error');
  let r = ds.saveData(p, good());
  check('L2 first save ok', r.ok === true && r.backup === null);
  check('L2 load returns same data', ds.loadData(p).status === 'ok' && ds.loadData(p).data.transactions.length === 3);
  fs.writeFileSync(p, '{"transactions": [ {"id":1}, ');
  check('L2 truncated JSON -> corrupt', ds.loadData(p).status === 'corrupt');
  fs.writeFileSync(p, '[1,2,3]');
  check('L2 array -> invalid', ds.loadData(p).status === 'invalid');
  fs.writeFileSync(p, 'null');
  check('L2 null -> invalid', ds.loadData(p).status === 'invalid');
  fs.writeFileSync(p, '{"transactions": "nope"}');
  check('L2 bad transactions type -> invalid', ds.loadData(p).status === 'invalid');
  fs.writeFileSync(p, '\uFEFF' + good());
  check('L2 BOM tolerated', ds.loadData(p).status === 'ok');
  fs.writeFileSync(p, '');
  check('L2 empty file -> corrupt', ds.loadData(p).status === 'corrupt');

  // ---------- L2 save refusals ----------
  p = fresh(); ds.saveData(p, good(5));
  for (const [label, bad] of [['empty string', ''], ['whitespace', '   '], ['undefined text', 'undefined'], ['not json', '{oops'], ['array', '[]'], ['null', 'null'], ['number', '5'], [' undefined value', undefined], ['object value', {}]]) {
    const res = ds.saveData(p, bad);
    check('L2 refuses to save ' + label, res.ok === false);
  }
  check('L2 file untouched after refusals', ds.loadData(p).data.transactions.length === 5);
  r = ds.saveData(p, JSON.stringify({ accounts: {}, transactions: [], settings: {} }));
  check('L2 wipe guard blocks erasing all transactions', r.ok === false && /erase all 5/.test(r.error));
  check('L2 data still intact after wipe attempt', ds.loadData(p).data.transactions.length === 5);
  r = ds.saveData(p, JSON.stringify({ transactions: [], settings: {} }), { allowWipe: true });
  check('L2 wipe allowed only when explicitly asked', r.ok === true);
  p = fresh();
  r = ds.saveData(p, JSON.stringify({ accounts: {}, transactions: [] }));
  check('L2 empty-to-empty save is fine', r.ok === true);

  // ---------- L2 backups ----------
  p = fresh(); ds.saveData(p, good(2));
  r = ds.saveData(p, good(3), { minIntervalMs: 0 });
  const bdir = path.join(path.dirname(p), 'backups');
  check('L2 second save makes a backup', r.ok && r.backup && fs.existsSync(r.backup));
  check('L2 backup holds the OLD content', JSON.parse(fs.readFileSync(r.backup, 'utf8')).transactions.length === 2);
  check('L2 backup name sorted/dated', /financial-tracker-data\.\d{4}-\d{2}-\d{2}_\d{9}\.json$/.test(r.backup));
  const r2 = ds.saveData(p, good(4), { minIntervalMs: 600000 });
  check('L2 no second backup inside the time gap', r2.ok && r2.backup === null);

  // ---------- L2 corrupt original is rescued ----------
  p = fresh(); fs.writeFileSync(p, '{broken');
  r = ds.saveData(p, good(1));
  const rescued = fs.readdirSync(path.dirname(p)).filter(f => f.includes('.unreadable-'));
  check('L2 corrupt original kept as .unreadable copy before overwrite', r.ok && rescued.length === 1 && fs.readFileSync(path.join(path.dirname(p), rescued[0]), 'utf8') === '{broken');

  // ---------- L4 sustained ----------
  p = fresh(); ds.saveData(p, good(1));
  let ok200 = 0;
  for (let i = 0; i < 200; i++) { if (ds.saveData(p, good(i + 1), { minIntervalMs: 0, keep: 10 }).ok) ok200++; }
  check('L4 200 rapid saves all ok', ok200 === 200);
  check('L4 final file valid and latest', ds.loadData(p).status === 'ok' && ds.loadData(p).data.transactions.length === 200);
  check('L4 backups capped at 10', ds.listBackups(path.join(path.dirname(p), 'backups'), 'financial-tracker-data').length === 10);
  check('L4 no leftover .tmp file', !fs.existsSync(p + '.tmp'));

  // ---------- L4 a second process reads while we write (like ASSET) ----------
  p = fresh(); ds.saveData(p, good(50));
  const readerCode = `const fs=require('fs');let bad=0,reads=0;const t=Date.now();while(Date.now()-t<2500){try{const x=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));if(!Array.isArray(x.transactions))bad++;}catch(e){if(e.code!=='ENOENT')bad++;}reads++;}console.log(JSON.stringify({bad,reads}));`;
  const child = spawn(process.execPath, ['-e', readerCode, p]);
  let out = ''; child.stdout.on('data', d => out += d);
  const done = new Promise(res => child.on('close', res));
  const t0 = Date.now(); let writes = 0;
  while (Date.now() - t0 < 2300) { ds.saveData(p, good(50 + (writes % 40)), { minIntervalMs: 600000 }); writes++; }
  await done;
  const rd = JSON.parse(out);
  check('L4 reader process never saw a half-written file', rd.bad === 0, JSON.stringify(rd));
  check('L4 test really did overlap (many reads and writes)', rd.reads > 100 && writes > 50, 'reads ' + rd.reads + ' writes ' + writes);

  // ---------- L5 extreme ----------
  p = fresh();
  const big = { accounts: {}, transactions: Array.from({ length: 60000 }, (_, i) => ({ id: 'x' + i, description: 'e'.repeat(60), amount: i / 7 })), settings: {} };
  const t1 = Date.now(); r = ds.saveData(p, JSON.stringify(big)); const l = ds.loadData(p);
  check('L5 60,000-transaction file saves and loads fast', r.ok && l.status === 'ok' && l.data.transactions.length === 60000 && Date.now() - t1 < 4000, (Date.now() - t1) + 'ms');
  p = fresh();
  const uni = { transactions: [{ description: 'Café ☕ 日本語 \u0000 \u{1F4B8}', amount: 1 }], settings: {} };
  ds.saveData(p, JSON.stringify(uni));
  check('L5 unicode survives round trip', ds.loadData(p).data.transactions[0].description === uni.transactions[0].description);
  p = fresh(); ds.saveData(p, good(3));
  fs.writeFileSync(p + '.tmp', '{"transactions":[{"id":"half'); // simulated crash mid-write of a previous run
  check('L5 leftover half-written .tmp does not affect the real file', ds.loadData(p).status === 'ok' && ds.loadData(p).data.transactions.length === 3);
  r = ds.saveData(p, good(4));
  check('L5 next save replaces the stale .tmp cleanly', r.ok && ds.loadData(p).data.transactions.length === 4 && !fs.existsSync(p + '.tmp'));
  const deep = path.join(root, 'a', 'b', 'c', 'financial-tracker-data.json');
  check('L5 creates missing folders on first save', ds.saveData(deep, good(1)).ok && ds.loadData(deep).status === 'ok');
  p = fresh();
  r = ds.saveData(p, '{"transactions": [], "x": ' + '['.repeat(100000) + ']'.repeat(100000) + '}');
  check('L5 absurdly deep JSON: no crash, and the file stays readable afterwards', typeof r.ok === 'boolean' && (r.ok === false || ds.loadData(p).status === 'ok'));
  p = fresh(); fs.mkdirSync(p); // the "file" is actually a folder
  check('L5 path is a folder -> error status, no crash', ['error', 'corrupt'].includes(ds.loadData(p).status));
  check('L5 saving onto a folder fails cleanly', ds.saveData(p, good(1)).ok === false);

  console.log(failed === 0 ? passed + '/' + passed + ' passed' : passed + '/' + (passed + failed) + ' passed, ' + failed + ' FAILED');
  fs.rmSync(root, { recursive: true, force: true });
  process.exit(failed === 0 ? 0 : 1);
})();