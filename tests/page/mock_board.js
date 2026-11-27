// La scheda finta dei test delle pagine del telefono (Web Bluetooth simulato e, con installWs(), WebSocket): un modello in JavaScript del ponte (tools/ble_bridge.py).
module.exports = `
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
  board.ev = ev; board.be = be;
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
  // BleClient finto (plugin @capacitor-community/bluetooth-le dell'app Android) sopra le stesse caratteristiche: serve a provare app/src/ble-shim.js
  board.makeBleClient = () => {
    const map = { [U('4')]: cmd, [U('5')]: dataIn, [U('6')]: evt, [U('7')]: dataOut };
    const calls = board.bleCalls = [];
    const bad = view => { if (!(view instanceof DataView)) throw new Error('il plugin vuole un DataView'); return new Uint8Array(view.buffer, view.byteOffset, view.byteLength); };
    board.dropBle = () => { board.connected = false; if (board.sess) { board.sess.asked.clear(); board.sess.partial.clear(); } if (board.bleOnDisconnect) board.bleOnDisconnect('AA:BB:CC'); };
    board.drop = board.dropBle;
    return {
      initialize: async o => { calls.push(['initialize', o]); },
      requestDevice: async o => { calls.push(['requestDevice', o]); board.requestCount++; return { deviceId: 'AA:BB:CC', name: 'VoLoRa-V3 IU5HJU' }; },
      connect: async (id, onDisconnect) => { board.connected = true; board.bleOnDisconnect = onDisconnect; calls.push(['connect', id]); },
      disconnect: async () => { board.connected = false; },
      isBonded: async () => false,
      createBond: async id => { calls.push(['createBond', id]); },
      startNotifications: async (id, svc, ch, cb) => { if (svc !== SERVICE) throw new Error('servizio'); map[ch]._l.push(e => cb(e.target.value)); },
      write: async (id, svc, ch, view) => map[ch].writeValue(bad(view)),
      writeWithoutResponse: async (id, svc, ch, view) => map[ch].writeValueWithoutResponse(bad(view))
    };
  };
  // Trasporto WebSocket (pagina servita dalla scheda): stesso ponte finto, con i messaggi prefissati dal canale (0 cmd, 1 data_in, 2 evt, 3 data_out)
  board.installWs = () => {
    board.wsOpen = 0;
    window.WebSocket = class {
      constructor(url) {
        this.url = url; this.binaryType = 'arraybuffer'; this.bufferedAmount = 0; board.wsUrl = url; board.ws = this; board.wsOpen++;
        const fwd = ch => v => { const u = new Uint8Array(v.target.value.buffer, v.target.value.byteOffset, v.target.value.byteLength); const m = new Uint8Array(u.length + 1); m[0] = ch; m.set(u, 1); setTimeout(() => this.onmessage && this.onmessage({ data: m.buffer }), 1); };
        this._f2 = fwd(2); this._f3 = fwd(3); evt._l.push(this._f2); dataOut._l.push(this._f3);
        setTimeout(() => { board.connected = true; this.onopen && this.onopen({}); }, 5);
      }
      send(d) { const u = new Uint8Array(d.buffer ? d.buffer.slice(d.byteOffset, d.byteOffset + d.byteLength) : d); const body = u.slice(1); if (u[0] === 0) return cmd.writeValue(body); return dataIn.writeValueWithoutResponse(body); }
      close() { board.connected = false; evt._l = evt._l.filter(f => f !== this._f2); dataOut._l = dataOut._l.filter(f => f !== this._f3); setTimeout(() => this.onclose && this.onclose({}), 1); }
    };
    board.drop = () => { board.connected = false; if (board.sess) { board.sess.asked.clear(); board.sess.partial.clear(); } if (board.ws) board.ws.close(); };
  };
  window.__telFast = true;
})();
`;
