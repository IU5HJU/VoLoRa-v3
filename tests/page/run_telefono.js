// Prova della pagina del telefono (site/telefono.html) con una SCHEDA FINTA che parla il protocollo di docs/ble-telefono.md (Web Bluetooth simulato).
//   node tests/page/run_telefono.js <cartella-del-sito>
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');
const site = path.resolve(process.argv[2] || '_site');
let fails = 0;
const check = (c, m) => { if (!c) { console.log('FALLITO: ' + m); fails++; } else console.log('ok: ' + m); };

// La scheda finta: un modello in JavaScript del ponte BleBridge (tools/ble_bridge.py), con Web Bluetooth simulato.
const MOCK = require('./mock_board.js');

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
    await page.goto(`http://127.0.0.1:${port}/telefono.html`);
    const B = () => page.evaluate(() => { const b = window.__board; return { pos: b.pos, done: b.done.map(d => ({ ...d, data: Array.from(d.data) })), writes: b.writes, maxWrite: b.maxWrite, resumed: b.resumed, log: b.log, requestCount: b.requestCount, filters: b.filters, rxAck: b.rxAck }; });
    const wait = (cond, ms = 6000) => page.waitForFunction(cond, null, { timeout: ms }).then(() => true, () => false);
    check(await page.isHidden('#nobt') && await page.isDisabled('#invia'), `[${scheme}] con il Bluetooth disponibile: nessun avviso, Invia spento`);

    // collegamento e INFO
    await page.click('#connetti');
    check(await wait(() => window.__tel.info && window.__tel.info.chip === 'SX1278'), `[${scheme}] collegata: la scheda risponde con INFO`);
    let b = await B();
    check(b.filters && b.filters.filters[0].services[0] === 'c49a1433-9f1b-4af8-9826-951953e47edb', `[${scheme}] la pagina cerca il servizio con l'UUID della specifica`);
    check((await page.textContent('#info')).includes('IU5HJU') && (await page.textContent('#info')).includes('posizione non nota'), `[${scheme}] la pagina mostra chip, nominativo e che manca la posizione`);

    // senza posizione: la pagina non parte
    await page.fill('#testo', 'Ciao dal telefono, qui IU5HJU');
    await page.click('#invia');
    check((await page.textContent('#inviomsg')).includes('posizione'), `[${scheme}] senza posizione la pagina non invia e lo dice`);
    // locatore non valido e valido
    await page.fill('#loc', 'ZZ99'); await page.click('#usaloc');
    check((await page.textContent('#pos')).includes('non valido'), `[${scheme}] locatore non valido: errore`);
    await page.fill('#loc', 'jn53ab'); await page.click('#usaloc');
    check(await wait(() => window.__board.pos) && (await page.textContent('#pos')).includes('JN53ab'), `[${scheme}] locatore valido: portato in JN53ab e mandato alla scheda`);
    b = await page.evaluate(() => window.__board.posBytes);
    check(b[0] === 0 && String.fromCharCode(...b.slice(1)) === 'JN53ab' && b.length === 7, `[${scheme}] posizione di 7 byte: tipo 0 e locatore ASCII`);

    // testo
    await page.fill('#dest', 'ik5xyz');
    await page.click('#invia');
    check(await wait(() => window.__board.done.length === 1), `[${scheme}] testo consegnato in radio dalla scheda finta`);
    b = await B();
    const d0 = b.done[0];
    check(d0.crcOk && Buffer.from(d0.data).toString() === 'Ciao dal telefono, qui IU5HJU' && d0.dest === 'IK5XYZ' && d0.kind === 0, `[${scheme}] testo identico, destinatario IK5XYZ, CRC giusto`);
    check((await page.textContent('#inviomsg')).includes('Consegnato'), `[${scheme}] la pagina dice "Consegnato in radio"`);

    // file piu' grande di un blocco: tre blocchi richiesti a richiesta
    const big = Buffer.alloc(5000); for (let i = 0; i < big.length; i++) big[i] = (i * 31 + 7) & 255;
    await page.click('#t_file');
    await page.setInputFiles('#file', { name: 'dati.bin', mimeType: 'application/octet-stream', buffer: big });
    await page.waitForFunction(() => window.__tel.payload && window.__tel.payload.kind === 1);
    await page.click('#invia');
    check(await wait(() => window.__board.done.length === 2), `[${scheme}] file di 5000 byte consegnato`);
    b = await B();
    check(b.done[1].crcOk && Buffer.compare(Buffer.from(b.done[1].data), big) === 0 && b.done[1].name === 'dati.bin', `[${scheme}] file identico, con il nome`);
    check(b.maxWrite <= 240, `[${scheme}] pacchetti di dati al massimo di 240 byte (${b.maxWrite})`);
    // file troppo grande
    await page.setInputFiles('#file', { name: 'grande.bin', mimeType: 'application/octet-stream', buffer: Buffer.alloc(65537) });
    await page.waitForTimeout(150);
    check((await page.textContent('#file_n')).includes('Troppo grande') && await page.isDisabled('#invia'), `[${scheme}] file di 64 kB + 1: rifiutato dalla pagina`);

    // MTU piccolo: la pagina riduce i pacchetti da sola
    await page.evaluate(() => { window.__board.mtuLimit = 20; window.__tel.chunk = 240; });
    await page.setInputFiles('#file', { name: 'piccolo.bin', mimeType: 'application/octet-stream', buffer: big.subarray(0, 1500) });
    await page.waitForFunction(() => window.__tel.payload && window.__tel.payload.name === 'piccolo.bin');
    await page.click('#invia');
    check(await wait(() => window.__board.done.length === 3, 15000), `[${scheme}] con scritture di al massimo 20 byte la pagina scende a pacchetti piccoli e consegna`);
    b = await B();
    check(b.done[2].crcOk && Buffer.compare(Buffer.from(b.done[2].data), big.subarray(0, 1500)) === 0 && await page.evaluate(() => window.__tel.chunk) === 20, `[${scheme}] file identico con pacchetti da 15 byte`);
    await page.evaluate(() => { window.__board.mtuLimit = 1e9; window.__tel.chunk = 240; });

    // interruzione del collegamento durante l'invio: la pagina si ricollega e manda RESUME
    await page.evaluate(() => { window.__board.dropAtBlock = 2; window.__board.dropped = false; });
    const big2 = Buffer.alloc(6000); for (let i = 0; i < big2.length; i++) big2[i] = (i * 17 + 3) & 255;
    await page.setInputFiles('#file', { name: 'lungo.bin', mimeType: 'application/octet-stream', buffer: big2 });
    await page.waitForFunction(() => window.__tel.payload && window.__tel.payload.name === 'lungo.bin');
    await page.click('#invia');
    check(await wait(() => window.__board.done.length === 4, 15000), `[${scheme}] collegamento caduto a meta': la pagina si ricollega e l'oggetto arriva`);
    b = await B();
    check(b.resumed >= 1 && b.done[3].crcOk && Buffer.compare(Buffer.from(b.done[3].data), big2) === 0, `[${scheme}] dopo la riconnessione manda RESUME (${b.resumed}) e il file e' identico`);

    // annullamento
    await page.evaluate(() => { window.__board.dropAtBlock = -1; });
    await page.setInputFiles('#file', { name: 'annulla.bin', mimeType: 'application/octet-stream', buffer: Buffer.alloc(20000, 5) });
    await page.waitForFunction(() => window.__tel.payload && window.__tel.payload.name === 'annulla.bin');
    await page.click('#invia');
    await wait(() => window.__tel.tx && window.__tel.tx.state === 'sending');
    await page.click('#annulla');
    check(await wait(() => window.__tel.tx.state === 'done') && (await page.textContent('#inviomsg')).includes('Annullato'), `[${scheme}] annullamento: la pagina lo mostra`);

    // errore della scheda: posizione rifiutata
    await page.evaluate(() => { window.__board.noPosition = true; });
    await page.click('#t_testo'); await page.fill('#testo', 'x');
    await page.click('#invia');
    check(await wait(() => window.__tel.tx.state === 'error') && (await page.textContent('#inviomsg')).includes('posizione'), `[${scheme}] errore NO_POSITION dalla scheda: messaggio comprensibile`);
    await page.evaluate(() => { window.__board.noPosition = false; });

    // ricezione dalla radio
    await page.evaluate(() => window.__board.radioReceive(0x0ABC, 0, new TextEncoder().encode('Risposta da IK5XYZ via radio'), 'IK5XYZ'));
    check(await wait(() => document.getElementById('ricevuti').textContent.includes('Risposta da IK5XYZ via radio')), `[${scheme}] testo ricevuto dalla radio: mostrato con il CRC giusto`);
    check(await wait(() => window.__board.rxAck === 0x0ABC) && (await page.textContent('#ricevuti')).includes('CRC giusto'), `[${scheme}] la pagina conferma alla scheda (RX_ACK)`);

    // immagine: compressione nel telefono
    await page.click('#t_img');
    const png = await page.evaluate(async () => { const c = document.createElement('canvas'); c.width = 640; c.height = 480; const x = c.getContext('2d'); for (let i = 0; i < 40; i++) { x.fillStyle = `hsl(${i * 9}, 80%, 50%)`; x.fillRect(i * 16, (i * 37) % 400, 40, 80); } const bl = await new Promise(r => c.toBlob(r, 'image/png')); return Array.from(new Uint8Array(await bl.arrayBuffer())); });
    await page.selectOption('#target', '5000');
    await page.setInputFiles('#img', { name: 'foto.png', mimeType: 'image/png', buffer: Buffer.from(png) });
    check(await wait(() => window.__tel.payload && window.__tel.payload.kind === 2), `[${scheme}] immagine ridimensionata e compressa nel telefono`);
    const ip = await page.evaluate(() => ({ n: window.__tel.payload.data.length, w: window.__tel.payload.w, h: window.__tel.payload.h, name: window.__tel.payload.name, jpg: window.__tel.payload.data[0] === 0xFF && window.__tel.payload.data[1] === 0xD8 }));
    check(ip.jpg && ip.n <= 5000 && ip.w > 0 && ip.w <= 320 && ip.name === 'foto.jpg', `[${scheme}] JPEG di ${ip.n} byte (massimo 5000), ${ip.w}x${ip.h}, nome foto.jpg`);
    await page.click('#invia');
    check(await wait(() => window.__board.done.length === 5, 15000), `[${scheme}] immagine consegnata in radio`);
    b = await B();
    check(b.done[4].kind === 2 && b.done[4].crcOk && b.done[4].data[0] === 0xFF, `[${scheme}] tipo immagine, CRC giusto, inizia con il marcatore JPEG`);
    const dd = b.done[4].data, le = b.done[4].lends;
    let sof2 = false; for (let i = 2; i + 4 < dd.length && dd[i] === 0xFF; ) { if (dd[i + 1] === 0xC2) { sof2 = true; break; } if (dd[i + 1] === 0xDA) break; i += 2 + ((dd[i + 2] << 8) | dd[i + 3]); }
    check(sof2, `[${scheme}] l'immagine mandata alla scheda e' un JPEG PROGRESSIVO (SOF2): la canvas lo scrive normale e la pagina lo trasforma senza perdite`);
    check(le.length === 3 && le[2] === dd.length && le[0] < le[1] && le[0] % 16 === 0 && le[1] % 16 === 0, `[${scheme}] il BEGIN porta tre livelli (fine a ${le.join(', ')} byte), i primi due su confini di pezzo`);
    check(dd[dd.length - 2] === 0xFF && dd[dd.length - 1] === 0xD9 && (await page.textContent('#img_n')).includes('3 livelli'), `[${scheme}] il file finisce con EOI e la pagina dice quanti livelli ha`);

    const noScroll = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    check(noScroll, `[${scheme}] nessuno scorrimento orizzontale a 390 px`);
    check(errors.length === 0, `[${scheme}] nessun errore nella console: ${errors.join(' | ')}`);
    await ctx.close();
  }
  // senza Web Bluetooth (iPhone): avviso e pulsante spento
  const ctx2 = await browser.newContext({ viewport: { width: 390, height: 900 } });
  const p2 = await ctx2.newPage();
  await p2.addInitScript(() => { Object.defineProperty(navigator, 'bluetooth', { value: undefined, configurable: true }); });
  await p2.goto(`http://127.0.0.1:${port}/telefono.html`);
  check(await p2.isVisible('#nobt') && await p2.isDisabled('#connetti') && (await p2.textContent('#nobt')).includes('iPhone'), 'senza Web Bluetooth (come su iPhone): avviso chiaro e pulsante spento');
  await browser.close(); server.close();
  console.log(fails ? `${fails} prove fallite` : 'pagina del telefono: tutte le prove passate');
  process.exit(fails ? 1 : 0);
})();
