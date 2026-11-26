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
E_INFO, E_BEGIN_OK, E_ERR, E_CREDIT, E_STAGED, E_PROGRESS, E_DONE, E_RX, E_RESUME = 0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88
# codici di errore
ERR_BUSY, ERR_TOO_BIG, ERR_NO_MEMORY, ERR_NO_POSITION, ERR_BAD_FRAME, ERR_CRC, ERR_BAD_KIND, ERR_UNKNOWN_OBJ, ERR_NO_CALL = 1, 2, 3, 4, 5, 6, 7, 8, 9
DONE_DELIVERED, DONE_FAILED, DONE_CANCELLED = 0, 1, 2
WINDOW = 2048            # byte di credito per volta (controllo di flusso: la scrittura senza risposta di NimBLE puo' perdere pacchetti se si esagera)
MAX_TEXT = 1024
MAX_OBJECT = 65536       # tetto del progetto per questo ponte
BUFFER_BYTES = 32768     # RAM dedicata (decisione di partenza: la T3 non ha PSRAM; con la microSD si potra' salire)
RESUME_TIMEOUT_S = 60.0
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


def enc_info(chip, rung_mask, buf_total, max_obj, position_known, call):
    return bytes([E_INFO, VERSION, CHIP[chip]]) + struct.pack(">H", rung_mask) + _u24(buf_total) + _u24(max_obj) + bytes([1 if position_known else 0, len(call)]) + call.encode()


def dec_info(b):
    ver, chip, mask = struct.unpack(">BBH", b[1:5])
    call_len = b[12]
    return dict(version=ver, chip="SX1262" if chip else "SX1278", rung_mask=mask, buf_total=int.from_bytes(b[5:8], "big"), max_obj=int.from_bytes(b[8:11], "big"),
                position_known=bool(b[11]), call=b[13:13 + call_len].decode())


def enc_event(code, obj, *fields):
    """Eventi con campi numerici: E_BEGIN_OK (credito 3, eta' 3, gradino 1), E_ERR (codice 1), E_CREDIT (credito 3, prossimo offset 3), E_STAGED (-),
    E_PROGRESS (percento 1, gradino 1, eta' 3), E_DONE (esito 1), E_RESUME (prossimo offset 3, credito 3)."""
    layout = {E_BEGIN_OK: "331", E_ERR: "1", E_CREDIT: "33", E_STAGED: "", E_PROGRESS: "113", E_DONE: "1", E_RESUME: "33"}
    body = b""
    for width, v in zip(layout[code], fields):
        body += int(v).to_bytes(int(width), "big")
    return struct.pack(">BH", code, obj) + body


def dec_event(b):
    layout = {E_BEGIN_OK: (3, 3, 1), E_ERR: (1,), E_CREDIT: (3, 3), E_STAGED: (), E_PROGRESS: (1, 1, 3), E_DONE: (1,), E_RESUME: (3, 3)}
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
    def __init__(self, call="IU5HJU", chip="SX1278", position=None, rung=5, rung_mask=None, radio_ok=True, buf_total=BUFFER_BYTES):
        self.call, self.chip, self.position, self.rung, self.radio_ok = call, chip, position, rung, radio_ok
        self.rung_mask = rung_mask if rung_mask is not None else (0xFFF if chip == "SX1278" else 0xFFE)
        self.buf_total = buf_total
        self.sessions = {}            # obj -> dict
        self.staged = []              # coda verso la radio (al massimo una, in RAM)
        self.radio = None             # oggetto in trasmissione
        self.radio_log = []           # (obj, kind, byte, destinatario, posizione): quello che parte davvero in radio
        self.out = []                 # eventi (byte) da notificare
        self.out_data = []            # dati in uscita verso il telefono (oggetti ricevuti)
        self.rx_sessions = {}
        self.t = 0.0
        self.stats = dict(bad_frames=0, dropped_out_of_order=0)

    # -- memoria
    def used(self):
        return sum(len(s["buf"]) if s["state"] != "rx" else 0 for s in self.sessions.values())

    def _err(self, obj, code):
        self.out.append(enc_event(E_ERR, obj, code))

    # -- comandi
    def on_command(self, b):
        try:
            if not b:
                raise BadFrame("vuoto")
            c = b[0]
            if c == C_HELLO:
                self.out.append(enc_info(self.chip, self.rung_mask, self.buf_total, MAX_OBJECT, self.position is not None, self.call))
            elif c == C_POSITION:
                fm.unpack_pos(b[1:8])
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
        if obj in self.sessions:
            return self._err(obj, ERR_BUSY)
        if len(self.sessions) >= 1:      # un solo oggetto alla volta in RAM
            return self._err(obj, ERR_BUSY)
        if h["size"] > self.buf_total - self.used():
            return self._err(obj, ERR_NO_MEMORY)
        eta = pi.estimate_seconds(h["size"], self.rung, self.chip)
        self.sessions[obj] = dict(h=h, buf=bytearray(), state="rx_phone", credit=min(h["size"], WINDOW), last=self.t, next_credit_at=0)
        self.out.append(enc_event(E_BEGIN_OK, obj, self.sessions[obj]["credit"], int(eta + 0.5), self.rung))

    def _cancel(self, obj):
        s = self.sessions.pop(obj, None)
        if s is None:
            return self._err(obj, ERR_UNKNOWN_OBJ)
        self.staged = [x for x in self.staged if x != obj]
        if self.radio and self.radio["obj"] == obj:
            self.radio = None
        self.out.append(enc_event(E_DONE, obj, DONE_CANCELLED))

    def _resume(self, obj):
        s = self.sessions.get(obj)
        if s is None:
            return self._err(obj, ERR_UNKNOWN_OBJ)
        if s["state"] == "staged":      # i dati erano gia' tutti arrivati: la notifica si era persa nell'interruzione
            if self.radio and self.radio["obj"] == obj:
                r = self.radio
                pct = min(99, int((self.t - r["start"]) / r["dur"] * 100))
                return self.out.append(enc_event(E_PROGRESS, obj, pct, self.rung, int(r["dur"] * (100 - pct) / 100)))
            return self.out.append(enc_event(E_STAGED, obj))
        s["last"] = self.t
        s["credit"] = min(s["h"]["size"] - len(s["buf"]), WINDOW)
        self.out.append(enc_event(E_RESUME, obj, len(s["buf"]), s["credit"]))

    def _rx_ack(self, obj):
        self.rx_sessions.pop(obj, None)

    # -- dati dal telefono (scrittura senza risposta)
    def on_data(self, b):
        try:
            obj, off, payload = dec_data(b)
        except BadFrame:
            self.stats["bad_frames"] += 1
            return
        s = self.sessions.get(obj)
        if s is None or s["state"] != "rx_phone":
            return
        if off != len(s["buf"]) or len(payload) > s["credit"]:
            self.stats["dropped_out_of_order"] += 1     # fuori ordine o oltre il credito: si scarta, il telefono riparte da RESUME
            return
        s["buf"] += payload
        s["credit"] -= len(payload)
        s["last"] = self.t
        h = s["h"]
        if len(s["buf"]) == h["size"]:
            if zlib.crc32(bytes(s["buf"])) & 0xFFFFFFFF != h["crc"]:
                self.sessions.pop(obj)
                return self._err(obj, ERR_CRC)
            s["state"] = "staged"
            self.staged.append(obj)
            self.out.append(enc_event(E_STAGED, obj))
        elif s["credit"] == 0:
            s["credit"] = min(h["size"] - len(s["buf"]), WINDOW)
            self.out.append(enc_event(E_CREDIT, obj, s["credit"], len(s["buf"])))

    # -- radio (modello)
    def tick(self, dt):
        self.t += dt
        for obj, s in list(self.sessions.items()):     # sessione abbandonata dal telefono: si libera la RAM
            if s["state"] == "rx_phone" and self.t - s["last"] > RESUME_TIMEOUT_S:
                self.sessions.pop(obj)
        if self.radio is None and self.staged:
            obj = self.staged.pop(0)
            s = self.sessions[obj]
            dur = pi.estimate_seconds(s["h"]["size"], self.rung, self.chip)
            self.radio = dict(obj=obj, start=self.t, dur=dur, last_pct=0, last_evt=self.t)
        if self.radio:
            r = self.radio
            pct = min(100, int((self.t - r["start"]) / r["dur"] * 100))
            if pct >= 100:
                s = self.sessions.pop(r["obj"])
                h = s["h"]
                status = DONE_DELIVERED if self.radio_ok else DONE_FAILED
                if self.radio_ok:
                    self.radio_log.append(dict(obj=r["obj"], kind=h["kind"], data=bytes(s["buf"]), dest=h["dest"], name=h["name"], call=self.call, position=self.position, rung=self.rung))
                self.out.append(enc_event(E_DONE, r["obj"], status))
                self.radio = None
            elif pct - r["last_pct"] >= 10 and self.t - r["last_evt"] >= 2.0:
                r["last_pct"], r["last_evt"] = pct, self.t
                self.out.append(enc_event(E_PROGRESS, r["obj"], pct, self.rung, int(r["dur"] * (100 - pct) / 100)))

    def radio_received(self, obj, kind, data, from_call):
        """Un oggetto arrivato dalla radio: si offre al telefono (E_RX) e si manda a pezzi."""
        crc = zlib.crc32(data) & 0xFFFFFFFF
        self.out.append(enc_rx(obj, kind, len(data), crc, from_call))
        self.rx_sessions[obj] = data
        self.out_data.append((obj, bytes(data), 0))


# ------------------------------------------------------------------------------------------------------------------ il telefono
class Phone:
    def __init__(self, link, bridge):
        self.link, self.b = link, bridge
        self.info = None
        self.tx = {}          # obj -> dict
        self.events = []
        self.received = {}    # oggetti arrivati dalla scheda: obj -> dict
        self.errors = []
        self.bytes_resent = 0

    def hello(self):
        self.link.to_node.append(("cmd", enc_hello()))

    def set_position(self, pos):
        self.link.to_node.append(("cmd", enc_position(pos)))

    def send(self, obj, kind, data, dest, name="", **kw):
        self.tx[obj] = dict(data=bytes(data), sent=0, credit=0, state="begin", eta=None, done=None)
        self.link.to_node.append(("cmd", enc_begin(obj, kind, data, dest, name, **kw)))

    def cancel(self, obj):
        self.link.to_node.append(("cmd", enc_obj_cmd(C_CANCEL, obj)))

    def reconnect(self):
        """Dopo un'interruzione si chiede alla scheda a che punto e' ogni oggetto in invio."""
        for obj, t in self.tx.items():
            if t["state"] in ("sending", "begin", "staged"):
                t["credit"] = 0
                self.link.to_node.append(("cmd", enc_obj_cmd(C_RESUME, obj)))

    bad_events = 0

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
            t["credit"], t["eta"], t["rung"], t["state"] = f[0], f[1], f[2], "sending"
        elif code == E_CREDIT:
            t["credit"] = f[0]
        elif code == E_RESUME:
            self.bytes_resent += max(0, t["sent"] - f[0])
            t["sent"], t["credit"], t["state"] = f[0], f[1], "sending"
        elif code == E_STAGED:
            t["state"] = "staged"
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
        for obj, t in self.tx.items():
            while t["state"] == "sending" and t["credit"] > 0 and t["sent"] < len(t["data"]) and n < max_pkts:
                size = min(self.link.att_payload - DATA_HDR, t["credit"], len(t["data"]) - t["sent"])
                self.link.to_node.append(("data", enc_data(obj, t["sent"], t["data"][t["sent"]:t["sent"] + size])))
                t["sent"] += size
                t["credit"] -= size
                n += 1


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
            down_until = pending[0][1]
            pending.pop(0)
        if not link.up and down_until is not None and t >= down_until:
            link.restore()
            down_until = None
            phone.reconnect()
        if link.up:
            if hook:
                hook(t, phone, bridge)
            for _ in range(link.ppe):
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
    print(p.tx[1]["state"], p.tx[1]["eta"], len(b.radio_log))
