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
check(d["nome"] == "REQ_RELAY" and d["obj"] == oid and d["dest"] == "IZ5AAA" and d["size"] == 20000 and len(fm.enc_req_relay(oid, "IU5HJU", "IZ5AAA", 1)) == 21, "RICHIESTA-RIPETITORI con identificativo a 32 bit (21 byte)")
d = fm.decode(fm.enc_offer_relay(oid, "IK5XYZ", {"lat": 43.7, "lon": 11.2}, 4, 5, 9, -3, fm.CODE_SELECTIVE | fm.CODE_FOUNTAIN, 120))
check(d["obj"] == fm.short_id(oid) and d["nome"] == "OFFER_RELAY" and d["rung_src"] == 4 and d["rung_dst"] == 5 and d["margin_src"] == 9 and d["margin_dst"] == -3 and d["codes"] == 3 and abs(d["pos"]["lat"] - 43.7) < 1e-4,
      "OFFERTA: posizione, gradini (un byte) verso mittente e destinatario, margini, codici")
mem = [("IK5XYZ", fm.ADMIT, 0), ("IZ5AAA", fm.ADMIT, 1), ("IW5BBB", fm.RESERVE, 2), ("IU5CCC", fm.EXCLUDE, 3)]
d = fm.decode(fm.enc_group(oid, fm.CODE_FOUNTAIN, 6, 128, 16, 0xBEEF, 1795000000, mem))
check(d["nome"] == "GROUP" and d["members"] == mem and d["k"] == 128 and d["rung"] == 6 and d["start"] == 1795000000 and d["seed"] == 0xBEEF, "GRUPPO: membri con stato e turno, codice, parametri, ora di inizio")
d = fm.decode(fm.enc_group_ack(oid, rung=6))
check(d["nome"] == "GROUP_ACK" and not d["veto"], "CONFERMA")
d = fm.decode(fm.enc_group_ack(oid, "IW5BBB", 6))
check(d["veto"] and d["veto_call"] == "IW5BBB", "VETO con il membro che non si sente")
check(fm.decode(b"\x3e\x63" + bytes(10)) is None and fm.decode(b"\x2e\x01" + bytes(12)) is None and fm.decode(fm.enc_group(oid, 1, 1, 1, 1, 1, 1, mem)[:-3]) is None,
      "frame sconosciuti o troncati: scartati")

d = fm.decode(fm.enc_vote("IU5HJU", 0xBEEF, 14, 3))
check(len(fm.enc_vote("IU5HJU", 1, 0, 1)) == 12 and d["nome"] == "VOTE" and d["call"] == "IU5HJU" and d["session"] == 0xBEEF and d["margin"] == 14 and d["node"] == 3, "VOTO: 12 byte, nominativo, sessione, margine, nodo")
check(fm.vote_winner([(10, 2), (14, 5)]) == 5 and fm.vote_winner([(12, 4), (12, 2)]) == 2, "vince il margine piu' alto; a parita' l'identificativo piu' basso")
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

# ---- revisione 0.2: opzioni, profili fisici, cambio di banda ----
check(fm.short_id(fm.object_id("IU5HJU", 7)) == fm.object_id("IU5HJU", 7) & 0xFFFF and fm.object_id("IU5HJU", 7) > 0xFFFF, "identificativo a 32 bit; la forma corta (sessione) e' la parte bassa")
opts = [fm.opt_revision(), fm.opt_profiles([(fm.PROFILE_SUBGHZ, 0x7FFF), (fm.PROFILE_2G4, 0x00FF)])]
h = sim.decode(sim.enc_hello(1, "IU5HJU", "SX1278", 0x7FFF, 255, 100, pos={"loc": "JN53ab"}, opts=opts))
check(h["flags"] & fm.F_OPT and h["opts"][fm.OPT_REV] == bytes([fm.REVISION]) and fm.parse_profiles(h["opts"][fm.OPT_PROFILES]) == [(0, 0x7FFF), (1, 0x00FF)] and h["pos"] == {"loc": "JN53ab"},
      "HELLO con posizione e opzioni: revisione e due profili fisici (430 MHz e 2,4 GHz)")
base = len(sim.enc_hello(1, "IU5HJU", "SX1278", 0x7FFF, 255, 100))
check(len(sim.enc_hello(1, "IU5HJU", "SX1278", 0x7FFF, 255, 100, opts=opts)) == base + 3 + 8, f"le opzioni costano solo quando ci sono: HELLO base {base} byte, +11 byte con revisione e due profili")
future = sim.enc_hello(1, "IU5HJU", "SX1278", 0x7FFF, 255, 100, opts=[(77, b"xyz"), fm.opt_revision()])
hf = sim.decode(future)
check(hf["opts"][77] == b"xyz" and hf["opts"][fm.OPT_REV] == bytes([fm.REVISION]) and hf["call"] == "IU5HJU", "un'opzione di tipo sconosciuto non rompe la lettura delle altre (compatibilita' in avanti)")
check(sim.decode(sim.enc_hello(1, "IU5HJU", "SX1278", 0x7FFF, 255, 100) + b"") ["flags"] & fm.F_OPT == 0, "un HELLO della revisione 0.1 (senza opzioni) si legge ancora")
try:
    fm.unpack_opts(b"\x01\x05ab")
    check(False, "opzioni troncate: errore")
except ValueError:
    check(True, "opzioni troncate: errore")
o = sim.decode(sim.enc_offer(2, "IU5HJU", 0, 20000, 16, 1250, 0, 0, [400, 1250], 0xDEADBEEF, pos={"loc": "JN53ab"}, opts=[fm.opt_id32(fm.object_id("IU5HJU", 9))]))
check(o["crc"] == 0xDEADBEEF and o["pos"] == {"loc": "JN53ab"} and int.from_bytes(o["opts"][fm.OPT_ID32], "big") == fm.object_id("IU5HJU", 9), "OFFER con posizione e identificativo a 32 bit in opzione")
b = fm.enc_band_set(0xABCD, fm.PROFILE_2G4, 3, 2, 15, 3, fm.BAND_AT_UTC, 1795000000)
d = fm.decode(b)
check(len(b) == 14 and d["nome"] == "BAND_SET" and d["profile"] == 1 and d["channel"] == 3 and d["rung"] == 2 and d["k"] == 15 and d["repeat"] == 3 and d["mode"] == fm.BAND_AT_UTC and d["start"] == 1795000000, "BAND-SET: 14 byte, profilo, canale, gradino, k, quando")
d = fm.decode(fm.enc_band_ack(0xABCD, 1, 3))
check(d["nome"] == "BAND_ACK" and d["profile"] == 1 and d["channel"] == 3 and len(fm.enc_band_ack(1, 1, 3)) == 6, "BAND-ACK: 6 byte")
d = fm.decode(fm.enc_band_back(0xABCD, fm.BACK_PROBE_FAILED))
check(d["nome"] == "BAND_BACK" and d["reason"] == 1 and len(fm.enc_band_back(1, 1)) == 5, "BAND-BACK: ritorno alla banda base, 5 byte")
d = fm.decode(fm.enc_offer_relay(fm.object_id("IU5HJU", 1), "IK5XYZ", {"loc": "JN53ab"}, 13, fm.NOT_HEARD, 9, -3, 3, 100))
check(d["rung_src"] == 13 and d["rung_dst"] == fm.NOT_HEARD, "OFFERTA: il gradino non sentito (255) non confonde piu' R15 o altri gradini futuri")
check(all(v < 64 for k, v in fm.SUB.items() if not k.startswith("BAND_")) and all(64 <= v < 128 for k, v in fm.SUB.items() if k.startswith("BAND_")), "sottotipi: 1-63 mesh, 64-127 collegamento e banda, 128-255 riservati")
b = fm.enc_band_set_freq(0xABCD, fm.PROFILE_SUBGHZ, 433955, 12, 3, 3, fm.BAND_AT_UTC, 1795000000)
d = fm.decode(b)
check(len(b) == 17 and d["nome"] == "BAND_SET_FREQ" and d["freq_khz"] == 433955 and d["rung"] == 12 and d["start"] == 1795000000, "BAND-SET con frequenza esplicita: 17 byte (le frequenze sono configurabili, le tabelle possono differire)")
d = fm.decode(fm.enc_band_ack_freq(0xABCD, fm.PROFILE_2G4_UART, 2424000, -97))
check(d["nome"] == "BAND_ACK_FREQ" and d["freq_khz"] == 2424000 and d["rssi_dbm"] == -97 and len(fm.enc_band_ack_freq(1, 1, 1)) == 10 and fm.decode(fm.enc_band_ack_freq(1, 1, 1))["rssi_dbm"] == fm.RSSI_UNKNOWN, "BAND-ACK con frequenza esplicita e RSSI del canale misurato dal ricevitore: 10 byte (controproposta)")
check(all(64 <= fm.SUB[k] < 128 for k in ("BAND_SET_FREQ", "BAND_ACK_FREQ")), "i sottotipi nuovi stanno nell'intervallo 64-127")
# compatibilita' con la v2: nessun frame V3 e' un pacchetto v2 e viceversa (la v2 scarta la versione diversa da 2)
v2 = bytes([0x21]) + bytes(8)                       # byte 0: versione 2, modo 1 (Codec2 1200)
check(fm.decode(v2) is None and sim.decode(v2) is None, "un pacchetto v2 non viene decodificato dai decoder V3")
v3 = [fm.enc_beacon("IU5HJU"), fm.enc_poll("IU5HJU", "IK5XYZ"), fm.enc_vote("IU5HJU", 1, 3, 1), sim.enc_hello(1, "IU5HJU", "SX1278", 0x7FFF, 255, 100), sim.enc_data(1, 0, b"x" * 16)]
check(all((f[0] >> 4) == 3 for f in v3), "tutti i frame V3 hanno la versione 3 nel nibble alto: una stazione v2 li scarta")
print("frame mesh: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
