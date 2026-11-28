// Prova della pagina di installazione del firmware V3 (site/firmware-v3.html): logica della pagina, non il flasher (esp-web-tools e' sostituito da un componente vuoto).
//   node tests/page/run_v3.js <cartella-del-sito> [cartella-per-le-schermate]
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');

const site = path.resolve(process.argv[2] || '_site');
const shots = process.argv[3] ? path.resolve(process.argv[3]) : null;
const types = { '.html': 'text/html', '.json': 'application/json', '.bin': 'application/octet-stream' };
const ENVS = ['mobile_t3', 'mobile_tbeam1262', 'mobile_tbeam1278', 'mobile_heltec_v3', 'bench_t3', 'bench_tbeam1262', 'bench_tbeam1278', 'ble_sim_t3', 'ble_sim_tbeam1262'];
let fails = 0;
const check = (c, m) => { if (!c) { console.log('FALLITO: ' + m); fails++; } else console.log('ok: ' + m); };

(async () => {
  // il sito assemblato: ogni firmware ha le quattro parti e un manifest con gli indirizzi giusti
  for (const e of ENVS) {
    const d = path.join(site, 'firmware-v3', e);
    const m = JSON.parse(fs.readFileSync(path.join(d, 'manifest.json'), 'utf8'));
    const parts = m.builds[0].parts;
    check(parts.map(p => p.offset).join() === (e === 'mobile_heltec_v3' ? '0,32768,57344,65536' : '4096,32768,57344,65536') && m.builds[0].chipFamily === (e === 'mobile_heltec_v3' ? 'ESP32-S3' : 'ESP32') && parts.map(p => p.path).join() === 'bootloader.bin,partitions.bin,boot_app0.bin,firmware.bin', `${e}: manifest con le quattro parti agli indirizzi giusti (0x1000 o, per ESP32-S3, 0x0; poi 0x8000, 0xe000, 0x10000)`);
    check(parts.every(p => fs.existsSync(path.join(d, p.path))) && m.new_install_prompt_erase === false, `${e}: i quattro file ci sono e la scheda non si cancella`);
  }
  const server = http.createServer((req, res) => {
    const p = path.join(site, decodeURIComponent(req.url.split('?')[0]));
    if (!p.startsWith(site) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': types[path.extname(p)] || 'text/plain' });
    fs.createReadStream(p).pipe(res);
  }).listen(0);
  const port = server.address().port;
  const browser = await chromium.launch(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {});
  const stub = r => r.fulfill({ contentType: 'text/javascript', body: "customElements.define('esp-web-install-button', class extends HTMLElement {});" });
  for (const scheme of ['light', 'dark']) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 }, colorScheme: scheme });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
    await page.route('**/esp-web-tools@*/**', stub);
    await page.goto(`http://127.0.0.1:${port}/firmware-v3.html`);
    await page.waitForFunction(() => !document.getElementById('ver').textContent.includes('…'));
    check(/Versione: .* \(commit [0-9a-f]{7}\)/.test(await page.textContent('#ver')), `[${scheme}] versione mostrata`);
    check(await page.getAttribute('#installer', 'manifest') === 'firmware-v3/mobile_t3/manifest.json', `[${scheme}] manifest iniziale: mobile T3`);
    for (const e of ENVS) {
      await page.selectOption('#board', e);
      check(await page.getAttribute('#installer', 'manifest') === `firmware-v3/${e}/manifest.json` && (await page.textContent('#desc')).length > 20, `[${scheme}] ${e}: manifest e descrizione`);
    }
    check(await page.isHidden('#missing'), `[${scheme}] con il firmware pubblicato l'avviso di mancanza non compare`);
    const text = await page.textContent('body');
    check(/mai eseguito su una scheda/.test(text) && /115200/.test(text) && /BOOST ON RISCHIO/.test(text) && /IOF ON RISCHIO/.test(text) && /IZ5IOF/.test(text), `[${scheme}] la pagina dice che e' uno studio mai provato su schede, la seriale e i due livelli di potenza`);
    check(/VoLoRa-V3\.apk/.test(await page.content()) && /mai provata su un telefono/.test(text), `[${scheme}] la pagina ha il collegamento all'app Android e dice che e' uno studio`);
    check(/le impostazioni salvate nella scheda restano/.test(text), `[${scheme}] la pagina dice che le impostazioni restano`);
    check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `[${scheme}] nessuno scorrimento orizzontale a 390 px`);
    check(errors.length === 0, `[${scheme}] nessun errore in console${errors.length ? ': ' + errors.join(' | ') : ''}`);
    if (shots) { fs.mkdirSync(shots, { recursive: true }); await page.screenshot({ path: path.join(shots, `pagina-v3-${scheme}.png`), fullPage: true }); }
    await ctx.close();
  }
  // firmware non pubblicato: compare l'avviso con il comando per compilarlo
  fs.renameSync(path.join(site, 'firmware-v3/bench_t3/manifest.json'), path.join(site, 'firmware-v3/bench_t3/manifest.off'));
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.route('**/esp-web-tools@*/**', stub);
  await page.goto(`http://127.0.0.1:${port}/firmware-v3.html`);
  await page.selectOption('#board', 'bench_t3');
  await page.waitForFunction(() => !document.getElementById('missing').hidden);
  check((await page.textContent('#missing')).includes('pio run -e bench_t3 -t upload'), 'firmware mancante: avviso con il comando di PlatformIO');
  fs.renameSync(path.join(site, 'firmware-v3/bench_t3/manifest.off'), path.join(site, 'firmware-v3/bench_t3/manifest.json'));
  await browser.close();
  server.close();
  if (fails) { console.log(`${fails} prove fallite`); process.exit(1); }
  console.log('pagina firmware V3: tutte le prove passate');
})();
