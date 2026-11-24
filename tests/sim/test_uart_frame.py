"""Prove dell'incapsulamento sul flusso seriale: python3 -I tests/sim/test_uart_frame.py"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import uart_frame as uf  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


rng = random.Random(5)
ok = True
for n in list(range(0, 600)) + [1000]:
    for _ in range(3):
        d = bytes(rng.choice([0, 0, 1, 255, rng.getrandbits(8)]) for _ in range(n))
        e = uf.cobs_encode(d)
        if 0 in e or uf.cobs_decode(e) != d:
            ok = False
for n in (253, 254, 255, 256, 507, 508, 509, 1000):
    d = bytes([7]) * n
    e = uf.cobs_encode(d)
    if 0 in e or uf.cobs_decode(e) != d:
        ok = False
check(ok, "COBS: andata e ritorno esatti, mai uno zero nel flusso, anche ai confini dei blocchi da 254")
try:
    uf.cobs_decode(bytes([5, 1, 2]))
    check(False, "COBS troncato: errore")
except ValueError:
    check(True, "COBS troncato: errore")

# frame a pezzi arbitrari
frames = [bytes(rng.getrandbits(8) for _ in range(rng.choice([1, 20, 100, 200]))) for _ in range(40)]
stream = b"".join(uf.encode_frame(f) for f in frames)
dec = uf.Decoder()
got = []
i = 0
while i < len(stream):
    k = rng.randint(1, 37)
    got += dec.feed(stream[i:i + k])
    i += k
check(got == frames and dec.bad == 0, "40 frame ricevuti a pezzi di lunghezza casuale: tutti uguali, nessuno scartato")

# perdita di pezzi del flusso e byte rovinati: ci si risincronizza e non si accetta mai un frame sbagliato
lost = bytearray()
sent_ok = set()
for f in frames:
    e = bytearray(uf.encode_frame(f))
    r = rng.random()
    if r < 0.2:
        continue                                   # frame perso del tutto
    if r < 0.4 and len(e) > 4:
        e[rng.randrange(len(e) - 1)] ^= 0x55       # un byte rovinato
        if e[:-1].count(0) == 0:
            pass
    elif r < 0.5:
        e = e[:len(e) // 2]                        # frame tagliato a meta' (poi arriva il successivo)
    lost += e
dec2 = uf.Decoder()
got2 = dec2.feed(bytes(lost))
check(all(g in frames for g in got2) and len(got2) >= 12 and dec2.bad >= 1, f"con perdite e byte rovinati: {len(got2)} frame buoni su 40, {dec2.bad} scartati, nessuno sbagliato")
d3 = uf.Decoder()
d3.feed(bytes([9]) * 3000)
check(d3.bad >= 1 and not d3.buf or len(d3.buf) <= uf.MAX_FRAME, "rumore senza delimitatore: il buffer non cresce all'infinito")
check(len(uf.encode_frame(b"x" * 100)) == 100 + 2 + 1 + 1, "costo per 100 byte: 4 byte (CRC 2, delimitatore 1, COBS 1)")
print("incapsulamento seriale: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
