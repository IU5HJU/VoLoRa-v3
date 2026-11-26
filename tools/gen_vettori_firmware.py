#!/usr/bin/env python3
"""Genera i VETTORI DI PROVA del firmware V3 dal riferimento Python (tools/ble_bridge.py, tools/protocollo_immagini.py): il nucleo C++ (firmware/v3/src) deve
riprodurli byte per byte (firmware/v3/tests/test_conformance.cpp). Deterministico: tests/sim/test_vettori_firmware.py controlla che i file nel repository siano aggiornati.
  python3 tools/gen_vettori_firmware.py [cartella-di-uscita]      (di base firmware/v3/tests/vettori)"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ble_bridge as bb  # noqa: E402
import frame_mesh as fm  # noqa: E402
import limiti_chip as lc  # noqa: E402
import protocollo_immagini as pi  # noqa: E402
import sim_immagini as si  # noqa: E402

CALL = "IU5HJU"


class Traccia(bb.BleBridge):
    """Il ponte di riferimento che scrive in un file tutto quello che entra e che esce."""

    def __init__(self, righe, **kw):
        super().__init__(**kw)
        self.righe = righe
        righe.append(f"init call={self.call} chip={self.chip} rung={self.rung} mask={self.rung_mask} pos={1 if self.position else 0} ok={1 if self.radio_ok else 0} "
                     f"retx={','.join(str(x) for x in sorted(self.retx_plan)) or '-'}")

    def _notify(self, frame):
        if self.connected:
            self.righe.append("out " + bytes(frame).hex())
        super()._notify(frame)

    def on_command(self, b):
        if b and b[0] == bb.C_BEGIN:                      # il tempo di radio stimato, esatto, per il modello a tempo del C++
            try:
                h = bb.dec_begin(b)
                self.righe.append("dur " + repr(pi.estimate_seconds(h["size"], self.rung, self.chip)))
            except (bb.BadFrame, ValueError, IndexError):
                pass
        self.righe.append("cmd " + (bytes(b).hex() or "-"))
        super().on_command(b)

    def on_data(self, b):
        self.righe.append("data " + (bytes(b).hex() or "-"))
        super().on_data(b)

    def tick(self, dt):
        self.righe.append("tick " + repr(dt))
        super().tick(dt)

    def on_disconnect(self):
        self.righe.append("disc")
        super().on_disconnect()

    def on_connect(self):
        self.righe.append("conn")
        super().on_connect()

    def radio_received(self, obj, kind, data, from_call):
        import zlib
        self.righe.append(f"rx {obj} {kind} {zlib.crc32(data) & 0xFFFFFFFF} {from_call} {len(data)}")
        return super().radio_received(obj, kind, data, from_call)

    def fine(self):
        s = self.stats
        self.righe.append(f"stats bad={s['bad_frames']} dropped={s['dropped']} maxheld={s['max_held']} pulls={s['pulls']} repulls={s['repulls']} sent={s['blocks_sent']} stalled={s['stalled_s']!r}")


def payload(n, seed):
    r = random.Random(seed)
    return bytes(r.getrandbits(8) for _ in range(n))


def scenario_telefono(nome, righe, size, mtu=185, kind=bb.KIND_FILE, retx=(), drops=(), seconds=90, cancel_at=None, pos=True, radio_ok=True, chip="SX1278", rung=5, begin_extra=None):
    link = bb.BleLink(mtu=mtu)
    br = Traccia(righe, call=CALL, chip=chip, position={"loc": "JN53ab"} if pos else None, rung=rung, radio_ok=radio_ok, retx=retx)
    ph = bb.Phone(link, br)
    ph.hello()
    if not pos:
        pass
    ph.send(7, kind, payload(size, size), "IK5XYZ", "prova.bin", width=160, height=120, layer_ends=(size // 3 // 16 * 16, size * 2 // 3 // 16 * 16, size) if size >= 600 else ())
    if cancel_at is None:
        bb.run(link, br, ph, seconds, drops=drops)
    else:
        bb.run(link, br, ph, cancel_at)
        ph.cancel(7)
        bb.run(link, br, ph, 2)
    br.fine()


def _h(b):
    return bytes(b).hex() or "."


def resumen(d):
    """Riassunto canonico di un frame decodificato dal riferimento Python: il C++ deve stampare la stessa riga (tests/test_frames.cpp)."""
    if d is None:
        return "NONE"
    t = d["tipo"]
    s = f"{t} {d['sess']} {d['flags']} {d['len']}"
    pos = lambda: _h(d["pos_raw"]) if "pos_raw" in d else "-"     # noqa: E731
    opt = lambda: _h(d["opts_raw"]) if "opts_raw" in d else "-"   # noqa: E731
    if t == 0:
        s += f" {_h(d['call'].encode())} {1 if d['chip'] == 'SX1262' else 0} {d['rung_mask']} {d['max_frame']} {d['mem_kb']} {int(d['reply'])} {d.get('rssi', '-')} {d.get('snr', '-')} {pos()} {opt()}"
    elif t == 1:
        s += f" {d['rung']} {d['idx']} {d['count']}"
    elif t == 2:
        s += f" {d['rung']} {d['expected']} {d['received']} {d['rssi']} {d['snr']}"
    elif t == 3:
        s += f" {d['rung']} {d['k']} {d['repeat']}"
    elif t == 4:
        s += f" {d['rung']}"
    elif t == 5:
        s += f" {_h(d['call'].encode())} {d['objtype']} {d['size']} {d['piece']} {d['npieces']} {d['w']} {d['h']} {','.join(str(e) for e in d['layer_ends']) or '-'} {d['crc']} {pos()} {opt()}"
    elif t == 6:
        s += f" {d['layers']} {d['window']} {d['k']}"
    elif t == 7:
        s += f" {d['offset']} {int(d['relayed'])} {d['hops']} {_h(d['payload'])}"
    elif t == 8:
        s += f" {d['base']} {d['bitmap']} {d['rssi']} {d['snr']} {d['loss_pct']} {d['layers_done']}"
    elif t == 10:
        s += f" {_h(d['call'].encode())} {d['layers']} {d['nbytes']} {d['crc']}"
    elif t == 11:
        s += f" {d['reason']}"
    return s


def genera_frames(out):
    """frames_enc.txt: ingressi e frame attesi di ogni codificatore; frames_dec.txt: frame (validi, sbagliati, mutati a caso) e il loro riassunto."""
    r = random.Random(2026)
    enc = []
    pos_l, pos_g = fm.pack_pos({"loc": "JN53ab"}), fm.pack_pos({"lat": 43.7696, "lon": 11.2558})
    opts = fm.pack_opts([fm.opt_revision(), (fm.OPT_PROFILES, bytes([1, 0b101])), (fm.OPT_ID32, (0x12345678).to_bytes(4, "big"))])
    ch = lambda b: b.hex() or "-"   # noqa: E731
    for sess in (0, 1, 0x1234, 65535):
        for call in ("IU5HJU", "I", "IZ5/ABC-1"):
            for chip in ("SX1278", "SX1262"):
                for reply, meas, pos, op in ((False, None, None, None), (True, (-100, 5), None, None), (True, (-128, 127), pos_l, None), (False, None, pos_g, opts), (True, (-30, -3), pos_l, opts)):
                    b = si.enc_hello(sess, call, chip, r.getrandbits(16), r.choice((64, 255)), r.getrandbits(16), reply=reply, rssi=None if meas is None else meas[0], snr=None if meas is None else meas[1],
                                     pos={"loc": "JN53ab"} if pos is pos_l else ({"lat": 43.7696, "lon": 11.2558} if pos is pos_g else None), opts=list(fm.unpack_opts(op).items()) if op else None)
                    d = si.decode(b)
                    enc.append(f"HELLO {sess} {call.encode().hex()} {1 if chip == 'SX1262' else 0} {d['rung_mask']} {d['max_frame']} {d['mem_kb']} {int(reply)} "
                               f"{'-' if meas is None else meas[0]} {'-' if meas is None else meas[1]} {ch(pos) if pos else '-'} {ch(op) if op else '-'} {b.hex()}")
    for sess in (0, 7, 65535):
        enc.append(f"PROBE {sess} 5 3 8 25 {si.enc_probe(sess, 5, 3, 8, 25).hex()}")
        enc.append(f"PROBE {sess} 14 0 255 0 {si.enc_probe(sess, 14, 0, 255, 0).hex()}")
        enc.append(f"PROBE_REPORT {sess} 5 8 7 -101 4 {si.enc_probe_report(sess, 5, 8, 7, -101, 4).hex()}")
        enc.append(f"PROBE_REPORT {sess} 10 8 0 -140 -25 {si.enc_probe_report(sess, 10, 8, 0, -140, -25).hex()}")      # -140 si limita a -128, come nel Python
        enc.append(f"MODE_SET {sess} 6 4 3 {si.enc_mode_set(sess, 6, 4, 3).hex()}")
        enc.append(f"MODE_ACK {sess} 14 {si.enc_mode_ack(sess, 14).hex()}")
        enc.append(f"ACCEPT {sess} 3 16 4 {si.enc_accept(sess, 3, 16, 4).hex()}")
        enc.append(f"ABORT {sess} 1 {si.enc_abort(sess, 1).hex()}")
        for call in ("IU5HJU", "IK5XYZ"):
            enc.append(f"DONE {sess} {call.encode().hex()} 3 9577 {0xDEADBEEF} {si.enc_done(sess, call, 3, 9577, 0xDEADBEEF).hex()}")
    for sess in (0, 9, 0xBEEF):
        for ends in ((), (174,), (174, 315, 598), tuple(range(1, 17))):
            for pos, op in ((None, None), (pos_l, None), (pos_g, opts)):
                b = si.enc_offer(sess, "IU5HJU", 2, 9577, 16, 599, 320, 240, list(ends), 0xCAFEBABE, pos=None if pos is None else fm.unpack_pos(pos), opts=list(fm.unpack_opts(op).items()) if op else None)
                enc.append(f"OFFER {sess} {'IU5HJU'.encode().hex()} 2 9577 16 599 320 240 {','.join(str(e) for e in ends) or '-'} {0xCAFEBABE} {ch(pos) if pos else '-'} {ch(op) if op else '-'} {b.hex()}")
        for off, fl, pl in ((0, 0, b"x" * 16), (65535, si.F_LAST_WINDOW | si.F_LAYER_END, b"\x00" * 48), (300, si.F_RETX | (3 << 5) | fm.F_RELAYED, bytes(range(32))), (1, 0, b"")):
            enc.append(f"DATA {sess} {off} {fl} {ch(pl)} {si.enc_data(sess, off, pl, fl).hex()}")
        for base, bm, rssi, snr, loss, lay, fl in ((0, 0, -100, 5, 0, 0, 0), (65535, (1 << 64) - 1, -128, 127, 100, 3, si.F_LAST_WINDOW), (12, 0xABCDEF0123456789, -77, -9, 37, 2, 0)):
            enc.append(f"STATUS {sess} {base} {bm} {rssi} {snr} {loss} {lay} {fl} {si.enc_status(sess, base, bm, rssi, snr, loss, lay, fl).hex()}")
    with open(os.path.join(out, "frames_enc.txt"), "w") as f:
        f.write("\n".join(enc) + "\n")
    # decodifica: i frame buoni, quelli troncati a ogni lunghezza, e 8000 mutazioni casuali
    buoni = [bytes.fromhex(e.split()[-1]) for e in enc]
    dec = []
    seen = set()

    def aggiungi(b):
        if b in seen:
            return
        seen.add(b)
        dec.append(f"{b.hex() or '-'} {resumen(si.decode(b))}")
    for b in buoni:
        aggiungi(b)
        for cut in range(0, len(b)):
            aggiungi(b[:cut])
    for _ in range(8000):
        b = bytearray(r.choice(buoni))
        for _ in range(r.randrange(1, 4)):
            k = r.randrange(5)
            if k == 0 and b:
                b[r.randrange(len(b))] = r.getrandbits(8)
            elif k == 1 and b:
                b[r.randrange(len(b))] ^= 1 << r.randrange(8)
            elif k == 2:
                b = b[:r.randrange(len(b) + 1)]
            elif k == 3:
                b += bytes(r.getrandbits(8) for _ in range(r.randrange(1, 6)))
            elif k == 4 and len(b) > 4:
                b[0] = (b[0] & 0xF0) | r.randrange(16)
        aggiungi(bytes(b))
    for _ in range(1500):
        aggiungi(bytes(r.getrandbits(8) for _ in range(r.randrange(0, 40))))
    with open(os.path.join(out, "frames_dec.txt"), "w") as f:
        f.write("\n".join(dec) + "\n")
    # maschere dei gradini (limiti dei chip dai datasheet)
    righe = []
    for chip in ("SX1278", "SX1262"):
        for tcxo in (0, 1):
            for khz in (144900, 150000, 400000, 410000, 430000, 433700, 433850, 433955, 440000, 525000, 868000, 960000):
                righe.append(f"mask {chip} {tcxo} {khz} {lc.rung_mask(chip, bool(tcxo), khz)}")
    for rid in range(len(pi.RUNGS)):
        for chip in ("SX1278", "SX1262"):
            for ppm in (0.5, 2.0, 2.5, 4.4, 4.6, 9.0, 10.0, 17.9, 18.1, 36.0, 49.0, 51.0):
                righe.append(f"rung {rid} {chip} 433700 {ppm!r} {int(lc.rung_support(rid, chip, 433700, ppm)[0])}")
    for ca in ("SX1278", "SX1262"):
        for cb in ("SX1278", "SX1262"):
            for ta in (0, 1):
                for tb in (0, 1):
                    ma, mb = lc.rung_mask(ca, bool(ta)), lc.rung_mask(cb, bool(tb))
                    righe.append(f"common {ca} {ma} {cb} {mb} {lc.common_mask(ca, ma, cb, mb)}")
    with open(os.path.join(out, "limits.txt"), "w") as f:
        f.write("\n".join(righe) + "\n")
    return ["frames_enc", "frames_dec", "limits"]


def genera(out):
    os.makedirs(out, exist_ok=True)
    tutti = {}
    # 1. scenari guidati dal telefono (Phone + BleLink) registrati al confine del ponte
    sc = {
        "testo": dict(size=29, kind=bb.KIND_TEXT, seconds=30),
        "file20k": dict(size=20000, seconds=60),
        "file64k": dict(size=65536, seconds=90, mtu=247),
        "retx": dict(size=8000, retx=(1, 4), seconds=60),
        "interruzioni": dict(size=12000, mtu=100, drops=[(3.0, 9.0), (14.0, 16.0)], seconds=90),
        "sparito": dict(size=20000, drops=[(1.0, 500.0)], seconds=90),
        "annulla": dict(size=20000, cancel_at=6.0),
        "senza_posizione": dict(size=100, pos=False, seconds=5),
        "radio_fallita": dict(size=3000, radio_ok=False, seconds=30),
        "sx1262_r10": dict(size=2000, chip="SX1262", rung=10, seconds=200),
        "fsk_r1": dict(size=5000, rung=1, seconds=60),
    }
    for nome, kw in sc.items():
        righe = []
        scenario_telefono(nome, righe, **kw)
        tutti[nome] = righe
    # 2. errori e frame strani, ingressi diretti
    righe = []
    br = Traccia(righe, call=CALL, position={"loc": "JN53ab"})
    ok = bb.enc_begin(1, bb.KIND_FILE, b"x" * 100, "IK5XYZ", "a.bin")
    for cmd in (b"", bytes([bb.C_HELLO, 1]), bytes([bb.C_POSITION]), bytes([bb.C_POSITION]) + bytes([2]) + b"ABCDEF", bytes([bb.C_POSITION, 0]) + bytes([0xFF]) * 6,
                bytes([bb.C_POSITION]) + fm.pack_pos({"lat": 43.0, "lon": 11.0}), bytes([bb.C_POSITION]) + fm.pack_pos({"loc": "JN53ab"}) + b"x", b"\x99",
                bb.enc_begin(2, 9, b"x" * 10, "IK5XYZ"), bb.enc_begin(3, bb.KIND_TEXT, b"x" * 2000, "IK5XYZ"), bb.enc_begin(4, bb.KIND_FILE, b"x" * 70000, "IK5XYZ"),
                bb.enc_begin(5, bb.KIND_FILE, b"", "IK5XYZ"), ok[:-1], ok + b"\x00", bytes([bb.C_CANCEL, 0]), bytes([bb.C_CANCEL, 0, 1, 2]), bb.enc_obj_cmd(bb.C_CANCEL, 77),
                bb.enc_obj_cmd(bb.C_RESUME, 77), bb.enc_obj_cmd(bb.C_RX_ACK, 77), ok, bb.enc_begin(6, bb.KIND_FILE, b"y" * 50, "IZ5AAA"), bb.enc_obj_cmd(bb.C_CANCEL, 1),
                bb.enc_obj_cmd(bb.C_RESUME, 1), bb.enc_begin(8, bb.KIND_IMAGE, b"i" * 3000, "IK5XYZ", "foto.jpg", 160, 120, (1000, 2000, 3000))):
        br.on_command(cmd)
    for d in (b"", b"\x00\x01\x00\x00\x00", bb.enc_data(99, 0, b"x"), bb.enc_data(1, 0, b"x" * 10), bb.enc_data(8, 0, b"x" * 100)):
        br.on_data(d)
    for _ in range(300):
        br.tick(0.03)
    br.fine()
    tutti["ingressi"] = righe
    # 3. oggetto dalla radio verso il telefono
    righe = []
    br = Traccia(righe, call=CALL, position={"loc": "JN53ab"})
    br.radio_received(0xABCD, bb.KIND_IMAGE, payload(5000, 11), "IK5XYZ")
    br.on_command(bb.enc_obj_cmd(bb.C_RX_ACK, 0xABCD))
    br.on_disconnect()
    br.radio_received(1, bb.KIND_TEXT, b"ciao", "IK5XYZ")
    br.fine()
    tutti["rx"] = righe
    # 4. fuzz: 4000 frame casuali (la parte piu' severa: stesso esito su qualunque ingresso)
    righe = []
    br = Traccia(righe, call=CALL, position={"loc": "JN53ab"})
    r = random.Random(1234)
    validi = [bb.enc_begin(r.randrange(1, 60000), r.choice((0, 1, 2)), payload(r.choice((50, 1500, 5000)), 1), "IK5XYZ", "n"), bb.enc_obj_cmd(bb.C_RESUME, 1), bb.enc_obj_cmd(bb.C_CANCEL, 1)]
    for i in range(4000):
        n = r.randrange(0, 40)
        junk = bytes(r.getrandbits(8) for _ in range(n))
        if junk and r.random() < 0.5:
            junk = bytes([r.choice((1, 2, 0x10, 0x12, 0x13, 0x14, 0x99))]) + junk[1:]
        if r.random() < 0.05:
            junk = r.choice(validi)
            if r.random() < 0.5:
                junk = bytearray(junk)
                junk[r.randrange(len(junk))] ^= 1 << r.randrange(8)
                junk = bytes(junk)
        (br.on_command if r.random() < 0.7 else br.on_data)(junk)
        if r.random() < 0.3:
            br.tick(0.5)
    br.fine()
    tutti["fuzz"] = righe
    for nome, righe in tutti.items():
        with open(os.path.join(out, nome + ".txt"), "w") as f:
            f.write("\n".join(righe) + "\n")
    # 5. stime dei tempi (porta in C++ di estimate_seconds)
    with open(os.path.join(out, "estimate.txt"), "w") as f:
        for chip in ("SX1278", "SX1262"):
            for rid in range(len(pi.RUNGS)):
                for size in (1, 29, 255, 1024, 5000, 20000, 65536):
                    f.write(f"{chip} {rid} {size} {pi.estimate_seconds(size, rid, chip)!r} {pi.chunk_size(rid, chip)} {pi.frame_airtime_s(rid, 255)!r}\n")
    return sorted(tutti) + ["estimate"] + genera_frames(out)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "firmware", "v3", "tests", "vettori")
    print("generati:", ", ".join(genera(out)))
