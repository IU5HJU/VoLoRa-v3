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
import protocollo_immagini as pi  # noqa: E402

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
    return sorted(tutti) + ["estimate"]


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "firmware", "v3", "tests", "vettori")
    print("generati:", ", ".join(genera(out)))
