// Prova della pagina di configurazione del nodo (site/nodo.html): validazione e JSON, con le stesse regole di tools/config_nodo.py.
//   node tests/page/run_nodo.js <cartella-del-sito>
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');
const site = path.resolve(process.argv[2] || '_site');
let fails = 0;
const check = (c, m) => { if (!c) { console.log('FALLITO: ' + m); fails++; } else console.log('ok: ' + m); };
(async () => {
  const server = http.createServer((req, res) => {
    const p = path.join(site, decodeURIComponent(req.url.split('?')[0]));
    if (!p.startsWith(site) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': 'text/html' }); fs.createReadStream(p).pipe(res);
  }).listen(0);
  const port = server.address().port;
  const browser = await chromium.launch(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {});
  for (const scheme of ['light', 'dark']) {
    const page = await (await browser.newContext({ viewport: { width: 390, height: 900 }, colorScheme: scheme })).newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    await page.goto(`http://127.0.0.1:${port}/nodo.html`);
    const stato = () => page.evaluate(() => window.__esito);
    let s = await stato();
    check(s.err.length === 1 && /nominativo/.test(s.err[0]), `[${scheme}] senza nominativo: un solo errore`);
    await page.fill('#nominativo', 'iu5hju');
    s = await stato();
    check(s.err.length === 0 && s.config.nominativo === 'IU5HJU' && s.config.topologia === 'singola' && s.config.freq_nodo_khz === 433700, `[${scheme}] nodo di partenza valido (nominativo in maiuscolo, singola, 433,700 MHz)`);
    check(s.config.v2_ruolo === 'gateway' && s.config.v3_ruolo === 'gateway' && s.config.attesa_fine_qso_min === 10 && s.config.forza_v3_da === 0, `[${scheme}] valori di partenza: gateway v2 e V3, attesa 10 minuti, nessun comando forzato`);
    await page.selectOption('#topologia', 'doppia');
    check(await page.isVisible('#voto') && await page.isHidden('#veloce'), `[${scheme}] doppia: compare il voto, non il 2,4 GHz`);
    await page.selectOption('#chip_servizio', 'SX1262');
    s = await stato();
    check(s.err.some(e => /SX1262/.test(e) && /150 MHz/.test(e)), `[${scheme}] voto a 144,900 MHz con SX1262: errore`);
    await page.selectOption('#voto_preset', '433.850');
    s = await stato();
    check(s.err.length === 0 && s.config.freq_voto_khz === 433850, `[${scheme}] voto a 433,850 MHz con SX1262: valido`);
    await page.selectOption('#topologia', 'tripla');
    check(await page.isVisible('#veloce'), `[${scheme}] tripla: compare il 2,4 GHz`);
    s = await stato();
    check(s.err.length === 0 && s.config.freq_veloce_khz === 2424000, `[${scheme}] tripla con 2424 MHz a 10k: valida`);
    await page.fill('#freq_veloce', '2450.5');
    s = await stato();
    check(s.err.some(e => /2400-2450/.test(e)), `[${scheme}] 2450,5 MHz: fuori banda`);
    await page.fill('#freq_veloce', '2425');
    await page.selectOption('#air_code_veloce', '4');
    s = await stato();
    check(s.err.some(e => /griglia/.test(e)), `[${scheme}] 2425 MHz a 50k (passo 2 MHz): fuori griglia`);
    await page.fill('#freq_veloce', '2426');
    s = await stato();
    check(s.err.length === 0, `[${scheme}] 2426 MHz a 50k: sulla griglia`);
    await page.fill('#attesa', '300');
    s = await stato();
    check(s.err.some(e => /1 a 255/.test(e)), `[${scheme}] attesa 300 minuti: errore`);
    await page.fill('#attesa', '30');
    await page.check('#forza_mobile'); await page.check('#forza_nodo'); await page.check('#lock_v2');
    await page.click('#gen');
    s = await stato();
    check(s.config.forza_v3_da === 3 && s.config.lock_v2 === true && /^[0-9a-f]{32}$/.test(s.config.chiave_sysop_hex) && s.err.length === 0, `[${scheme}] forza da mobile e nodo, lock, chiave generata di 32 cifre esadecimali`);
    check(JSON.parse(await page.textContent('#json')).chiave_sysop_hex === s.config.chiave_sysop_hex, `[${scheme}] il JSON mostrato contiene la chiave`);
    const noScroll = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    check(noScroll, `[${scheme}] nessuno scorrimento orizzontale a 390 px`);
    check(errors.length === 0, `[${scheme}] nessun errore nella console: ${errors.join(' | ')}`);
  }
  await browser.close(); server.close();
  console.log(fails ? `${fails} prove fallite` : 'pagina di configurazione: tutte le prove passate');
  process.exit(fails ? 1 : 0);
})();
