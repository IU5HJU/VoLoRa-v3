"""Prove della tabella dei canali: python3 -I tests/sim/test_canali.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import canali as ch  # noqa: E402
import protocollo_immagini as pi  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


check(ch.frequency_khz(ch.CH_MEETING) == 433700 and ch.frequency_khz(ch.CH_SERVICE) == 433850, "incontro a 433,700 MHz; il canale 1 (433,850 MHz) e' ora per trasferimenti stretti")
check(ch.SERVICE_2M_KHZ == 144900 and ch.valid_frequency("SX1278", 144900) and not ch.valid_frequency("SX1262", 144900), "il canale di servizio del voto (144,900 MHz) e' nel campo dell'SX1278 (T3, T-Beam SX1278) ma NON in quello dell'SX1262 (da 150 MHz): il T-Beam con SX1262 non puo' fare il voto a 2 m")
h3 = ch.harmonic_khz(ch.SERVICE_2M_KHZ, 3)
nearest = min(min(abs(h3 - ch.span_khz(i)[0]), abs(h3 - ch.span_khz(i)[1])) for i in ch.PROFILE0)
check(h3 == 434700 and all(not (ch.span_khz(i)[0] <= h3 <= ch.span_khz(i)[1]) for i in ch.PROFILE0) and nearest > 500, f"la terza armonica del servizio ({h3 / 1000:.3f} MHz) cade fuori dai canali, a {nearest:.0f} kHz dal piu' vicino: serve un filtro passa-basso sulla radio a 2 m")
lo, hi = ch.SEGMENT_KHZ
inside = all(lo <= ch.span_khz(i)[0] and ch.span_khz(i)[1] <= hi for i in ch.PROFILE0)
check(inside, "tutti i canali stanno dentro il segmento 433,600-434,000 MHz")
check(all(ch.guard_khz(a, b) >= 10 for a in ch.PROFILE0 for b in ch.PROFILE0 if a < b), f"nessuna sovrapposizione, guardia minima {min(ch.guard_khz(a, b) for a in ch.PROFILE0 for b in ch.PROFILE0 if a < b):.2f} kHz")
check(ch.span_khz(0)[0] >= 433625 - 12.5 and ch.span_khz(0)[1] <= 433775 + 12.5, "il canale di incontro sta (quasi) nei canali digitali 433,625-433,775 MHz")
check(ch.span_khz(ch.CH_MEETING)[0] > 433575, "il canale di incontro e' oltre il segmento FM/Digital Voice della v2 (fino a 433,575 MHz)")
a0 = ch.allowed_rungs(0)
check(a0 == [2, 8, 9, 10, 11, 12, 13, 14] and pi.RENDEZVOUS in a0, f"canale 0 (125 kHz): gradini ammessi R{a0}, compreso R10 di incontro")
check(ch.allowed_rungs(2) == [11, 12, 13, 14], "canale 2 (62,5 kHz): solo R11-R14")
check(ch.best_channel_for(10) == 0 and ch.best_channel_for(10, busy={0}) == 1 and ch.best_channel_for(13, busy={0, 1}) == 2, "scelta del primo canale libero che ospita il gradino")
check(all(ch.best_channel_for(r) is None for r in (0, 1, 3, 4, 5, 6, 7)), "R0, R1 e R3-R7 (piu' larghi di 125 kHz) non hanno canale nel segmento: servono l'altra banda o un accordo")
try:
    ch.frequency_khz(5)
    check(False, "canale riservato: errore")
except ValueError:
    check(True, "canale riservato: errore")
# frequenze configurabili
custom = ch.make_plan({0: (433700, 125, "incontro"), 1: (434500, 125, "altro"), 7: (470000, 62.5, "fuori dalla banda dello studio ma nel campo del chip")})
check(set(custom) == {0, 1, 7}, "tabella configurata liberamente (anche fuori da 430-440 MHz, purche' nel campo del chip)")
for bad, chip in (({0: (200000, 125, "x")}, "SX1278"), ({0: (433700, 125, "a"), 1: (433750, 125, "b")}, "SX1278"), ({0: (100000, 125, "x")}, "SX1262")):
    try:
        ch.make_plan(bad, chip)
        check(False, f"configurazione non valida {bad}: errore")
    except ValueError:
        pass
check(True, "frequenza fuori dal campo del chip o canali sovrapposti: errore")
check(ch.valid_frequency("SX1262", 868000) and not ch.valid_frequency("SX1278", 868000) and ch.valid_frequency("SX1278", 433000), "campo di sintonia: SX1278 137-175 e 395-525 MHz, SX1262 150-960 MHz")
check(ch.chan_for_frequency_2g4(2424000, 3) == 24 and ch.chan_for_frequency_2g4(2424000, 4) == 12 and ch.chan_for_frequency_2g4(2425000, 7) == 5, "frequenza a 2,4 GHz -> CHAN del modulo (1 MHz a 10k, 2 MHz a 50k, 5 MHz a 2M)")
for khz, ac in ((2450001, 3), (2399000, 3), (2425000, 4), (2423500, 3)):
    try:
        ch.chan_for_frequency_2g4(khz, ac)
        check(False, f"{khz} kHz con codice {ac}: errore")
    except ValueError:
        pass
check(True, "fuori da 2400-2450 MHz o fuori dalla griglia del modulo: errore")
print("canali: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
