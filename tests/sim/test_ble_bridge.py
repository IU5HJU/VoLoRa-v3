"""Prove del ponte BLE telefono <-> scheda (specifica docs/ble-telefono.md): python3 -I tests/sim/test_ble_bridge.py"""
import os
import random
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import ble_bridge as bb  # noqa: E402
import protocollo_immagini as pi  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


def rig(mtu=185, pos=True, **kw):
    link = bb.BleLink(mtu=mtu)
    br = bb.BleBridge(position={"loc": "JN53ab"} if pos else None, **kw)
    return link, br, bb.Phone(link, br)


def payload(n, seed=1):
    r = random.Random(seed)
    return bytes(r.getrandbits(8) for _ in range(n))


# codec
d = payload(300)
b = bb.enc_begin(7, bb.KIND_IMAGE, d, "IK5XYZ", "foto.jpg", 160, 120, (200, 600, 1200))
h = bb.dec_begin(b)
check(h["obj"] == 7 and h["kind"] == 2 and h["size"] == 300 and h["crc"] == zlib.crc32(d) & 0xFFFFFFFF and h["dest"] == "IK5XYZ" and h["name"] == "foto.jpg" and h["layer_ends"] == [200, 600, 1200] and (h["width"], h["height"]) == (160, 120), "BEGIN: codifica e decodifica di tutti i campi (immagine a livelli)")
check(bb.dec_data(bb.enc_data(9, 70000, b"abc")) == (9, 70000, b"abc"), "DATA: oggetto, offset a 24 bit, byte")
ev = [(bb.E_BEGIN_OK, 3, (2048, 14, 5)), (bb.E_ERR, 3, (bb.ERR_BUSY,)), (bb.E_CREDIT, 3, (2048, 4096)), (bb.E_STAGED, 3, ()), (bb.E_PROGRESS, 3, (50, 5, 30)), (bb.E_DONE, 3, (0,)), (bb.E_RESUME, 3, (1000, 2048))]
check(all(bb.dec_event(bb.enc_event(c, o, *f)) == (c, o, list(f)) for c, o, f in ev), "eventi: tutti si decodificano come sono stati scritti")
inf = bb.dec_info(bb.enc_info("SX1262", 0xFFE, 32768, 65536, True, "IU5HJU"))
check(inf == dict(version=1, chip="SX1262", rung_mask=0xFFE, buf_total=32768, max_obj=65536, position_known=True, call="IU5HJU"), "INFO: chip, maschera dei gradini, memoria, tetto, posizione nota, nominativo")

# testo
link, br, ph = rig()
ph.hello()
ph.send(1, bb.KIND_TEXT, "Ciao dal telefono, qui IU5HJU".encode(), "IK5XYZ")
bb.run(link, br, ph, 30)
check(ph.info and ph.info["call"] == "IU5HJU" and ph.tx[1]["state"] == "done" and ph.tx[1]["done"] == bb.DONE_DELIVERED, "testo: INFO, invio e consegna in radio")
r = br.radio_log[0]
check(r["data"] == "Ciao dal telefono, qui IU5HJU".encode() and r["dest"] == "IK5XYZ" and r["call"] == "IU5HJU" and r["position"] == {"loc": "JN53ab"}, "in radio partono i byte, il destinatario, il nominativo e la posizione (regola fissa del progetto)")

# file e immagine di vari formati, con MTU diversi
for mtu in (23, 100, 185, 247):
    link, br, ph = rig(mtu=mtu)
    data = payload(20000, mtu)
    ph.send(2, bb.KIND_FILE, data, "IK5XYZ", "dati.bin")
    t = bb.run(link, br, ph, 400)
    ok = br.radio_log and br.radio_log[0]["data"] == data
    check(ok and ph.tx[2]["state"] == "done", f"file di 20 kB con MTU {mtu}: byte identici in radio")
    if mtu in (23, 247):
        staged_at = next(i for i, e in enumerate(ph.events) if e[0] == bb.E_STAGED)
        print(f"   MTU {mtu}: {len(ph.events)} eventi")
# il BLE non e' il collo di bottiglia: il tempo di carico sulla scheda e' molto minore di quello della radio
link, br, ph = rig(mtu=23)
data = payload(20000, 5)
ph.send(3, bb.KIND_FILE, data, "IK5XYZ")
tt = 0.0
while ph.tx[3]["state"] != "staged" and tt < 200:
    bb.run(link, br, ph, 0.3)
    tt += 0.3
radio_s = pi.estimate_seconds(20000, 5, "SX1278")
check(ph.tx[3]["state"] == "staged" and tt < radio_s, f"20 kB con MTU 23 (il peggiore) arrivano sulla scheda in circa {tt:.0f} s, la radio a R5 ne vuole {radio_s:.0f}")
check(ph.tx[3]["eta"] == int(radio_s + 0.5), "la scheda dice al telefono il tempo stimato della radio (ETA) prima di ricevere i dati")

# controllo di flusso: mai oltre il credito
link, br, ph = rig(mtu=247)
ph.send(4, bb.KIND_FILE, payload(10000, 2), "IK5XYZ")
bb.run(link, br, ph, 60)
check(br.stats["dropped_out_of_order"] == 0 and br.stats["bad_frames"] == 0, "il telefono rispetta il credito: nessun pacchetto scartato")
check(sum(1 for e in ph.events if e[0] == bb.E_CREDIT) >= 3, "il credito si rinnova a finestre da 2 kB")

# interruzione e ripresa: nessun byte confermato viene rimandato, il file arriva identico
link, br, ph = rig(mtu=100)
data = payload(12000, 8)
ph.send(5, bb.KIND_FILE, data, "IK5XYZ", "grande.bin")
bb.run(link, br, ph, 60, drops=[(0.3, 3.0), (3.6, 6.0)])
check(br.radio_log and br.radio_log[0]["data"] == data, "due interruzioni del BLE durante l'invio: il file arriva identico in radio")
check(0 < ph.bytes_resent <= 2 * 4 * 100 and ph.tx[5]["state"] == "done", f"dopo l'interruzione si riparte dall'offset della scheda: rimandati solo {ph.bytes_resent} byte (quelli in volo), non tutto il file")

# annullamento
link, br, ph = rig()
ph.send(6, bb.KIND_FILE, payload(6000, 3), "IK5XYZ")
bb.run(link, br, ph, 0.5)
ph.cancel(6)
bb.run(link, br, ph, 2)
check(ph.tx[6]["state"] == "done" and ph.tx[6]["done"] == bb.DONE_CANCELLED and not br.sessions and not br.radio_log, "annullamento: la RAM si libera e niente parte in radio")
ph.send(7, bb.KIND_TEXT, b"dopo", "IK5XYZ")
bb.run(link, br, ph, 30)
check(br.radio_log and br.radio_log[0]["data"] == b"dopo", "dopo l'annullamento si puo' inviare ancora")

# annullamento durante la trasmissione radio
link, br, ph = rig()
ph.send(8, bb.KIND_FILE, payload(20000, 9), "IK5XYZ")
bb.run(link, br, ph, 15)
check(br.radio is not None, "la radio sta trasmettendo")
ph.cancel(8)
bb.run(link, br, ph, 1)
check(br.radio is None and not br.radio_log and ph.tx[8]["done"] == bb.DONE_CANCELLED, "annullamento anche durante la trasmissione radio")
check(any(e[0] == bb.E_PROGRESS for e in ph.events), "durante la trasmissione il telefono riceve l'avanzamento")

# errori
link, br, ph = rig(pos=False)
ph.send(10, bb.KIND_TEXT, b"x", "IK5XYZ")
bb.run(link, br, ph, 2)
check((10, bb.ERR_NO_POSITION) in ph.errors, "senza posizione la scheda rifiuta: nominativo, rapporto e posizione sono sempre trasmessi")
ph.set_position({"lat": 43.7696, "lon": 11.2558})
ph.send(11, bb.KIND_TEXT, b"x", "IK5XYZ")
bb.run(link, br, ph, 20)
check(ph.tx[11]["state"] == "done" and abs(br.position["lat"] - 43.7696) < 0.001, "la posizione GPS del telefono (assoluta) basta")
link, br, ph = rig()
ph.send(12, bb.KIND_TEXT, payload(bb.MAX_TEXT + 1), "IK5XYZ")
ph.send(13, bb.KIND_FILE, payload(bb.MAX_OBJECT + 1, 1), "IK5XYZ")
ph.send(14, 9, b"x", "IK5XYZ")
bb.run(link, br, ph, 2)
check((12, bb.ERR_TOO_BIG) in ph.errors and (13, bb.ERR_TOO_BIG) in ph.errors and (14, bb.ERR_BAD_KIND) in ph.errors, "testo oltre 1 kB, oggetto oltre 64 kB e tipo sconosciuto: rifiutati")
link, br, ph = rig(buf_total=1000)
ph.send(15, bb.KIND_FILE, payload(2000, 2), "IK5XYZ")
bb.run(link, br, ph, 2)
check((15, bb.ERR_NO_MEMORY) in ph.errors, "oggetto piu' grande della RAM libera: NO_MEMORY, il telefono lo sa subito")
link, br, ph = rig()
ph.send(16, bb.KIND_FILE, payload(5000, 4), "IK5XYZ")
ph.send(17, bb.KIND_TEXT, b"seconda", "IK5XYZ")
bb.run(link, br, ph, 2)
check((17, bb.ERR_BUSY) in ph.errors, "un solo oggetto alla volta: il secondo riceve BUSY")
# CRC sbagliato
link, br, ph = rig()
ph.send(18, bb.KIND_FILE, payload(3000, 6), "IK5XYZ")
ph.tx[18]["data"] = bytes([ph.tx[18]["data"][0] ^ 1]) + ph.tx[18]["data"][1:]     # un byte rovinato dopo il calcolo del CRC
bb.run(link, br, ph, 10)
check((18, bb.ERR_CRC) in ph.errors and not br.radio_log and not br.sessions, "CRC sbagliato: errore e niente in radio")
# radio che fallisce
link, br, ph = rig(radio_ok=False)
ph.send(19, bb.KIND_TEXT, b"x", "IK5XYZ")
bb.run(link, br, ph, 20)
check(ph.tx[19]["done"] == bb.DONE_FAILED, "trasmissione radio fallita: il telefono lo sa (DONE con esito 1)")
# sessione abbandonata
link, br, ph = rig()
ph.send(20, bb.KIND_FILE, payload(6000, 7), "IK5XYZ")
bb.run(link, br, ph, 0.5, drops=[(0.2, 999)])
bb.run(link, br, ph, 0, )
link.up = True
br.tick(bb.RESUME_TIMEOUT_S + 1)
check(not br.sessions, "telefono sparito per piu' di 60 s: la scheda libera la RAM")

# ricezione dalla radio verso il telefono
link, br, ph = rig(mtu=185)
img = payload(5000, 11)
br.radio_received(0xABCD, bb.KIND_IMAGE, img, "IK5XYZ")
bb.run(link, br, ph, 10)
rx = ph.received[0xABCD]
check(rx["ok"] is True and bytes(rx["buf"]) == img and rx["h"]["from_call"] == "IK5XYZ" and 0xABCD not in br.rx_sessions, "oggetto ricevuto dalla radio: arriva al telefono, il CRC torna e la scheda libera la copia")

# input malformati: nessuna eccezione
r = random.Random(99)
link, br, ph = rig()
try:
    for _ in range(3000):
        n = r.randrange(0, 40)
        junk = bytes(r.getrandbits(8) for _ in range(n))
        if junk and r.random() < 0.5:
            junk = bytes([r.choice((1, 2, 0x10, 0x12, 0x13, 0x14, 0x99))]) + junk[1:]
        br.on_command(junk)
        br.on_data(junk)
    check(True, "3000 frame casuali sulla scheda: nessuna eccezione")
except Exception as e:  # noqa: BLE001
    check(False, f"frame casuali: {e!r}")
check(br.stats["bad_frames"] > 1000 and not br.radio_log, "i frame sbagliati sono contati e rifiutati, niente parte in radio")
try:
    for _ in range(2000):
        n = r.randrange(0, 30)
        junk = bytes(r.getrandbits(8) for _ in range(n))
        if junk and r.random() < 0.7:
            junk = bytes([r.choice((0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88))]) + junk[1:]
        ph.on_event(junk) if junk else None
        ph.on_data(junk)
    check(ph.bad_events > 100, f"2000 eventi e dati casuali sul telefono: nessuna eccezione, {ph.bad_events} scartati")
except Exception as e:  # noqa: BLE001
    check(False, f"eventi casuali: {e!r}")

print("ponte BLE: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
