"""Prove dei frame mesh e dei campi nuovi: python3 -I tests/sim/test_frame_mesh.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import frame_mesh as fm  # noqa: E402
import sim_immagini as sim  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


# nominativo compatto
for c in ("IU5HJU", "IK5XYZ/P", "A1B", "IU5HJU-1"):
    check(fm.unpack_call(fm.pack_call(c)) == c, f"nominativo compatto {c}")
check(len(fm.pack_call("IU5HJU")) == 6, "nominativo compatto: 6 byte per 8 caratteri")
try:
    fm.pack_call("IU5HJU123")
    check(False, "nominativo di 9 caratteri deve dare errore")
except ValueError:
    check(True, "nominativo di 9 caratteri: errore")

# posizione
p = fm.unpack_pos(fm.pack_pos({"loc": "JN53ab"}))
check(p == {"loc": "JN53ab"} and len(fm.pack_pos({"loc": "JN53ab"})) == 7, "posizione come locatore: 7 byte")
g = fm.unpack_pos(fm.pack_pos({"lat": 43.7712, "lon": 11.2486}))
check(abs(g["lat"] - 43.7712) < 2e-5 and abs(g["lon"] - 11.2486) < 3e-5 and len(fm.pack_pos({"lat": 1.0, "lon": 2.0})) == 7, f"posizione GPS: errore {abs(g['lat'] - 43.7712) * 111000:.1f} m in latitudine")
gs = fm.unpack_pos(fm.pack_pos({"lat": -33.9, "lon": -151.2}))
check(abs(gs["lat"] + 33.9) < 2e-5 and abs(gs["lon"] + 151.2) < 3e-5, "posizione GPS con segni negativi")

# identificativo globale e salti
check(fm.object_id("IU5HJU", 1) == fm.object_id("iu5hju", 1) and fm.object_id("IU5HJU", 1) != fm.object_id("IU5HJU", 2) and fm.object_id("IU5HJU", 1) != fm.object_id("IK5XYZ", 1), "identificativo globale: stesso (nominativo, contatore) = stesso id")
fl = fm.data_flags(1 | 4, relayed=True, hops=2)
sp = fm.split_data_flags(fl)
check(sp == {"base": 5, "relayed": True, "hops": 2}, f"flag DATA con ripetuto e salti: {sp}")

# beacon
b = fm.enc_beacon("IU5HJU")
d = fm.decode(b)
check(len(b) == 7 and d["nome"] == "BEACON" and d["call"] == "IU5HJU", "BEACON: 7 byte, solo nominativo")

# frame mesh
d = fm.decode(fm.enc_poll("IU5HJU", "IK5XYZ"))
check(d["nome"] == "POLL" and d["caller"] == "IU5HJU" and d["target"] == "IK5XYZ", "POLL")
d = fm.decode(fm.enc_poll_reply("IK5XYZ", {"loc": "JN54xx"}, -118, -7, 0x7FFF, 3, 100))
check(d["nome"] == "POLL_REPLY" and d["pos"] == {"loc": "JN54xx"} and d["rssi"] == -118 and d["snr"] == -7 and d["rung_mask"] == 0x7FFF and d["codes"] == 3, "POLL-REPLY: posizione, rapporto, capacita'")
oid = fm.object_id("IU5HJU", 7)
d = fm.decode(fm.enc_req_relay(oid, "IU5HJU", "IZ5AAA", 20000))
check(d["nome"] == "REQ_RELAY" and d["obj"] == oid and d["dest"] == "IZ5AAA" and d["size"] == 20000, "RICHIESTA-RIPETITORI")
d = fm.decode(fm.enc_offer_relay(oid, "IK5XYZ", {"lat": 43.7, "lon": 11.2}, 4, 5, 9, -3, fm.CODE_SELECTIVE | fm.CODE_FOUNTAIN, 120))
check(d["nome"] == "OFFER_RELAY" and d["rung_src"] == 4 and d["rung_dst"] == 5 and d["margin_src"] == 9 and d["margin_dst"] == -3 and d["codes"] == 3 and abs(d["pos"]["lat"] - 43.7) < 1e-4,
      "OFFERTA: posizione, gradini verso mittente e destinatario, margini, codici")
mem = [("IK5XYZ", fm.ADMIT, 0), ("IZ5AAA", fm.ADMIT, 1), ("IW5BBB", fm.RESERVE, 2), ("IU5CCC", fm.EXCLUDE, 3)]
d = fm.decode(fm.enc_group(oid, fm.CODE_FOUNTAIN, 6, 128, 16, 0xBEEF, 1795000000, mem))
check(d["nome"] == "GROUP" and d["members"] == mem and d["k"] == 128 and d["rung"] == 6 and d["start"] == 1795000000 and d["seed"] == 0xBEEF, "GRUPPO: membri con stato e turno, codice, parametri, ora di inizio")
d = fm.decode(fm.enc_group_ack(oid, rung=6))
check(d["nome"] == "GROUP_ACK" and not d["veto"], "CONFERMA")
d = fm.decode(fm.enc_group_ack(oid, "IW5BBB", 6))
check(d["veto"] and d["veto_call"] == "IW5BBB", "VETO con il membro che non si sente")
check(fm.decode(b"\x3e\x63" + bytes(10)) is None and fm.decode(b"\x2e\x01" + bytes(12)) is None and fm.decode(fm.enc_group(oid, 1, 1, 1, 1, 1, 1, mem)[:-3]) is None,
      "frame sconosciuti o troncati: scartati")

# i frame V3 gia' esistenti con i campi nuovi
h = sim.decode(sim.enc_hello(1, "IU5HJU", "SX1278", 0x7FFF, 255, 100, reply=True, rssi=-110, snr=-4, pos={"loc": "JN53ab"}))
check(h["call"] == "IU5HJU" and h["rssi"] == -110 and h["pos"] == {"loc": "JN53ab"} and h["len"] == sim.decode(sim.enc_hello(1, "IU5HJU", "SX1278", 0x7FFF, 255, 100, reply=True, rssi=-110, snr=-4))["len"] + 7,
      "HELLO con rapporto e posizione: 7 byte in piu'")
h = sim.decode(sim.enc_hello(1, "IU5HJU", "SX1278", 0x7FFF, 255, 100, pos={"lat": 43.7, "lon": 11.2}))
check("pos" in h and "rssi" not in h, "HELLO con la sola posizione (primo contatto, senza rapporto)")
o = sim.decode(sim.enc_offer(2, "IU5HJU", 0, 20000, 16, 1250, 0, 0, [400, 1250], 0xDEADBEEF, pos={"loc": "JN53ab"}))
check(o["crc"] == 0xDEADBEEF and o["pos"] == {"loc": "JN53ab"} and o["layer_ends"] == [400, 1250], "OFFER con la posizione del mittente")
o = sim.decode(sim.enc_offer(2, "IU5HJU", 0, 20000, 16, 1250, 0, 0, [400, 1250], 0xDEADBEEF))
check("pos" not in o and o["crc"] == 0xDEADBEEF, "OFFER senza posizione ancora decodificabile (compatibilita' del simulatore)")
dt = sim.decode(sim.enc_data(3, 10, b"x" * 16, fm.data_flags(1, relayed=True, hops=2)))
check(dt["relayed"] and dt["hops"] == 2 and dt["flags"] & 1 and dt["offset"] == 10, "DATA con ripetuto e numero di salti")
dt = sim.decode(sim.enc_data(3, 10, b"x" * 16, 1))
check(not dt["relayed"] and dt["hops"] == 0, "DATA normale: non ripetuto, 0 salti")

print("frame mesh: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
