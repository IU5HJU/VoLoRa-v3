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
const MOCK = `
(() => {
  const SERVICE = 'c49a1433-9f1b-4af8-9826-951953e47edb';
  const U = n => 'c49a143' + n + '-9f1b-4af8-9826-951953e47edb';
  const crcT = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
  const crc32 = b => { let c = 0xFFFFFFFF; for (const x of b) c = crcT[(c ^ x) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  const rd = (b, o, n) => { let v = 0; for (let i = 0; i < n; i++) v = v * 256 + b[o + i]; return v; };
  const w = (...a) => new Uint8Array(a.flat());
  const be = (v, n) => Array.from({ length: n }, (_, i) => (v >>> (8 * (n - 1 - i))) & 255);
  const BLOCK = 1024;
  const board = window.__board = { pos: false, call: 'IU5HJU', sess: null, done: [], log: [], dropAtBlock: -1, noPosition: false, writes: 0, maxWrite: 0, mtuLimit: 1e9, resumed: 0, dropped: false, posBytes: null, rx: null };
  const listeners = {};
  function mk(uuid) {
    const ch = { uuid, _l: [], properties: {} };
    ch.addEventListener = (t, f) => ch._l.push(f);
    ch.startNotifications = async () => ch;
    ch.notify = bytes => { const v = new DataView(new Uint8Array(bytes).buffer); for (const f of ch._l) f({ target: { value: v } }); };
    return ch;
  }
  const cmd = mk(U('4')), dataIn = mk(U('5')), evt = mk(U('6')), dataOut = mk(U('7'));
  const ev = (...a) => evt.notify(w(...a));
  const pull = k => { const s = board.sess; const off = k * BLOCK, len = Math.min(BLOCK, s.size - off); s.asked.add(k); ev(0x89, be(s.obj, 2), be(off, 3), be(len, 2)); };
  function prefetch() {
    const s = board.sess; if (!s || !board.connected) return;
    for (let k = s.idx; k < Math.min(s.idx + 3, s.n); k++) if (!s.cache.has(k) && !s.asked.has(k)) pull(k);
  }
  function radioStep() {
    const s = board.sess; if (!s) return;
    if (s.cache.has(s.idx)) {
      s.sent.set(s.idx, s.cache.get(s.idx)); s.cache.delete(s.idx); s.idx++;
      if (board.dropAtBlock === s.idx && !board.dropped) { board.dropped = true; board.drop(); return; }
      if (s.idx >= s.n) {
        const all = new Uint8Array(s.size); for (const [k, v] of s.sent) all.set(v, k * BLOCK);
        board.done.push({ obj: s.obj, kind: s.kind, lends: s.lends, data: all, crcOk: crc32(all) === s.crc, dest: s.dest, name: s.name, pos: board.posBytes });
        ev(0x86, be(s.obj, 2), 0); board.sess = null; return;
      }
      if (s.idx % 2 === 0) ev(0x85, be(s.obj, 2), Math.floor(100 * s.idx / s.n), 5, be(10, 3));
      prefetch();
    }
    setTimeout(radioStep, 15);
  }
  cmd.writeValue = async v => {
    const b = new Uint8Array(v.buffer || v); board.log.push(b[0]);
    if (b[0] === 0x01) { const call = Array.from(board.call).map(c => c.charCodeAt(0)); evt.notify(w(0x80, 1, 0, be(0xFFF, 2), be(BLOCK, 3), be(65536, 3), board.pos ? 1 : 0, call.length, call)); }
    else if (b[0] === 0x02) { board.pos = true; board.posBytes = Array.from(b.slice(1)); }
    else if (b[0] === 0x10) {
      const obj = rd(b, 1, 2), kind = b[3], size = rd(b, 4, 3), crc = rd(b, 7, 4), nl = b[15];
      const lends = Array.from({ length: nl }, (_, i) => rd(b, 16 + 3 * i, 3));
      let p = 16 + 3 * nl; const dl = b[p]; const dest = new TextDecoder().decode(b.slice(p + 1, p + 1 + dl)); p += 1 + dl; const nn = b[p]; const name = new TextDecoder().decode(b.slice(p + 1, p + 1 + nn));
      if (!board.pos || board.noPosition) { ev(0x82, be(obj, 2), 4); return; }
      if (board.sess) { ev(0x82, be(obj, 2), 1); return; }
      board.sess = { obj, kind, size, crc, dest, name, lends, n: Math.ceil(size / BLOCK), idx: 0, cache: new Map(), partial: new Map(), asked: new Set(), sent: new Map() };
      ev(0x81, be(obj, 2), be(7, 3), 5, be(BLOCK, 2)); prefetch(); setTimeout(radioStep, 15);
    } else if (b[0] === 0x12) { const s = board.sess; if (s && s.obj === rd(b, 1, 2)) { board.sess = null; ev(0x86, be(s.obj, 2), 2); } }
    else if (b[0] === 0x13) { const s = board.sess; board.resumed++; if (s) { s.asked.clear(); s.partial.clear(); prefetch(); setTimeout(radioStep, 15); } }
    else if (b[0] === 0x14) board.rxAck = rd(b, 1, 2);
  };
  dataIn.writeValueWithoutResponse = async v => {
    const b = new Uint8Array(v.buffer || v); board.writes++; board.maxWrite = Math.max(board.maxWrite, b.length);
    if (b.length > board.mtuLimit) throw new Error('GATT: valore troppo lungo');
    if (!board.connected) throw new Error('scollegato');
    const s = board.sess; if (!s) return; const off = rd(b, 2, 3), k = Math.floor(off / BLOCK);
    if (rd(b, 0, 2) !== s.obj || !s.asked.has(k) || s.cache.has(k)) return;
    const start = k * BLOCK, ln = Math.min(BLOCK, s.size - start); const part = s.partial.get(k) || []; if (off !== start + part.length) return;
    part.push(...b.slice(5)); s.partial.set(k, part);
    if (part.length === ln) { s.cache.set(k, new Uint8Array(part)); s.partial.delete(k); }
  };
  const service = { getCharacteristic: async u => ({ [U('4')]: cmd, [U('5')]: dataIn, [U('6')]: evt, [U('7')]: dataOut })[u] };
  const dev = { name: 'VoLoRa-T3', gatt: {}, addEventListener: (t, f) => (listeners[t] = listeners[t] || []).push(f) };
  board.connected = false;
  dev.gatt.connect = async () => { board.connected = true; dev.gatt.connected = true; return { getPrimaryService: async u => { if (u !== SERVICE) throw new Error('servizio'); return service; } }; };
  dev.gatt.disconnect = () => { board.connected = false; dev.gatt.connected = false; };
  board.drop = () => { board.connected = false; dev.gatt.connected = false; if (board.sess) { board.sess.asked.clear(); board.sess.partial.clear(); } (listeners.gattserverdisconnected || []).forEach(f => f({})); };
  board.radioReceive = (obj, kind, data, from) => {
    const c = Array.from(from).map(x => x.charCodeAt(0));
    evt.notify(w(0x87, be(obj, 2), kind, be(data.length, 3), be(crc32(data), 4), c.length, c));
    for (let off = 0; off < data.length; off += 100) dataOut.notify(w(be(obj, 2), be(off, 3), Array.from(data.slice(off, off + 100))));
  };
  board.requestCount = 0;
  Object.defineProperty(navigator, 'bluetooth', { value: { requestDevice: async o => { board.requestCount++; board.filters = o; return dev; } }, configurable: true });
  window.__telFast = true;
})();
`;

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
