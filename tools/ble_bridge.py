#!/usr/bin/env python3
"""Ponte BLE telefono <-> scheda V3 (specifica in docs/ble-telefono.md): codec dei frame, la scheda (BleBridge), il telefono (Phone) e un collegamento BLE finto.
Provato sul PC (tests/sim/test_ble_bridge.py), NON su schede ne' su telefoni. Il trasporto radio e' un modello: il tempo viene da protocollo_immagini.estimate_seconds."""
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame_mesh as fm  # noqa: E402
import protocollo_immagini as pi  # noqa: E402

VERSION = 1
# UUID a 128 bit (scelti a caso il 26/11/2026, non registrati): servizio e quattro caratteristiche
SERVICE_UUID = "c49a1433-9f1b-4af8-9826-951953e47edb"
CHAR_UUIDS = {"cmd": "c49a1434-9f1b-4af8-9826-951953e47edb", "data_in": "c49a1435-9f1b-4af8-9826-951953e47edb",
              "evt": "c49a1436-9f1b-4af8-9826-951953e47edb", "data_out": "c49a1437-9f1b-4af8-9826-951953e47edb"}
KIND_TEXT, KIND_FILE, KIND_IMAGE = 0, 1, 2
# comandi (telefono -> scheda, caratteristica CMD, scrittura con risposta)
C_HELLO, C_POSITION, C_BEGIN, C_CANCEL, C_RESUME, C_RX_ACK = 0x01, 0x02, 0x10, 0x12, 0x13, 0x14
# eventi (scheda -> telefono, caratteristica EVT, notifica)
E_INFO, E_BEGIN_OK, E_ERR, E_PROGRESS, E_DONE, E_RX, E_PULL = 0x80, 0x81, 0x82, 0x85, 0x86, 0x87, 0x89
# codici di errore (3 = NO_MEMORY e 6 = CRC: riservati, non usati nel modello "il buffer e' il telefono")
ERR_BUSY, ERR_TOO_BIG, ERR_NO_MEMORY, ERR_NO_POSITION, ERR_BAD_FRAME, ERR_CRC, ERR_BAD_KIND, ERR_UNKNOWN_OBJ, ERR_NO_CALL = 1, 2, 3, 4, 5, 6, 7, 8, 9
DONE_DELIVERED, DONE_FAILED, DONE_CANCELLED = 0, 1, 2
BLOCK = 1024             # unita' di richiesta: la scheda chiede al telefono un blocco alla volta, quando la radio ne ha bisogno
CACHE_BLOCKS = 3         # RAM della scheda per l'oggetto: il blocco in trasmissione e i due successivi (3 kB). Il BUFFER e' il telefono; niente microSD sulle schede mobili
MAX_TEXT = 1024
MAX_OBJECT = 65536       # tetto del progetto per questo ponte (decide il tempo di radio, non la RAM della scheda)
STALL_TIMEOUT_S = 60.0   # radio in attesa di un blocco che il telefono non manda: si abbandona
RETX_DELAY = 4           # una ritrasmissione selettiva torna in coda dopo alcuni blocchi (la mappa del ricevitore arriva a fine finestra): oltre la cache
DATA_HDR = 5             # oggetto (2) + offset (3)
CHIP = {"SX1278": 0, "SX1262": 1}


class BadFrame(ValueError):
    pass


# ------------------------------------------------------------------------------------------------------------------ codec
def _u24(v):
    return int(v).to_bytes(3, "big")


def enc_hello():
    return bytes([C_HELLO, VERSION])


def enc_position(pos):
    return bytes([C_POSITION]) + fm.pack_pos(pos)


def enc_begin(obj, kind, data, dest, name="", width=0, height=0, layer_ends=()):
    if len(dest) > 12 or len(name.encode()) > 40 or len(layer_ends) > 8:
        raise BadFrame("campi troppo lunghi")
    return (bytes([C_BEGIN]) + struct.pack(">HB", obj, kind) + _u24(len(data)) + struct.pack(">IHHB", zlib.crc32(data) & 0xFFFFFFFF, width, height, len(layer_ends))
            + b"".join(_u24(e) for e in layer_ends) + bytes([len(dest)]) + dest.encode() + bytes([len(name.encode())]) + name.encode())


def dec_begin(b):
    try:
        obj, kind = struct.unpack(">HB", b[1:4])
        size = int.from_bytes(b[4:7], "big")
        crc, w, h, nl = struct.unpack(">IHHB", b[7:16])
        p = 16
        ends = [int.from_bytes(b[p + 3 * i:p + 3 * i + 3], "big") for i in range(nl)]
        p += 3 * nl
        dl = b[p]
        dest = b[p + 1:p + 1 + dl].decode()
        p += 1 + dl
        nlen = b[p]
        name = b[p + 1:p + 1 + nlen].decode()
        if len(b) != p + 1 + nlen or len(dest) != dl:
            raise BadFrame("lunghezza")
    except (IndexError, struct.error, UnicodeDecodeError) as e:
        raise BadFrame(str(e))
    return dict(obj=obj, kind=kind, size=size, crc=crc, width=w, height=h, layer_ends=ends, dest=dest, name=name)


def enc_obj_cmd(code, obj):
    return struct.pack(">BH", code, obj)


def enc_data(obj, offset, payload):
    return struct.pack(">H", obj) + _u24(offset) + bytes(payload)


def dec_data(b):
    if len(b) <= DATA_HDR:
        raise BadFrame("dati vuoti")
    return struct.unpack(">H", b[:2])[0], int.from_bytes(b[2:5], "big"), bytes(b[5:])


def enc_info(chip, rung_mask, block, max_obj, position_known, call):
    return bytes([E_INFO, VERSION, CHIP[chip]]) + struct.pack(">H", rung_mask) + _u24(block) + _u24(max_obj) + bytes([1 if position_known else 0, len(call)]) + call.encode()


def dec_info(b):
    ver, chip, mask = struct.unpack(">BBH", b[1:5])
    call_len = b[12]
    return dict(version=ver, chip="SX1262" if chip else "SX1278", rung_mask=mask, block=int.from_bytes(b[5:8], "big"), max_obj=int.from_bytes(b[8:11], "big"),
                position_known=bool(b[11]), call=b[13:13 + call_len].decode())


def enc_event(code, obj, *fields):
    """Eventi con campi numerici: E_BEGIN_OK (tempo stimato di radio 3 s, gradino 1, blocco 2), E_ERR (codice 1), E_PROGRESS (percento 1, gradino 1, secondi che mancano 3),
    E_DONE (esito 1), E_PULL (offset 3, lunghezza 2): la scheda chiede al telefono `lunghezza` byte dell'oggetto da `offset`."""
    layout = {E_BEGIN_OK: "312", E_ERR: "1", E_PROGRESS: "113", E_DONE: "1", E_PULL: "32"}
    body = b""
    for width, v in zip(layout[code], fields):
        body += int(v).to_bytes(int(width), "big")
    return struct.pack(">BH", code, obj) + body


def dec_event(b):
    layout = {E_BEGIN_OK: (3, 1, 2), E_ERR: (1,), E_PROGRESS: (1, 1, 3), E_DONE: (1,), E_PULL: (3, 2)}
    code = b[0]
    if code not in layout or len(b) != 3 + sum(layout[code]):
        raise BadFrame("evento")
    obj = struct.unpack(">H", b[1:3])[0]
    out, p = [], 3
    for w in layout[code]:
        out.append(int.from_bytes(b[p:p + w], "big"))
        p += w
    return code, obj, out


def enc_rx(obj, kind, size, crc, from_call):
    return struct.pack(">BHB", E_RX, obj, kind) + _u24(size) + struct.pack(">IB", crc, len(from_call)) + from_call.encode()


def dec_rx(b):
    obj, kind = struct.unpack(">HB", b[1:4])
    size = int.from_bytes(b[4:7], "big")
    crc, n = struct.unpack(">IB", b[7:12])
    return dict(obj=obj, kind=kind, size=size, crc=crc, from_call=b[12:12 + n].decode())


# ------------------------------------------------------------------------------------------------------------------ collegamento BLE finto
class BleLink:
    """Collegamento BLE affidabile (il livello di collegamento ritrasmette) con una capacita' per evento di connessione. Si puo' interrompere e ripristinare.
    Quello che e' in volo in un'interruzione va perso (non e' stato consegnato)."""

    def __init__(self, mtu=185, interval_s=0.03, pkts_per_event=4):
        self.mtu, self.interval, self.ppe = mtu, interval_s, pkts_per_event
        self.up = True
        self.to_node, self.to_phone = [], []     # (canale, byte)

    @property
    def att_payload(self):
        return self.mtu - 3

    def drop(self):
        self.up = False
        self.to_node.clear()
        self.to_phone.clear()

    def restore(self):
        self.up = True


# ------------------------------------------------------------------------------------------------------------------ la scheda
class BleBridge:
    """La scheda NON tiene l'oggetto: il buffer e' il telefono. La radio consuma l'oggetto a blocchi; la scheda chiede al telefono (E_PULL) il blocco in trasmissione e i due
    successivi, li tiene in RAM (CACHE_BLOCKS) e li rilascia appena trasmessi; se la ritrasmissione selettiva ne richiede uno gia' liberato, lo richiede al telefono."""

    def __init__(self, call="IU5HJU", chip="SX1278", position=None, rung=5, rung_mask=None, radio_ok=True, retx=()):
        self.call, self.chip, self.position, self.rung, self.radio_ok = call, chip, position, rung, radio_ok
        self.rung_mask = rung_mask if rung_mask is not None else (0xFFF if chip == "SX1278" else 0xFFE)
        self.retx_plan = set(retx)    # blocchi da ritrasmettere una volta (la mappa del ricevitore li dichiara mancanti): prova della ritrasmissione selettiva
        self.sess = None
        self.radio_log = []           # quello che parte davvero in radio
        self.out, self.out_data = [], []
        self.rx_sessions = {}
        self.last_done = {}           # esito degli ultimi oggetti: se la notifica DONE si perde nell'interruzione, il RESUME la rida'
        self.connected = True
        self.t = 0.0
        self.stats = dict(bad_frames=0, dropped=0, max_held=0, pulls=0, repulls=0, stalled_s=0.0, blocks_sent=0)

    # -- sessione
    def _nblocks(self):
        return (self.sess["h"]["size"] + BLOCK - 1) // BLOCK

    def _span(self, k):
        size = self.sess["h"]["size"]
        return k * BLOCK, min(BLOCK, size - k * BLOCK)

    def held(self):
        if not self.sess:
            return 0
        return sum(len(v) for v in self.sess["cache"].values()) + sum(len(v) for v in self.sess["partial"].values())

    def _notify(self, frame):
        """Una notifica a telefono non collegato non esiste: si perde (l'esito resta in last_done e si rida' con RESUME)."""
        if self.connected:
            self.out.append(frame)

    def _err(self, obj, code):
        self._notify(enc_event(E_ERR, obj, code))

    def _done(self, obj, status):
        self.last_done[obj] = status
        while len(self.last_done) > 4:
            self.last_done.pop(next(iter(self.last_done)))
        self._notify(enc_event(E_DONE, obj, status))

    # -- collegamento BLE
    def on_disconnect(self):
        self.connected = False
        if self.sess:
            self.sess["partial"].clear()      # un blocco a meta' si butta: lo si richiede intero
            self.sess["asked"].clear()

    def on_connect(self):
        self.connected = True

    # -- comandi
    def on_command(self, b):
        try:
            if not b:
                raise BadFrame("vuoto")
            c = b[0]
            if c == C_HELLO:
                self._notify(enc_info(self.chip, self.rung_mask, BLOCK, MAX_OBJECT, self.position is not None, self.call))
            elif c == C_POSITION:
                if len(b) != 8:
                    raise BadFrame("posizione")
                self.position = fm.unpack_pos(b[1:8])
            elif c == C_BEGIN:
                self._begin(dec_begin(b))
            elif c in (C_CANCEL, C_RESUME, C_RX_ACK):
                if len(b) != 3:
                    raise BadFrame("comando")
                obj = struct.unpack(">H", b[1:3])[0]
                {C_CANCEL: self._cancel, C_RESUME: self._resume, C_RX_ACK: self._rx_ack}[c](obj)
            else:
                raise BadFrame("comando sconosciuto")
        except (BadFrame, ValueError, IndexError, struct.error):
            self.stats["bad_frames"] += 1
            self._err(0, ERR_BAD_FRAME)

    def _begin(self, h):
        obj = h["obj"]
        if not self.call:
            return self._err(obj, ERR_NO_CALL)
        if h["kind"] not in (KIND_TEXT, KIND_FILE, KIND_IMAGE):
            return self._err(obj, ERR_BAD_KIND)
        if self.position is None:       # regola del progetto: ogni collegamento porta nominativo, rapporto e posizione (locatore o GPS)
            return self._err(obj, ERR_NO_POSITION)
        if h["size"] == 0 or h["size"] > MAX_OBJECT or (h["kind"] == KIND_TEXT and h["size"] > MAX_TEXT):
            return self._err(obj, ERR_TOO_BIG)
        if self.sess is not None:        # un oggetto alla volta
            return self._err(obj, ERR_BUSY)
        dur = pi.estimate_seconds(h["size"], self.rung, self.chip)
        n = (h["size"] + BLOCK - 1) // BLOCK
        self.sess = dict(h=h, cache={}, partial={}, asked=set(), seq=list(range(n)), idx=0, in_block=0.0, dur=dur, sent={}, started=self.t, last_progress=self.t, pct=0,
                         stall=0.0, retx_left=set(self.retx_plan & set(range(n))))
        self._notify(enc_event(E_BEGIN_OK, obj, int(dur + 0.5), self.rung, BLOCK))
        self._prefetch()

    def _lookahead(self):
        s = self.sess
        out = []
        for k in s["seq"][s["idx"]:s["idx"] + CACHE_BLOCKS]:
            if k not in out:
                out.append(k)
        return out

    def _prefetch(self):
        """Richiede al telefono i blocchi che servono alla radio nei prossimi passi e butta quelli che non servono piu'."""
        s = self.sess
        if s is None:
            return
        want = self._lookahead()
        for k in list(s["cache"]):
            if k not in want:
                del s["cache"][k]
                s["asked"].discard(k)       # liberato: se serve di nuovo si richiede al telefono
        for k in list(s["partial"]):
            if k not in want:
                del s["partial"][k]
                s["asked"].discard(k)
        if not self.connected:
            return
        for k in want:
            if k not in s["cache"] and k not in s["asked"]:
                off, ln = self._span(k)
                s["asked"].add(k)
                self.stats["pulls"] += 1
                if k in s.get("served", set()):
                    self.stats["repulls"] += 1
                self._notify(enc_event(E_PULL, s["h"]["obj"], off, ln))

    def _cancel(self, obj):
        if not self.sess or self.sess["h"]["obj"] != obj:
            return self._err(obj, ERR_UNKNOWN_OBJ)
        self.sess = None
        self._done(obj, DONE_CANCELLED)

    def _resume(self, obj):
        """Dopo una riconnessione: la scheda richiede di nuovo i blocchi che le servono (le richieste in volo si erano perse)."""
        if obj in self.last_done and (not self.sess or self.sess["h"]["obj"] != obj):
            return self._notify(enc_event(E_DONE, obj, self.last_done[obj]))
        if not self.sess or self.sess["h"]["obj"] != obj:
            return self._err(obj, ERR_UNKNOWN_OBJ)
        self.sess["asked"].clear()
        self.sess["stall"] = 0.0
        self._prefetch()

    def _rx_ack(self, obj):
        self.rx_sessions.pop(obj, None)

    # -- dati dal telefono (scrittura senza risposta): solo i blocchi richiesti, in ordine
    def on_data(self, b):
        try:
            obj, off, payload = dec_data(b)
        except BadFrame:
            self.stats["bad_frames"] += 1
            return
        s = self.sess
        if s is None or s["h"]["obj"] != obj:
            return
        k = off // BLOCK
        if k not in s["asked"] or k in s["cache"] or k >= self._nblocks():
            self.stats["dropped"] += 1
            return
        start, ln = self._span(k)
        part = s["partial"].setdefault(k, bytearray())
        if off != start + len(part) or len(part) + len(payload) > ln:
            self.stats["dropped"] += 1
            return
        part += payload
        if len(part) == ln:
            s["cache"][k] = bytes(s["partial"].pop(k))
            s.setdefault("served", set()).add(k)
        self.stats["max_held"] = max(self.stats["max_held"], self.held())

    # -- radio (modello): trasmette il blocco corrente quando ce l'ha; se manca, aspetta
    def tick(self, dt):
        self.t += dt
        s = self.sess
        if s is None:
            return
        n = self._nblocks()
        cur = s["seq"][s["idx"]] if s["idx"] < len(s["seq"]) else None
        if cur is None:
            return
        if cur not in s["cache"]:
            s["stall"] += dt
            self.stats["stalled_s"] += dt
            if s["stall"] > STALL_TIMEOUT_S:
                obj = s["h"]["obj"]
                self.sess = None
                self._done(obj, DONE_FAILED)
            return
        s["stall"] = 0.0
        _, ln = self._span(cur)
        bt = s["dur"] * ln / s["h"]["size"]
        s["in_block"] += dt
        if s["in_block"] < bt:
            return
        s["in_block"] = 0.0
        s["sent"].setdefault(cur, s["cache"][cur])
        self.stats["blocks_sent"] += 1
        s["idx"] += 1
        if cur in s["retx_left"]:         # la mappa del ricevitore dira' che manca: lo si rimanda dopo due blocchi
            s["retx_left"].discard(cur)
            s["seq"].insert(min(s["idx"] + RETX_DELAY, len(s["seq"])), cur)
        if s["idx"] >= len(s["seq"]):
            obj, h = s["h"]["obj"], s["h"]
            status = DONE_DELIVERED if self.radio_ok else DONE_FAILED
            if self.radio_ok:
                data = b"".join(s["sent"][k] for k in range(n))
                self.radio_log.append(dict(obj=obj, kind=h["kind"], data=data, crc=h["crc"], dest=h["dest"], name=h["name"], call=self.call, position=self.position, rung=self.rung))
            self.sess = None
            self._done(obj, status)
            return
        done = sum(1 for k in range(n) if k in s["sent"])
        pct = min(99, int(100 * done / n))
        if pct - s["pct"] >= 10 and self.t - s["last_progress"] >= 2.0:
            s["pct"], s["last_progress"] = pct, self.t
            self._notify(enc_event(E_PROGRESS, s["h"]["obj"], pct, self.rung, int(s["dur"] * (100 - pct) / 100)))
        self._prefetch()

    def radio_received(self, obj, kind, data, from_call):
        """Un oggetto arrivato dalla radio: la scheda non lo conserva, quindi lo accetta solo con il telefono collegato; passa al telefono a pezzi. False = rifiutato."""
        if not self.connected:
            return False
        crc = zlib.crc32(data) & 0xFFFFFFFF
        self._notify(enc_rx(obj, kind, len(data), crc, from_call))
        self.rx_sessions[obj] = data
        self.out_data.append((obj, bytes(data), 0))
        return True


# ------------------------------------------------------------------------------------------------------------------ il telefono
class Phone:
    """Il telefono tiene l'oggetto intero (e' lui il buffer) e risponde alle richieste E_PULL della scheda."""

    def __init__(self, link, bridge):
        self.link, self.b = link, bridge
        self.info = None
        self.tx = {}          # obj -> dict
        self.pulls = []       # richieste da servire: (obj, offset, lunghezza, inviati)
        self.events = []
        self.received = {}
        self.errors = []
        self.bytes_resent = 0
        self.bad_events = 0
        self.served = {}      # (obj, offset) -> quante volte e' stato servito

    def hello(self):
        self.link.to_node.append(("cmd", enc_hello()))

    def set_position(self, pos):
        self.link.to_node.append(("cmd", enc_position(pos)))

    def send(self, obj, kind, data, dest, name="", **kw):
        self.tx[obj] = dict(data=bytes(data), state="begin", eta=None, done=None, rung=None)
        self.link.to_node.append(("cmd", enc_begin(obj, kind, data, dest, name, **kw)))

    def cancel(self, obj):
        self.link.to_node.append(("cmd", enc_obj_cmd(C_CANCEL, obj)))

    def reconnect(self):
        """Dopo un'interruzione le richieste in coda e in volo sono perse: si rilegge lo stato con RESUME e la scheda richiede quello che le serve."""
        self.pulls.clear()
        for obj, t in self.tx.items():
            if t["state"] in ("begin", "sending"):
                self.link.to_node.append(("cmd", enc_obj_cmd(C_RESUME, obj)))

    def on_event(self, b):
        try:
            self._on_event(b)
        except (BadFrame, IndexError, struct.error, UnicodeDecodeError, KeyError):
            self.bad_events += 1       # un evento sbagliato si scarta: il telefono non si ferma

    def _on_event(self, b):
        if b[0] == E_INFO:
            self.info = dec_info(b)
            return
        if b[0] == E_RX:
            h = dec_rx(b)
            self.received[h["obj"]] = dict(h=h, buf=bytearray(), ok=None)
            return
        code, obj, f = dec_event(b)
        self.events.append((code, obj, f))
        t = self.tx.get(obj)
        if code == E_ERR:
            self.errors.append((obj, f[0]))
            if t:
                t["state"], t["done"] = "error", f[0]
        elif t is None:
            return
        elif code == E_BEGIN_OK:
            t["eta"], t["rung"], t["state"] = f[0], f[1], "sending"
        elif code == E_PULL:
            if f[0] + f[1] > len(t["data"]) or f[1] == 0:
                raise BadFrame("richiesta fuori dall'oggetto")
            self.served[(obj, f[0])] = self.served.get((obj, f[0]), 0) + 1
            if self.served[(obj, f[0])] > 1:
                self.bytes_resent += f[1]
            self.pulls.append([obj, f[0], f[1], 0])
        elif code == E_DONE:
            t["state"], t["done"] = "done", f[0]

    def on_data(self, b):
        try:
            obj, off, payload = dec_data(b)
        except BadFrame:
            return
        r = self.received.get(obj)
        if r is None or off != len(r["buf"]):
            return
        r["buf"] += payload
        if len(r["buf"]) == r["h"]["size"]:
            r["ok"] = zlib.crc32(bytes(r["buf"])) & 0xFFFFFFFF == r["h"]["crc"]
            self.link.to_node.append(("cmd", enc_obj_cmd(C_RX_ACK, obj)))

    def pump(self, max_pkts):
        n = 0
        while self.pulls and n < max_pkts:
            p = self.pulls[0]
            obj, off, ln, sent = p
            data = self.tx[obj]["data"]
            size = min(self.link.att_payload - DATA_HDR, ln - sent)
            self.link.to_node.append(("data", enc_data(obj, off + sent, data[off + sent:off + sent + size])))
            p[3] += size
            n += 1
            if p[3] >= ln:
                self.pulls.pop(0)


# ------------------------------------------------------------------------------------------------------------------ esecuzione
def run(link, bridge, phone, seconds, drops=(), hook=None):
    """Esegue il collegamento per `seconds`. drops = [(t_giu, t_su)]: interruzioni del BLE (il telefono si ricollega da solo)."""
    t = 0.0
    down_until = None
    pending = sorted(drops)
    while t < seconds:
        if pending and t >= pending[0][0] and link.up:
            link.drop()
            bridge.out.clear()      # le notifiche non consegnate si perdono con il collegamento
            bridge.on_disconnect()
            phone.pulls.clear()
            down_until = pending[0][1]
            pending.pop(0)
        if not link.up and down_until is not None and t >= down_until:
            link.restore()
            down_until = None
            bridge.on_connect()
            phone.reconnect()
        if link.up:
            if hook:
                hook(t, phone, bridge)
            for _ in range(link.ppe):      # la scheda legge quello che il telefono ha scritto al passo precedente: in un'interruzione il volo si perde
                if link.to_node:
                    ch, b = link.to_node.pop(0)
                    (bridge.on_command if ch == "cmd" else bridge.on_data)(b)
            phone.pump(link.ppe)
            for _ in range(link.ppe):
                if bridge.out:
                    phone.on_event(bridge.out.pop(0))
                elif bridge.out_data:
                    obj, data, off = bridge.out_data[0]
                    n = min(link.att_payload - DATA_HDR, len(data) - off)
                    phone.on_data(enc_data(obj, off, data[off:off + n]))
                    if off + n >= len(data):
                        bridge.out_data.pop(0)
                    else:
                        bridge.out_data[0] = (obj, data, off + n)
        bridge.tick(link.interval)
        t += link.interval
    return t


if __name__ == "__main__":
    l = BleLink(mtu=185)
    b = BleBridge(position={"loc": "JN53ab"})
    p = Phone(l, b)
    p.hello()
    p.send(1, KIND_FILE, bytes(range(256)) * 40, "IK5XYZ", "prova.bin")
    run(l, b, p, 60)
    print(p.tx[1]["state"], p.tx[1]["eta"], len(b.radio_log), b.stats)
