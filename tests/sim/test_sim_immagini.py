"""Prove del simulatore del protocollo immagini: python3 -I tests/sim/test_sim_immagini.py"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import protocollo_immagini as pi  # noqa: E402
import sim_immagini as sim  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


def run(prx=-100.0, size=5000, scenario="costante", seed=1, budget=3600.0, hook=None, **kw):
    ch = sim.Channel(prx, scenario, rng=random.Random(seed + 1), **kw)
    s = sim.Simulator(size, (1 / 3, 2 / 3, 1.0), ch, "SX1278", "SX1278", budget, seed)
    s.drop_hook = hook
    return s, s.run()


# ---- codec ----
sid = 0xBEEF
f = sim.decode(sim.enc_hello(sid, "IU5HJU", "SX1262", 0x7FFF, 255, 100, reply=True))
check(f and f["nome"] == "HELLO" and f["call"] == "IU5HJU" and f["chip"] == "SX1262" and f["reply"] and f["rung_mask"] == 0x7FFF and f["max_frame"] == 255 and f["mem_kb"] == 100, "HELLO")
f = sim.decode(sim.enc_hello(sid, "IU5HJU", "SX1278", 0x7FFF, 255, 100, reply=True, rssi=-118.4, snr=-9.0))
check(f["reply"] and f["rssi"] == -118 and f["snr"] == -9 and f["flags"] == 3, "HELLO di risposta con la misura (RSSI e SNR)")
f = sim.decode(sim.enc_probe(sid, 5, 2, 8))
check(f["nome"] == "PROBE" and f["rung"] == 5 and f["idx"] == 2 and f["count"] == 8 and f["len"] == sim.PROBE_BYTES, "PROBE (32 byte)")
f = sim.decode(sim.enc_probe_report(sid, 5, 8, 7, -101.4, 12.0))
check(f["nome"] == "PROBE_REPORT" and f["received"] == 7 and f["rssi"] == -101 and f["snr"] == 12, "PROBE-REPORT")
f = sim.decode(sim.enc_mode_set(sid, 7, 15, 2))
check(f["nome"] == "MODE_SET" and f["rung"] == 7 and f["k"] == 15 and f["repeat"] == 2, "MODE-SET")
check(sim.decode(sim.enc_mode_ack(sid, 7))["rung"] == 7, "MODE-ACK")
o = sim.enc_offer(sid, "IU5HJU", 0, 20000, 16, 1250, 160, 120, [400, 800, 1250], 0xDEADBEEF)
f = sim.decode(o)
check(f["nome"] == "OFFER" and f["size"] == 20000 and f["npieces"] == 1250 and f["layer_ends"] == [400, 800, 1250] and f["crc"] == 0xDEADBEEF and f["w"] == 160, "OFFER")
f = sim.decode(sim.enc_accept(sid, 3, 16, 4))
check(f["nome"] == "ACCEPT" and f["layers"] == 3 and f["window"] == 16 and f["k"] == 4, "ACCEPT")
d = sim.enc_data(sid, 1234, bytes(range(48)), sim.F_LAST_WINDOW | sim.F_RETX)
f = sim.decode(d)
check(len(d) == pi.DATA_HEADER + 48 and f["offset"] == 1234 and f["payload"] == bytes(range(48)) and f["flags"] == 3, "DATA: intestazione di 6 byte")
s = sim.enc_status(sid, 100, 0xF0F0F0F0F0F0F0F0, -110, -4, 12.5, 2)
f = sim.decode(s)
check(len(s) == pi.STATUS_BYTES and f["base"] == 100 and f["bitmap"] == 0xF0F0F0F0F0F0F0F0 and f["rssi"] == -110 and f["snr"] == -4 and f["loss_pct"] == 12 and f["layers_done"] == 2, "STATUS: 18 byte")
f = sim.decode(sim.enc_done(sid, "IU5HJU", 2, 1667, 0x01020304))
check(f["nome"] == "DONE" and f["layers"] == 2 and f["nbytes"] == 1667 and f["crc"] == 0x01020304, "DONE")
check(sim.decode(sim.enc_abort(sid, 1))["reason"] == 1, "ABORT")
check(sim.decode(bytes([0x27, 0, 1, 0])) is None and sim.decode(b"\x30") is None, "un frame v2 (versione 2) o troppo corto non e' V3")
check(all(sim.enc_data(1, 0, b"x" * 16)[0] >> 4 == 3 for _ in range(1)), "i frame V3 hanno il nibble di versione 3 (la v2 li scarta)")

# ---- protocollo ----
s1, r1 = run(-100.0, 5000, seed=1)
check(r1.ok and r1.crc_ok and r1.layers_delivered == 3 and r1.bytes_delivered == 5000, "link forte: consegna completa con CRC giusto")
check(min(r for r in r1.rung_time if r != pi.RENDEZVOUS) < pi.RENDEZVOUS, "link forte: sale oltre il gradino di incontro")
s1b, r1b = run(-100.0, 5000, seed=1)
check(r1b.time_s == r1.time_s and r1b.frames == r1.frames, "stesso seme, stesso risultato (determinismo)")
times = [run(p, 3000, seed=2)[1].transfer_s for p in (-100, -120, -130)]
check(times[0] < times[1] < times[2], f"piu' debole il segnale, piu' lungo il trasferimento: {[round(x) for x in times]} s")
for p in (-100, -118, -128):
    _, r = run(p, 4000, seed=3)
    check(r.ok and r.crc_ok, f"consegna con crc giusto a {p} dBm")

# budget: i livelli che non entrano non partono, il primo e' obbligatorio, i byte consegnati sono un prefisso con CRC giusto
s2, r2 = run(-125.0, 20000, seed=4, budget=120.0)
check(r2.ok and 1 <= r2.layers_delivered < 3 and r2.crc_ok and r2.bytes_delivered < 20000, f"budget stretto: consegnati {r2.layers_delivered} livelli su 3, CRC ok")
s3, r3 = run(-134.0, 20000, seed=5, budget=10.0)
check(not r3.ok and "primo livello" in r3.reason, "budget troppo piccolo per il primo livello: non parte (" + r3.reason + ")")
# incontro: la misura nell'HELLO fa risparmiare tempo rispetto alla raffica di PROBE, con lo stesso risultato
_, ra = run(-100.0, 5000, seed=11)
ch_ = sim.Channel(-100.0, rng=random.Random(12))
sb = sim.Simulator(5000, (1 / 3, 2 / 3, 1.0), ch_, "SX1278", "SX1278", 3600.0, 11, incontro="probe")
rb = sb.run()
check(ra.ok and rb.ok and ra.time_s < rb.time_s - 8.0, f"incontro con misura nell'HELLO: {ra.time_s:.0f} s contro {rb.time_s:.0f} s con 8 PROBE")
# nessun collegamento: termina e non trasmette all'infinito
s4, r4 = run(-150.0, 2000, seed=6)
check(not r4.ok and "nessun incontro" in r4.reason and r4.time_s <= 700 and r4.frames.get("HELLO", 0) < 30, f"nessun incontro: rinuncia dopo {r4.time_s:.0f} s e {r4.frames.get('HELLO', 0)} HELLO")

# MODE-ACK perso: disallineamento, attesa del fallback, poi riuscita
state = {"n": 0}


def drop_first_ack(d):
    if d["nome"] == "MODE_ACK" and state["n"] < 3:   # tutti e tre i tentativi del primo cambio
        state["n"] += 1
        return True
    return False


s5, r5 = run(-110.0, 3000, seed=7, hook=drop_first_ack)
check(any("disallineamento" in l for l in s5.log), "MODE-ACK perso: si vede il disallineamento e l'attesa del fallback")
check(r5.ok and r5.crc_ok, "dopo il disallineamento la consegna riesce")

# STATUS perso piu' volte: il mittente ripete e poi scende, ma consegna
state2 = {"n": 0}


def drop_some_status(d):
    if d["nome"] == "STATUS" and state2["n"] < 4:
        state2["n"] += 1
        return True
    return False


s6, r6 = run(-105.0, 3000, seed=8, hook=drop_some_status)
check(r6.ok and r6.crc_ok, "STATUS persi: consegna riuscita")

# degrado a meta' trasferimento: scende di gradino e consegna
s7, r7 = run(-126.0, 6000, scenario="gradino", seed=1, extra_db=9.0, when_s=100.0)
check(r7.ok and r7.crc_ok, "gradino di -9 dB durante il trasferimento: consegna")
# affievolimento ondulato: ritrasmissioni e consegna
s8, r8 = run(-133.0, 3000, scenario="oscilla", seed=2, extra_db=8.0, span_s=200.0)
check(r8.ok and r8.crc_ok and r8.retx_frames > 0, f"segnale ondulato: {r8.retx_frames} ritrasmissioni, consegna ok")

# la stima della tabella e' vicina al simulatore in condizioni buone (stesso ordine di grandezza)
s9, r9 = run(-100.0, 20000, seed=9)
est = pi.estimate_seconds(20000, 2, "SX1278")
check(r9.ok and 0.3 * est <= r9.transfer_s <= 3.0 * est, f"trasferimento di 20 kB a -100 dBm: simulato {r9.transfer_s:.0f} s, stima della tabella {est:.0f} s")

# ricerca a calendario (dopo un lungo silenzio): scenario in cui R10 non si sente piu' (da -136 a -147 dBm a 60 s), 8 semi
ok_cal = ok_r10 = 0
for seed in range(1, 9):
    for ric in ("calendario", "r10"):
        ch = sim.Channel(-136.0, "gradino", extra_db=11.0, when_s=60.0, rng=random.Random(seed + 1))
        sm = sim.Simulator(1000, (1 / 3, 2 / 3, 1.0), ch, "SX1278", "SX1278", 7200.0, seed, ricerca=ric)
        r = sm.run()
        if r.ok:
            ok_cal += ric == "calendario"
            ok_r10 += ric == "r10"
check(ok_cal >= ok_r10 + 3, f"ricerca a calendario: {ok_cal}/8 riuscite contro {ok_r10}/8 con il solo ritorno a R10 (R10 non si sente piu')")
check(sim.scan_rung(0) == 10 and sim.scan_rung(sim.scan_dwell_s(10) + 1) == 11 and sim.scan_rung(sum(sim.scan_dwell_s(r) for r in sim.SCAN_ORDER) + 1) == 10, "calendario: R10, poi R11, e ricomincia dopo il giro")

if fails:
    print(fails, "prove fallite")
    sys.exit(1)
print("simulatore: tutte le prove passate")
