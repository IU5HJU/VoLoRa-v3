// Prova della pagina del telefono SERVITA DALLA SCHEDA: collegamento via WebSocket (Wi-Fi della scheda) con la scheda finta di mock_board.js.
//   node tests/page/run_telefono_ws.js <cartella-del-sito>
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');
const MOCK = require('./mock_board.js');
const site = path.resolve(process.argv[2] || '_site');
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
  for (const scheme of ['light', 'dark']) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 900 }, colorScheme: scheme });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    await page.addInitScript(MOCK);
    await page.addInitScript('window.__board.installWs();');
    // niente Web Bluetooth: la pagina della scheda non ne ha bisogno
    await page.addInitScript("Object.defineProperty(navigator, 'bluetooth', { value: undefined, configurable: true });");
    await page.goto(`http://127.0.0.1:${port}/telefono.html?modo=ws`);
    await page.waitForFunction(() => window.__tel && window.__tel.connected);
    check(true, `[${scheme}] la pagina si collega da sola alla scheda via WebSocket`);
    check(await page.evaluate(() => window.__board.wsUrl) === `ws://127.0.0.1:${port}/ws`, `[${scheme}] indirizzo del WebSocket: stesso host della pagina, /ws`);
    check(await page.isHidden('#nobt'), `[${scheme}] nessun avviso sul Web Bluetooth in modo Wi-Fi`);
    check((await page.textContent('#modo')).includes('Wi-Fi della scheda'), `[${scheme}] la pagina dice come e' collegata`);
    await page.waitForFunction(() => !document.getElementById('info').hidden);
    check((await page.textContent('#info')).includes('IU5HJU'), `[${scheme}] INFO dalla scheda: nominativo`);
    check(await page.isVisible('#regbtn'), `[${scheme}] il pulsante del registro della scheda c'e'`);
    // posizione e testo
    await page.fill('#loc', 'JN53ab'); await page.click('#usaloc');
    await page.fill('#dest', 'IZ5FSN'); await page.fill('#testo', 'Prova via Wi-Fi della scheda');
    await page.waitForFunction(() => !document.getElementById('invia').disabled);
    await page.click('#invia');
    await page.waitForFunction(() => window.__board.done.length === 1, null, { timeout: 15000 });
    const d = await page.evaluate(() => { const x = window.__board.done[0]; return { text: new TextDecoder().decode(new Uint8Array(x.data)), crcOk: x.crcOk, dest: x.dest, pos: x.pos }; });
    check(d.text === 'Prova via Wi-Fi della scheda' && d.crcOk && d.dest === 'IZ5FSN', `[${scheme}] testo identico, destinatario e CRC giusti via WebSocket`);
    check(JSON.stringify(d.pos) === JSON.stringify([0, 74, 78, 53, 51, 97, 98]), `[${scheme}] la posizione (locatore) arriva alla scheda`);
    await page.waitForFunction(() => /Consegnato/.test(document.getElementById('inviomsg').textContent));
    check(true, `[${scheme}] la pagina dice "Consegnato in radio"`);
    // file di piu' blocchi
    await page.click('#t_file');
    const big = Buffer.alloc(3500); for (let i = 0; i < big.length; i++) big[i] = (i * 7 + 3) & 255;
    await page.setInputFiles('#file', { name: 'dati.bin', mimeType: 'application/octet-stream', buffer: big });
    await page.waitForFunction(() => !document.getElementById('invia').disabled);
    await page.click('#invia');
    await page.waitForFunction(() => window.__board.done.length === 2, null, { timeout: 20000 });
    const f = await page.evaluate(() => { const x = window.__board.done[1]; return { crcOk: x.crcOk, n: x.data.length, name: x.name }; });
    check(f.crcOk && f.n === 3500 && f.name === 'dati.bin', `[${scheme}] file da 3500 byte (4 blocchi) identico via WebSocket`);
    // la scheda dice perche' un invio e' fallito (E_DIAG): la pagina lo mostra
    await page.click('#t_testo'); await page.fill('#testo', 'secondo');
    await page.waitForFunction(() => !document.getElementById('invia').disabled);
    await page.evaluate(() => { window.__board.noPosition = false; });
    await page.click('#invia');
    await page.waitForFunction(() => window.__tel.tx && window.__tel.tx.state === 'sending' || window.__board.done.length === 3);
    await page.waitForFunction(() => window.__board.done.length === 3);
    await page.evaluate(() => {
      const t = window.__tel.tx, b = window.__board;
      b.ev(0x8A, b.be(t.obj, 2), 3, 0, b.be(0, 3), 10, 0, b.be(75, 2));      // E_DIAG: motivo 3 (offerta)
      b.ev(0x86, b.be(t.obj, 2), 1);                                         // E_DONE: fallito
    });
    await page.waitForFunction(() => /offerta non accettata/.test(document.getElementById('inviomsg').textContent));
    check(true, `[${scheme}] E_DIAG: la pagina spiega il motivo del fallimento`);
    // il collegamento cade e si riprende da solo
    await page.evaluate(() => { window.__board.drop(); });
    await page.waitForFunction(() => window.__tel.connected === false || window.__board.wsOpen >= 2, null, { timeout: 5000 });
    await page.waitForFunction(() => window.__tel.connected && window.__board.wsOpen >= 2, null, { timeout: 15000 });
    check(true, `[${scheme}] caduto il collegamento, la pagina si ricollega da sola`);
    check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `[${scheme}] nessuno scorrimento orizzontale a 390 px`);
    check(errors.length === 0, `[${scheme}] nessun errore nella pagina${errors.length ? ': ' + errors.join(' | ') : ''}`);
    await ctx.close();
  }
  await browser.close();
  server.close();
  if (fails) { console.log(`${fails} prove fallite`); process.exit(1); }
  console.log('pagina del telefono dalla scheda (WebSocket): tutte le prove passate');
})();
