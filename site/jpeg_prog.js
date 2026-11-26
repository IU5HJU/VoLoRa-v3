// Trasformazione SENZA PERDITE di un JPEG normale (baseline) in JPEG progressivo a tre livelli: stesso risultato di `jpegtran -progressive`, scritta per il browser.
// Si leggono i coefficienti DCT del JPEG di partenza (la canvas lo scrive normale) e li si riscrivono con lo script di scansioni di libjpeg (10 per un'immagine a colori, 6 in
// bianco e nero) e tabelle di Huffman ottimizzate; nessun pixel cambia. Poi le scansioni si raggruppano in tre LIVELLI (come tools/immagine_livelli.py) con la fine di ogni livello
// allineata a un pezzo da 16 byte (segmento COM di riempimento).  Specifica: docs/immagine-livelli.md.  Prova: tests/sim/test_jpeg_prog_js.py.
//   JpegProg.transcode(Uint8Array baseline) -> { data: Uint8Array, ends: [fine livello 1, fine livello 2, fine = lunghezza] }
(function (root) {
  'use strict';

  // ------------------------------------------------------------------ lettura del JPEG di partenza
  function parse(d) {
    if (d[0] !== 0xFF || d[1] !== 0xD8) throw new Error('non e\' un JPEG');
    let i = 2; const head = []; const dc = {}, ac = {}; let sof = null, dri = 0, comps = null;
    let scanFound = false;
    while (i + 4 <= d.length) {
      if (d[i] !== 0xFF) throw new Error('JPEG rovinato');
      const m = d[i + 1];
      if (m === 0xD9) break;
      const len = (d[i + 2] << 8) | d[i + 3], seg = d.subarray(i + 4, i + 2 + len);
      if (m === 0xC0 || m === 0xC1) {
        const P = seg[0], H = (seg[1] << 8) | seg[2], W = (seg[3] << 8) | seg[4], n = seg[5];
        if (P !== 8) throw new Error('solo 8 bit per campione');
        if (n !== 1 && n !== 3) throw new Error('solo 1 o 3 componenti');
        comps = []; for (let c = 0; c < n; c++) comps.push({ id: seg[6 + 3 * c], h: seg[7 + 3 * c] >> 4, v: seg[7 + 3 * c] & 15, tq: seg[8 + 3 * c] });
        sof = { width: W, height: H, raw: Array.from(seg), n };
        i += 2 + len; continue;
      }
      if (m === 0xC2 || m === 0xC3 || (m >= 0xC5 && m <= 0xCF && m !== 0xC4 && m !== 0xC8 && m !== 0xCC)) throw new Error('questo JPEG non e\' baseline');
      if (m === 0xC4) {
        let p = 0;
        while (p < seg.length) {
          const tc = seg[p] >> 4, th = seg[p] & 15; const counts = Array.from(seg.subarray(p + 1, p + 17)); const nv = counts.reduce((a, b) => a + b, 0);
          (tc === 0 ? dc : ac)[th] = mkDecTable(counts, Array.from(seg.subarray(p + 17, p + 17 + nv))); p += 17 + nv;
        }
        i += 2 + len; continue;
      }
      if (m === 0xDD) { dri = (seg[0] << 8) | seg[1]; i += 2 + len; continue; }
      if (m === 0xDA) {
        if (!sof) throw new Error('SOS prima di SOF');
        const ns = seg[0], sc = [];
        for (let c = 0; c < ns; c++) { const id = seg[1 + 2 * c], tt = seg[2 + 2 * c]; const ci = comps.findIndex(x => x.id === id); if (ci < 0) throw new Error('componente sconosciuta'); sc.push({ ci, td: tt >> 4, ta: tt & 15 }); }
        if (scanFound) throw new Error('baseline a piu\' scansioni non supportato');
        if (ns !== comps.length) throw new Error('serve una sola scansione con tutte le componenti');
        scanFound = true;
        decodeScan(d, i + 2 + len, sof, comps, sc, dc, ac, dri);
        break;
      }
      if (m !== 0xDB && !(m >= 0xE0 && m <= 0xEF) && m !== 0xFE) { /* marcatori sconosciuti: si tengono */ }
      head.push(d.subarray(i, i + 2 + len));          // APPn, DQT, COM e altro: si copiano cosi' come sono
      i += 2 + len;
    }
    if (!scanFound) throw new Error('nessuna scansione');
    return { sof, comps, head };
  }
  function mkDecTable(counts, vals) {
    const mincode = new Int32Array(17), maxcode = new Int32Array(18).fill(-1), valptr = new Int32Array(17);
    let code = 0, k = 0;
    for (let l = 1; l <= 16; l++) { valptr[l] = k; mincode[l] = code; code += counts[l - 1]; k += counts[l - 1]; maxcode[l] = counts[l - 1] ? code - 1 : -1; code <<= 1; }
    return { mincode, maxcode, valptr, vals };
  }
  function decodeScan(d, start, sof, comps, sc, dc, ac, dri) {
    let pos = start, bitBuf = 0, bitCnt = 0;
    const nextByte = () => {
      if (pos >= d.length) throw new Error('JPEG troncato');
      const b = d[pos++];
      if (b === 0xFF) { const n = d[pos]; if (n === 0) pos++; else throw new Error('marcatore inatteso nei dati'); }
      return b;
    };
    const bit = () => { if (!bitCnt) { bitBuf = nextByte(); bitCnt = 8; } bitCnt--; return (bitBuf >> bitCnt) & 1; };
    const recv = n => { let v = 0; for (let k = 0; k < n; k++) v = (v << 1) | bit(); return v; };
    const ext = (v, n) => (n && v < (1 << (n - 1))) ? v - (1 << n) + 1 : v;
    const huff = t => { let code = 0; for (let l = 1; l <= 16; l++) { code = (code << 1) | bit(); if (t.maxcode[l] >= 0 && code <= t.maxcode[l] && code >= t.mincode[l]) return t.vals[t.valptr[l] + code - t.mincode[l]]; } throw new Error('codice di Huffman non valido'); };
    const maxH = Math.max(...comps.map(c => c.h)), maxV = Math.max(...comps.map(c => c.v));
    const single = comps.length === 1;
    const mcuW = single ? 8 : 8 * maxH, mcuH = single ? 8 : 8 * maxV;
    const mcusX = Math.ceil(sof.width / mcuW), mcusY = Math.ceil(sof.height / mcuH);
    for (const c of comps) {
      const hh = single ? 1 : c.h, vv = single ? 1 : c.v;
      c.cw = Math.ceil(sof.width * c.h / maxH); c.ch = Math.ceil(sof.height * c.v / maxV);
      c.bw = single ? Math.ceil(sof.width / 8) : Math.ceil(c.cw / 8); c.bh = single ? Math.ceil(sof.height / 8) : Math.ceil(c.ch / 8);   // blocchi veri (scansioni di una componente)
      c.pbw = mcusX * hh; c.pbh = mcusY * vv;                                                                                              // blocchi di riempimento (scansioni intercalate)
      c.hh = hh; c.vv = vv; c.coef = new Int16Array(c.pbw * c.pbh * 64);
    }
    const pred = new Int32Array(comps.length);
    let n = 0;
    for (let my = 0; my < mcusY; my++) for (let mx = 0; mx < mcusX; mx++) {
      if (dri && n && n % dri === 0) {                                   // intervallo di ripartenza: byte intero, RSTn, predittori a zero
        bitCnt = 0; if (d[pos] !== 0xFF || d[pos + 1] < 0xD0 || d[pos + 1] > 0xD7) throw new Error('manca il marcatore di ripartenza'); pos += 2; pred.fill(0);
      }
      n++;
      for (let s = 0; s < sc.length; s++) {
        const c = comps[sc[s].ci], dt = dc[sc[s].td], at = ac[sc[s].ta];
        if (!dt || !at) throw new Error('tabella di Huffman mancante');
        for (let v = 0; v < c.vv; v++) for (let h = 0; h < c.hh; h++) {
          const base = ((my * c.vv + v) * c.pbw + (mx * c.hh + h)) * 64;
          const t = huff(dt); pred[sc[s].ci] += ext(recv(t), t); c.coef[base] = pred[sc[s].ci];
          for (let k = 1; k < 64;) {
            const rs = huff(at), r = rs >> 4, sz = rs & 15;
            if (!sz) { if (r === 15) { k += 16; continue; } break; }
            k += r; if (k > 63) throw new Error('coefficiente fuori dal blocco');
            c.coef[base + k] = ext(recv(sz), sz); k++;
          }
        }
      }
    }
  }

  // ------------------------------------------------------------------ tabelle di Huffman ottimizzate (Annex K.2, come libjpeg)
  function optimalTable(freqIn) {
    const freq = new Float64Array(257); for (let i = 0; i < 256; i++) freq[i] = freqIn[i] || 0; freq[256] = 1;        // 256 e' il codice riservato (tutti uno)
    const codesize = new Int32Array(257), others = new Int32Array(257).fill(-1);
    for (;;) {
      let c1 = -1, v = 1e30; for (let i = 0; i <= 256; i++) if (freq[i] && freq[i] <= v) { v = freq[i]; c1 = i; }
      let c2 = -1; v = 1e30; for (let i = 0; i <= 256; i++) if (freq[i] && freq[i] <= v && i !== c1) { v = freq[i]; c2 = i; }
      if (c2 < 0) break;
      freq[c1] += freq[c2]; freq[c2] = 0;
      codesize[c1]++; while (others[c1] >= 0) { c1 = others[c1]; codesize[c1]++; }
      others[c1] = c2;
      codesize[c2]++; while (others[c2] >= 0) { c2 = others[c2]; codesize[c2]++; }
    }
    const bits = new Int32Array(40);
    for (let i = 0; i <= 256; i++) if (codesize[i]) bits[codesize[i]]++;
    for (let i = 39; i > 16; i--) while (bits[i] > 0) { let j = i - 2; while (bits[j] === 0) j--; bits[i] -= 2; bits[i - 1]++; bits[j + 1] += 2; bits[j]--; }
    let i = 16; while (bits[i] === 0) i--; bits[i]--;                                                                    // toglie il codice riservato
    const vals = []; for (let l = 1; l <= 40; l++) for (let j = 0; j <= 255; j++) if (codesize[j] === l) vals.push(j);
    const counts = Array.from(bits.subarray(1, 17));
    const code = new Int32Array(256), size = new Int32Array(256);
    let c = 0, k = 0; for (let l = 1; l <= 16; l++) { for (let q = 0; q < counts[l - 1]; q++) { code[vals[k]] = c++; size[vals[k]] = l; k++; } c <<= 1; }
    return { counts, vals, code, size };
  }

  // ------------------------------------------------------------------ scritture a bit
  function BitWriter() { this.out = []; this.acc = 0; this.n = 0; }
  BitWriter.prototype.put = function (v, nb) {
    for (let b = nb - 1; b >= 0; b--) { this.acc = (this.acc << 1) | ((v >> b) & 1); if (++this.n === 8) { this.out.push(this.acc); if (this.acc === 0xFF) this.out.push(0); this.acc = 0; this.n = 0; } }
  };
  BitWriter.prototype.flush = function () { while (this.n) this.put(1, 1); };
  const nbitsOf = v => { let n = 0; while (v) { n++; v >>= 1; } return n; };

  // ------------------------------------------------------------------ le scansioni
  // Ogni funzione produce una lista di operazioni: ['S', tabella, simbolo] o ['B', valore, nbit]
  function blockOrderDC(img) {      // scansione DC: intercalata (tutte le componenti) se a colori, altrimenti raster sui blocchi veri
    const comps = img.comps, single = comps.length === 1, out = [];
    if (single) { const c = comps[0]; for (let by = 0; by < c.bh; by++) for (let bx = 0; bx < c.bw; bx++) out.push([0, (by * c.pbw + bx) * 64]); return out; }
    const maxH = Math.max(...comps.map(c => c.h)), maxV = Math.max(...comps.map(c => c.v));
    const mcusX = Math.ceil(img.sof.width / (8 * maxH)), mcusY = Math.ceil(img.sof.height / (8 * maxV));
    for (let my = 0; my < mcusY; my++) for (let mx = 0; mx < mcusX; mx++)
      comps.forEach((c, ci) => { for (let v = 0; v < c.vv; v++) for (let h = 0; h < c.hh; h++) out.push([ci, ((my * c.vv + v) * c.pbw + (mx * c.hh + h)) * 64]); });
    return out;
  }
  function scanDC(img, Ah, Al) {
    const ops = [], pred = new Int32Array(img.comps.length);
    for (const [ci, base] of blockOrderDC(img)) {
      const c = img.comps[ci], co = c.coef[base], tab = ci === 0 ? 0 : 1;
      if (Ah === 0) {
        const t2 = co >> Al, diff = t2 - pred[ci]; pred[ci] = t2;
        const a = Math.abs(diff), nb = nbitsOf(a);
        ops.push(['S', tab, nb]); if (nb) ops.push(['B', diff < 0 ? (diff - 1) & ((1 << nb) - 1) : diff, nb]);
      } else ops.push(['B', (co >> Al) & 1, 1]);
    }
    return ops;
  }
  function scanAC(img, ci, Ss, Se, Ah, Al) {
    const c = img.comps[ci], tab = ci === 0 ? 0 : 1, ops = [];
    let eobrun = 0, pend = [];         // pend: bit di correzione in attesa (solo rifinitura)
    const emitEob = () => {
      if (eobrun > 0) {
        const nb = nbitsOf(eobrun) - 1; ops.push(['S', tab, nb << 4]); if (nb) ops.push(['B', eobrun & ((1 << nb) - 1), nb]); eobrun = 0;
        for (const b of pend) ops.push(['B', b, 1]); pend = [];
      }
    };
    const abs = new Int32Array(64);
    for (let by = 0; by < c.bh; by++) for (let bx = 0; bx < c.bw; bx++) {
      const base = (by * c.pbw + bx) * 64;
      if (Ah === 0) {
        let r = 0;
        for (let k = Ss; k <= Se; k++) {
          let t = c.coef[base + k]; if (t === 0) { r++; continue; }
          let t2; if (t < 0) { t = -t; t >>= Al; t2 = ~t; } else { t >>= Al; t2 = t; }
          if (t === 0) { r++; continue; }
          emitEob();
          while (r > 15) { ops.push(['S', tab, 0xF0]); r -= 16; }
          const nb = nbitsOf(t); ops.push(['S', tab, (r << 4) + nb]); ops.push(['B', t2 & ((1 << nb) - 1), nb]); r = 0;
        }
        if (r > 0) { eobrun++; if (eobrun === 0x7FFF) emitEob(); }
      } else {
        let EOB = 0;
        for (let k = Ss; k <= Se; k++) { const t = Math.abs(c.coef[base + k]) >> Al; abs[k] = t; if (t === 1) EOB = k; }
        let r = 0, cur = [];
        for (let k = Ss; k <= Se; k++) {
          const t = abs[k];
          if (t === 0) { r++; continue; }
          while (r > 15 && k <= EOB) { emitEob(); ops.push(['S', tab, 0xF0]); r -= 16; for (const b of cur) ops.push(['B', b, 1]); cur = []; }
          if (t > 1) { cur.push(t & 1); continue; }
          emitEob();
          ops.push(['S', tab, (r << 4) + 1]); ops.push(['B', c.coef[base + k] < 0 ? 0 : 1, 1]);
          for (const b of cur) ops.push(['B', b, 1]); cur = []; r = 0;
        }
        if (r > 0 || cur.length) { eobrun++; pend = pend.concat(cur); if (eobrun === 0x7FFF || pend.length > 1000 - 64 + 1) emitEob(); }
      }
    }
    emitEob();
    return ops;
  }

  // ------------------------------------------------------------------ scrittura del file
  function seg(marker, payload) { const n = payload.length + 2; return [0xFF, marker, n >> 8, n & 255, ...payload]; }
  function writeScan(out, ops, comps, ss, se, ah, al, dcScan) {
    // tabelle ottimizzate per ogni (classe, id) usata
    const freq = [new Array(256).fill(0), new Array(256).fill(0)];
    for (const o of ops) if (o[0] === 'S') freq[o[1]][o[2]]++;
    const tabs = [], used = [];
    for (let t = 0; t < 2; t++) if (freq[t].some(x => x)) { tabs[t] = optimalTable(freq[t]); used.push(t); }
    for (const t of used) out.push(...seg(0xC4, [(dcScan ? 0 : 0x10) | t, ...tabs[t].counts, ...tabs[t].vals]));
    const sosComps = dcScan ? comps : [comps[ops.ci]];
    const sos = [sosComps.length];
    for (const sc of sosComps) { const t = sc.tab; sos.push(sc.id, dcScan ? (t << 4) : t); }
    sos.push(ss, se, (ah << 4) | al);
    out.push(...seg(0xDA, sos));
    const bw = new BitWriter();
    for (const o of ops) { if (o[0] === 'S') bw.put(tabs[o[1]].code[o[2]], tabs[o[1]].size[o[2]]); else bw.put(o[1], o[2]); }
    bw.flush();
    for (const b of bw.out) out.push(b);
  }

  function transcode(d) {
    const img = parse(d), comps = img.comps, color = comps.length === 3;
    comps.forEach((c, i) => { c.tab = i === 0 ? 0 : 1; });
    const out = [0xFF, 0xD8];
    for (const h of img.head) for (const b of h) out.push(b);
    const sof = img.sof.raw.slice(); out.push(...seg(0xC2, sof));
    const ends = [];
    const scan = (ci, ss, se, ah, al) => { const ops = scanAC(img, ci, ss, se, ah, al); ops.ci = ci; writeScan(out, ops, comps, ss, se, ah, al, false); };
    const dcscan = (ah, al) => writeScan(out, scanDC(img, ah, al), comps, 0, 0, ah, al, true);
    const mark = () => {      // fine di livello: un segmento COM porta l'offset a un multiplo di 16 (almeno 4 byte: marcatore 2 + lunghezza 2)
      const p = ((-out.length) % 16 + 16) % 16;
      if (p) { const n = p >= 4 ? p : p + 16; out.push(0xFF, 0xFE, ((n - 2) >> 8) & 255, (n - 2) & 255); for (let k = 0; k < n - 4; k++) out.push(0); }
      ends.push(out.length);
    };
    if (color) {            // lo script di libjpeg per YCbCr: 10 scansioni
      dcscan(0, 1);
      scan(0, 1, 5, 0, 2); mark();
      scan(2, 1, 63, 0, 1); scan(1, 1, 63, 0, 1);
      scan(0, 6, 63, 0, 2); scan(0, 1, 63, 2, 1); mark();
      dcscan(1, 0); scan(2, 1, 63, 1, 0); scan(1, 1, 63, 1, 0); scan(0, 1, 63, 1, 0);
    } else {                // bianco e nero: 6 scansioni
      dcscan(0, 1);
      scan(0, 1, 5, 0, 2); mark();
      scan(0, 6, 63, 0, 2); scan(0, 1, 63, 2, 1); mark();
      dcscan(1, 0); scan(0, 1, 63, 1, 0);
    }
    out.push(0xFF, 0xD9);
    ends.push(out.length);
    return { data: Uint8Array.from(out), ends };
  }

  const api = { transcode, parse };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.JpegProg = api;
})(typeof self !== 'undefined' ? self : this);
