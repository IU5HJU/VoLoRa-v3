// Prova del Web Bluetooth dell'app Android (app/src/ble-shim.js) con la pagina del telefono vera e un BleClient finto sopra la scheda finta di mock_board.js.
// Come nell'app: la pagina e' quella del sito con lo strato inserito prima dei suoi script (app/scripts/build-www.js fa lo stesso).
//   node tests/page/run_app_shim.js <cartella-del-sito>
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');
const MOCK = require('./mock_board.js');
const site = path.resolve(process.argv[2] || '_site');
const shim = fs.readFileSync(path.resolve(__dirname, '../../app/src/ble-shim.js'), 'utf8');
let fails = 0;
const check = (c, m) => { if (!c) { console.log('FALLITO: ' + m); fails++; } else console.log('ok: ' + m); };

(async () => {
  const server = http.createServer((req, res) => {
    const p = path.join(site, decodeURIComponent(req.url.split('?')[0]));
    if (!p.startsWith(site) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': p.endsWith('.js') ? 'text/javascript' : 'text/html' }); fs.createReadStream(p).pipe(res);
  }).listen(0);
  const port = server.address().port;
  const browser = await chromium.launch(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {});
  const ctx = await browser.newContext({ viewport: { width: 390, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.addInitScript(MOCK);
  // niente navigator.bluetooth di Chrome: lo mette lo strato, come nel WebView di Android
  await page.addInitScript("Object.defineProperty(navigator, 'bluetooth', { value: undefined, configurable: true });");
  await page.addInitScript(shim);
  await page.addInitScript('window.VolShim.installShim(window.__board.makeBleClient(), window); window.__keepAwakeCalls = []; window.__keepAwake = async on => window.__keepAwakeCalls.push(on);');
  await page.goto(`http://127.0.0.1:${port}/telefono.html?modo=ble`);
  check(await page.evaluate(() => !!navigator.bluetooth && typeof navigator.bluetooth.requestDevice === 'function'), 'lo strato mette navigator.bluetooth nella pagina');
  check(await page.isHidden('#nobt'), 'nessun avviso "il browser non supporta il Bluetooth"');
  check(await page.isEnabled('#connetti'), 'il pulsante "Collega la scheda" e\' attivo');
  await page.click('#connetti');
  await page.waitForFunction(() => window.__tel.connected);
  const calls = await page.evaluate(() => window.__board.bleCalls);
  check(calls.some(c => c[0] === 'initialize' && c[1].androidNeverForLocation === true), 'il plugin e\' inizializzato (Bluetooth senza chiedere la posizione)');
  check(calls.some(c => c[0] === 'requestDevice' && c[1].services.length === 1 && c[1].services[0] === 'c49a1433-9f1b-4af8-9826-951953e47edb'), 'il selettore cerca il servizio VoLoRa V3');
  check(calls.some(c => c[0] === 'createBond'), 'l\'accoppiamento (codice a 6 cifre) si chiede subito dopo il collegamento');
  await page.waitForFunction(() => !document.getElementById('info').hidden);
  check((await page.textContent('#info')).includes('IU5HJU'), 'INFO dalla scheda: nominativo (notifiche arrivano alla pagina)');
  await page.fill('#loc', 'JN53ab'); await page.click('#usaloc');
  await page.fill('#dest', 'IZ5FSN'); await page.fill('#testo', 'Prova dall\'app');
  await page.waitForFunction(() => !document.getElementById('invia').disabled);
  await page.click('#invia');
  await page.waitForFunction(() => window.__board.done.length === 1, null, { timeout: 15000 });
  const d = await page.evaluate(() => { const x = window.__board.done[0]; return { text: new TextDecoder().decode(new Uint8Array(x.data)), crcOk: x.crcOk }; });
  check(d.text === 'Prova dall\'app' && d.crcOk, 'testo identico e CRC giusto attraverso lo strato');
  await page.click('#t_file');
  const big = Buffer.alloc(3500); for (let i = 0; i < big.length; i++) big[i] = (i * 5 + 1) & 255;
  await page.setInputFiles('#file', { name: 'dati.bin', mimeType: 'application/octet-stream', buffer: big });
  await page.waitForFunction(() => !document.getElementById('invia').disabled);
  await page.click('#invia');
  await page.waitForFunction(() => window.__board.done.length === 2, null, { timeout: 20000 });
  check(await page.evaluate(() => window.__board.done[1].crcOk && window.__board.done[1].data.length === 3500), 'file da 3500 byte (quattro blocchi) identico');
  const wr = await page.evaluate(() => ({ max: window.__board.maxWrite, calls: window.__board.bleCalls.map(c => c[0]) }));
  check(wr.calls.includes('getMtu') && wr.calls.includes('priority'), 'si legge l\'MTU e si chiede la priorita\' alta del collegamento');
  check(wr.max > 0 && wr.max <= 182, 'nessun pacchetto oltre MTU-3 = 182 byte (il piu\' lungo: ' + wr.max + ')');
  const ka = await page.evaluate(() => window.__keepAwakeCalls);
  check(ka.includes(true) && ka[ka.length - 1] === false, 'lo schermo resta acceso durante l\'invio e si libera alla fine (' + JSON.stringify(ka) + ')');
  // ricezione dalla radio
  await page.evaluate(() => window.__board.radioReceive(77, 0, new TextEncoder().encode('ciao dalla radio'), 'IZ5FSN'));
  await page.waitForFunction(() => /ciao dalla radio/.test(document.getElementById('ricevuti').textContent), null, { timeout: 5000 });
  check(true, 'oggetto ricevuto dalla radio (data_out) mostrato dalla pagina');
  // il collegamento cade: la pagina si ricollega da sola
  await page.evaluate(() => window.__board.drop());
  await page.waitForFunction(() => window.__tel.connected === false || window.__board.bleCalls.filter(c => c[0] === 'connect').length >= 2, null, { timeout: 5000 });
  await page.waitForFunction(() => window.__tel.connected && window.__board.bleCalls.filter(c => c[0] === 'connect').length >= 2, null, { timeout: 15000 });
  check(true, 'caduto il collegamento, la pagina si ricollega da sola');
  check(errors.length === 0, 'nessun errore nella pagina' + (errors.length ? ': ' + errors.join(' | ') : ''));
  await browser.close();
  server.close();
  if (fails) { console.log(`${fails} prove fallite`); process.exit(1); }
  console.log('app Android (strato Web Bluetooth): tutte le prove passate');
})();
