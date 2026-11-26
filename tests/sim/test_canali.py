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


check(ch.frequency_khz(ch.CH_MEETING) == 433700 and ch.frequency_khz(ch.CH_SERVICE) == 433850, "incontro a 433,700 MHz e servizio a 433,850 MHz")
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
print("canali: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
