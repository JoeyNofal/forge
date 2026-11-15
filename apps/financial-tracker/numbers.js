// numbers.js - READ-ONLY helper: opens a data file in a hidden copy of the page and prints the key money figures.
// It never saves anything (the page's save function is a stub) and never writes the file.
// Run:  node numbers.js "D:\path\to\file.json"
const fs = require('fs'), path = require('path');

async function figures(filePath) {
  const { JSDOM, VirtualConsole } = require('jsdom');
  const rd = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
  let html = rd('index.html');
  for (const f of ['dates.js', 'bills.js', 'ledger.js', 'v2view.js', 'settingscheck.js', 'paycheckrec.js']) html = html.replace('<script src="' + f + '"></script>', () => '<script>' + rd(f) + '</script>');
  html = html.replace(/<script[^>]*\bsrc=[^>]*><\/script>/g, '');
  const text = fs.readFileSync(filePath, 'utf8');
  JSON.parse(text);   // throws a clear error if the file is not JSON
  return new Promise((resolve, reject) => {
    const handlers = {};
    const api = { saveData: async () => ({ ok: true }), createNewFile: async () => ({ ok: false }), loadFile: async () => ({ ok: false, canceled: true }), importFile: async () => ({ ok: false }),
      openBackupsFolder: async () => '', getAppInfo: async () => ({}), openExternal: async () => {}, flushDone: () => Promise.resolve(),
      onInitialData: (cb) => { handlers.initial = cb; }, onLoadProblem: (cb) => { handlers.problem = cb; }, onFlushRequest: () => {} };
    const vc = new VirtualConsole();
    const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/', beforeParse(w) {
      w.electronAPI = api; w.Chart = class { constructor() {} destroy() {} update() {} }; w.Chart.register = () => {}; w.ExcelJS = {};
      w.setTimeout = () => 1; w.clearTimeout = () => {}; w.HTMLCanvasElement.prototype.getContext = () => null; } });
    setImmediate(() => {
      try {
        handlers.initial({ path: filePath, data: text });
        setImmediate(() => {
          try {
            const w = dom.window, App = w.eval('App'), Views = w.eval('Views');
            const rows = Views.forecast.generate();
            resolve({
              kind: App.v2Raw ? 'v2' : 'v1',
              groceriesAverage: App.calc.avgGroceries(),
              monthlyCosts: App.calc.monthlyExpenses(),
              weeklyFixed: App.calc.weeklyFixedExpenses(),
              flexAllowance: App.calc.flexAllowance(),
              vaultTarget: App.calc.vaultBufferTarget(),
              forecastWeek1Vault: rows[0].vault,
              forecastWeek52Vault: rows[51].vault
            });
          } catch (e) { reject(e); }
        });
      } catch (e) { reject(e); }
    });
  });
}

module.exports = { figures };

if (require.main === module) {
  const file = process.argv[2];
  if (!file) { console.log('Usage: node numbers.js "path\\to\\data-file.json"'); process.exit(2); }
  figures(file).then((f) => {
    const m = (n) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    console.log('File type: ' + f.kind + '   (read only, nothing is saved)');
    console.log('Groceries average per month ........ ' + m(f.groceriesAverage));
    console.log('Monthly costs incl. groceries ...... ' + m(f.monthlyCosts));
    console.log('Weekly fixed costs (Forecast) ...... ' + m(f.weeklyFixed));
    console.log('FLEX weekly allowance .............. ' + m(f.flexAllowance));
    console.log('VAULT target ....................... ' + m(f.vaultTarget));
    console.log('Forecast VAULT after week 1 ........ ' + m(f.forecastWeek1Vault));
    console.log('Forecast VAULT after week 52 ....... ' + m(f.forecastWeek52Vault));
    process.exit(0);
  }).catch((e) => { console.log('Could not read that file: ' + (e && e.message ? e.message : e)); process.exit(1); });
}