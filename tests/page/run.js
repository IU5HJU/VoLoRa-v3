// Prova della pagina di installazione (site/index.html): logica della pagina, non il flasher.
// Il componente esp-web-tools viene da una CDN: qui la richiesta e' sostituita da un componente vuoto, quindi NON si prova la scrittura sulla scheda.
//   node tests/page/run.js <cartella-del-sito> [cartella-per-le-schermate]
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');

const site = path.resolve(process.argv[2] || '_site');
const shots = process.argv[3] ? path.resolve(process.argv[3]) : null;
const types = { '.html': 'text/html', '.json': 'application/json', '.bin': 'application/octet-stream' };
let fails = 0;
const check = (c, m) => { if (!c) { console.log('FALLITO: ' + m); fails++; } else console.log('ok: ' + m); };

(async () => {
  const server = http.createServer((req, res) => {
    const p = path.join(site, decodeURIComponent(req.url.split('?')[0]));
    if (!p.startsWith(site) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': types[path.extname(p)] || 'text/plain' });
    fs.createReadStream(p).pipe(res);
  }).listen(0);
  const port = server.address().port;
  const browser = await chromium.launch(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {});
  for (const scheme of ['light', 'dark']) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 }, colorScheme: scheme });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
    await page.route('**/esp-web-tools@*/**', r => r.fulfill({ contentType: 'text/javascript', body: "customElements.define('esp-web-install-button', class extends HTMLElement {});" }));
    await page.goto(`http://127.0.0.1:${port}/index.html`);
    await page.waitForFunction(() => document.getElementById('ver').textContent.startsWith('Versione: ') && !document.getElementById('ver').textContent.includes('…'));
    const ver = await page.textContent('#ver');
    check(/Versione: .* \(commit [0-9a-f]{7}\)/.test(ver), `[${scheme}] versione mostrata: ${ver}`);
    check(await page.getAttribute('#installer', 'manifest') === 'firmware/t3/manifest.json', `[${scheme}] manifest iniziale: T3`);
    await page.selectOption('#board', 'tbeam1262');
    check(await page.getAttribute('#installer', 'manifest') === 'firmware/tbeam1262/manifest.json', `[${scheme}] cambio scheda cambia il manifest`);
    await page.waitForTimeout(300);
    check(await page.isHidden('#missing'), `[${scheme}] nessun avviso se il firmware c'e`);
    const noScroll = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    check(noScroll, `[${scheme}] nessuno scorrimento orizzontale a 390 px`);
    check(errors.length === 0, `[${scheme}] nessun errore in console${errors.length ? ': ' + errors.join(' | ') : ''}`);
    if (shots) { fs.mkdirSync(shots, { recursive: true }); await page.screenshot({ path: path.join(shots, `pagina-${scheme}.png`), fullPage: true }); }
    await ctx.close();
  }
  // firmware non pubblicato per una scheda: compare l'avviso
  fs.renameSync(path.join(site, 'firmware/tbeam1262/manifest.json'), path.join(site, 'firmware/tbeam1262/manifest.off'));
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.route('**/esp-web-tools@*/**', r => r.fulfill({ contentType: 'text/javascript', body: "customElements.define('esp-web-install-button', class extends HTMLElement {});" }));
  await page.goto(`http://127.0.0.1:${port}/index.html`);
  await page.selectOption('#board', 'tbeam1262');
  await page.waitForFunction(() => !document.getElementById('missing').hidden);
  check(true, 'firmware mancante: compare l\'avviso');
  fs.renameSync(path.join(site, 'firmware/tbeam1262/manifest.off'), path.join(site, 'firmware/tbeam1262/manifest.json'));
  await browser.close();
  server.close();
  if (fails) { console.log(`${fails} prove fallite`); process.exit(1); }
  console.log('pagina: tutte le prove passate');
})();
