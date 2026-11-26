"""Prove del ponte BLE telefono <-> scheda (specifica docs/ble-telefono.md): il BUFFER e' il telefono. python3 -I tests/sim/test_ble_bridge.py"""
import os
import random
import struct
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
h = bb.dec_begin(bb.enc_begin(7, bb.KIND_IMAGE, d, "IK5XYZ", "foto.jpg", 160, 120, (200, 600, 1200)))
check(h["obj"] == 7 and h["kind"] == 2 and h["size"] == 300 and h["crc"] == zlib.crc32(d) & 0xFFFFFFFF and h["dest"] == "IK5XYZ" and h["name"] == "foto.jpg" and h["layer_ends"] == [200, 600, 1200] and (h["width"], h["height"]) == (160, 120), "BEGIN: codifica e decodifica di tutti i campi (immagine a livelli)")
check(bb.dec_data(bb.enc_data(9, 70000, b"abc")) == (9, 70000, b"abc"), "DATA: oggetto, offset a 24 bit, byte")
ev = [(bb.E_BEGIN_OK, 3, (14, 5, 1024)), (bb.E_ERR, 3, (bb.ERR_BUSY,)), (bb.E_PROGRESS, 3, (50, 5, 30)), (bb.E_DONE, 3, (0,)), (bb.E_PULL, 3, (4096, 1024))]
check(all(bb.dec_event(bb.enc_event(c, o, *f)) == (c, o, list(f)) for c, o, f in ev), "eventi: tutti si decodificano come sono stati scritti")
inf = bb.dec_info(bb.enc_info("SX1262", 0xFFE, 1024, 65536, True, "IU5HJU"))
check(inf == dict(version=1, chip="SX1262", rung_mask=0xFFE, block=1024, max_obj=65536, position_known=True, call="IU5HJU"), "INFO: chip, maschera dei gradini, blocco, tetto, posizione nota, nominativo")

# testo
link, br, ph = rig()
ph.hello()
ph.send(1, bb.KIND_TEXT, "Ciao dal telefono, qui IU5HJU".encode(), "IK5XYZ")
bb.run(link, br, ph, 30)
check(ph.info and ph.info["call"] == "IU5HJU" and ph.tx[1]["state"] == "done" and ph.tx[1]["done"] == bb.DONE_DELIVERED, "testo: INFO, invio e consegna in radio")
r = br.radio_log[0]
check(r["data"] == "Ciao dal telefono, qui IU5HJU".encode() and r["dest"] == "IK5XYZ" and r["call"] == "IU5HJU" and r["position"] == {"loc": "JN53ab"}, "in radio partono i byte, il destinatario, il nominativo e la posizione (regola fissa del progetto)")
check(r["crc"] == zlib.crc32(r["data"]) & 0xFFFFFFFF, "il CRC dell'oggetto dato dal telefono e' quello dei byte trasmessi")

# la scheda non tiene l'oggetto: la RAM non supera 3 blocchi qualunque sia la dimensione e l'MTU
for mtu in (23, 100, 185, 247):
    link, br, ph = rig(mtu=mtu)
    data = payload(20000, mtu)
    ph.send(2, bb.KIND_FILE, data, "IK5XYZ", "dati.bin")
    bb.run(link, br, ph, 60 if mtu > 23 else 80)
    check(br.radio_log and br.radio_log[0]["data"] == data and ph.tx[2]["state"] == "done", f"file di 20 kB con MTU {mtu}: byte identici in radio")
    check(br.stats["max_held"] <= bb.CACHE_BLOCKS * bb.BLOCK, f"MTU {mtu}: RAM della scheda al massimo {br.stats['max_held']} byte (limite {bb.CACHE_BLOCKS * bb.BLOCK}), non 20000")
link, br, ph = rig(mtu=247)
data = payload(65536, 21)
ph.send(3, bb.KIND_FILE, data, "IK5XYZ")
bb.run(link, br, ph, 90)
check(br.sess is None and br.radio_log and br.radio_log[0]["data"] == data and br.stats["max_held"] <= 3072, "un oggetto di 64 kB (il tetto) passa con 3 kB di RAM sulla scheda")
check(br.stats["repulls"] == 0 and br.stats["pulls"] == 64, "senza perdite ogni blocco e' richiesto una volta sola (64 richieste)")

# il BLE non fa aspettare la radio (anche con l'MTU peggiore)
link, br, ph = rig(mtu=23)
ph.send(4, bb.KIND_FILE, payload(20000, 5), "IK5XYZ")
bb.run(link, br, ph, 80)
dur = pi.estimate_seconds(20000, 5, "SX1278")
check(br.stats["stalled_s"] < 0.1 * dur, f"MTU 23: la radio e' rimasta ferma ad aspettare il telefono solo {br.stats['stalled_s']:.1f} s su {dur:.0f}")
check(ph.tx[4]["eta"] == int(dur + 0.5), "la scheda dice al telefono il tempo stimato della radio (ETA) subito, all'inizio")
# a un gradino molto veloce (R3) la radio consuma piu' in fretta: serve MTU decente
link, br, ph = rig(mtu=185, rung=3)
ph.send(5, bb.KIND_FILE, payload(20000, 6), "IK5XYZ")
bb.run(link, br, ph, 30)
check(br.radio_log and br.stats["stalled_s"] < 0.2 * pi.estimate_seconds(20000, 3, "SX1278"), f"anche a R3 (7 s per 20 kB) con MTU 185 la radio aspetta poco ({br.stats['stalled_s']:.1f} s)")

# ritrasmissione selettiva: la scheda richiede di nuovo i blocchi che aveva liberato
link, br, ph = rig(mtu=185, retx=(1, 4))
data = payload(8000, 7)
ph.send(6, bb.KIND_FILE, data, "IK5XYZ")
bb.run(link, br, ph, 60)
check(br.radio_log and br.radio_log[0]["data"] == data and br.stats["repulls"] == 2 and br.stats["blocks_sent"] == 8 + 2, f"due blocchi da ritrasmettere: richiesti di nuovo al telefono ({br.stats['repulls']} richieste ripetute), {br.stats['blocks_sent']} blocchi in radio")
check(ph.bytes_resent == 2 * bb.BLOCK and br.stats["max_held"] <= 3072, "il telefono rimanda solo quei due blocchi e la RAM resta dentro i 3 kB")

# interruzione del BLE: la radio continua con la cache, poi aspetta; alla riconnessione si riprende
link, br, ph = rig(mtu=100)
data = payload(12000, 8)
ph.send(7, bb.KIND_FILE, data, "IK5XYZ", "grande.bin")
bb.run(link, br, ph, 90, drops=[(3.0, 9.0), (14.0, 16.0)])
check(br.radio_log and br.radio_log[0]["data"] == data and ph.tx[7]["state"] == "done", "due interruzioni del BLE durante la trasmissione: l'oggetto arriva identico in radio")
check(br.stats["stalled_s"] > 1.0 and br.stats["repulls"] == 0 and br.stats["max_held"] <= 3072, f"la radio ha aspettato {br.stats['stalled_s']:.1f} s l'interruzione, senza riscaricare blocchi gia' trasmessi")
# telefono assente troppo a lungo
link, br, ph = rig()
ph.send(8, bb.KIND_FILE, payload(20000, 9), "IK5XYZ")
bb.run(link, br, ph, 90, drops=[(1.0, 500.0)])
check(ph.tx[8]["state"] == "sending" and br.sess is None and br.radio_log == [] and not br.out, "telefono sparito per piu' di 60 s con la radio in attesa: la scheda abbandona (la RAM si libera)")
link.restore()
br.on_connect()
ph.reconnect()
bb.run(link, br, ph, 1)
check(ph.tx[8]["state"] == "done" and ph.tx[8]["done"] == bb.DONE_FAILED, "alla riconnessione tardiva il telefono sa com'e' finita (DONE fallito): la notifica persa si rida' con RESUME")
ph.send(80, bb.KIND_TEXT, b"x", "IK5XYZ")
ph.link.to_node.append(("cmd", bb.enc_obj_cmd(bb.C_RESUME, 555)))
bb.run(link, br, ph, 1)
check((555, bb.ERR_UNKNOWN_OBJ) in ph.errors, "RESUME di un oggetto mai visto: UNKNOWN_OBJ")

# annullamento
link, br, ph = rig()
ph.send(9, bb.KIND_FILE, payload(6000, 3), "IK5XYZ")
bb.run(link, br, ph, 3)
ph.cancel(9)
bb.run(link, br, ph, 2)
check(ph.tx[9]["done"] == bb.DONE_CANCELLED and br.sess is None and not br.radio_log, "annullamento durante la trasmissione: la scheda si ferma e libera la RAM")
ph.send(10, bb.KIND_TEXT, b"dopo", "IK5XYZ")
bb.run(link, br, ph, 30)
check(br.radio_log and br.radio_log[0]["data"] == b"dopo", "dopo l'annullamento si puo' inviare ancora")
link, br, ph = rig()
ph.send(11, bb.KIND_FILE, payload(20000, 9), "IK5XYZ")
bb.run(link, br, ph, 25)
check(any(e[0] == bb.E_PROGRESS for e in ph.events), "durante la trasmissione il telefono riceve l'avanzamento")

# errori
link, br, ph = rig(pos=False)
ph.send(12, bb.KIND_TEXT, b"x", "IK5XYZ")
bb.run(link, br, ph, 2)
check((12, bb.ERR_NO_POSITION) in ph.errors, "senza posizione la scheda rifiuta: nominativo, rapporto e posizione sono sempre trasmessi")
ph.set_position({"lat": 43.7696, "lon": 11.2558})
ph.send(13, bb.KIND_TEXT, b"x", "IK5XYZ")
bb.run(link, br, ph, 20)
check(ph.tx[13]["state"] == "done" and abs(br.position["lat"] - 43.7696) < 0.001, "la posizione GPS del telefono (assoluta) basta")
link, br, ph = rig()
ph.send(14, bb.KIND_TEXT, payload(bb.MAX_TEXT + 1), "IK5XYZ")
ph.send(15, bb.KIND_FILE, payload(bb.MAX_OBJECT + 1, 1), "IK5XYZ")
ph.send(16, 9, b"x", "IK5XYZ")
bb.run(link, br, ph, 2)
check((14, bb.ERR_TOO_BIG) in ph.errors and (15, bb.ERR_TOO_BIG) in ph.errors and (16, bb.ERR_BAD_KIND) in ph.errors, "testo oltre 1 kB, oggetto oltre 64 kB e tipo sconosciuto: rifiutati")
link, br, ph = rig()
ph.send(17, bb.KIND_FILE, payload(5000, 4), "IK5XYZ")
ph.send(18, bb.KIND_TEXT, b"seconda", "IK5XYZ")
bb.run(link, br, ph, 2)
check((18, bb.ERR_BUSY) in ph.errors, "un solo oggetto alla volta: il secondo riceve BUSY")
link, br, ph = rig(radio_ok=False)
ph.send(19, bb.KIND_TEXT, b"x", "IK5XYZ")
bb.run(link, br, ph, 20)
check(ph.tx[19]["done"] == bb.DONE_FAILED, "trasmissione radio fallita: il telefono lo sa (DONE con esito 1)")

# richieste e dati non voluti
link, br, ph = rig()
ph.send(20, bb.KIND_FILE, payload(5000, 4), "IK5XYZ")
bb.run(link, br, ph, 0.2)
before = br.stats["dropped"]
br.on_data(bb.enc_data(20, 4096, b"x" * 50))      # blocco non richiesto (il 4 non e' nella cache in vista)
br.on_data(bb.enc_data(99, 0, b"x" * 50))         # oggetto sconosciuto
check(br.stats["dropped"] > before and br.held() <= 3072, "dati di un blocco non richiesto: scartati")

# ricezione dalla radio: la scheda non conserva, serve il telefono collegato
link, br, ph = rig(mtu=185)
img = payload(5000, 11)
check(br.radio_received(0xABCD, bb.KIND_IMAGE, img, "IK5XYZ"), "oggetto dalla radio con il telefono collegato: accettato")
bb.run(link, br, ph, 10)
rx = ph.received[0xABCD]
check(rx["ok"] is True and bytes(rx["buf"]) == img and rx["h"]["from_call"] == "IK5XYZ" and 0xABCD not in br.rx_sessions, "arriva al telefono, il CRC torna e la scheda libera la copia")
link, br, ph = rig()
br.on_disconnect()
check(br.radio_received(1, bb.KIND_TEXT, b"ciao", "IK5XYZ") is False and not br.out_data, "senza telefono collegato la scheda non accetta oggetti dalla radio (non ha dove tenerli: niente microSD)")

# input malformati
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
            junk = bytes([r.choice((0x80, 0x81, 0x82, 0x85, 0x86, 0x87, 0x89))]) + junk[1:]
        ph.on_event(junk) if junk else None
        ph.on_data(junk)
    check(ph.bad_events > 100, f"2000 eventi e dati casuali sul telefono: nessuna eccezione, {ph.bad_events} scartati")
except Exception as e:  # noqa: BLE001
    check(False, f"eventi casuali: {e!r}")

print("ponte BLE: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
