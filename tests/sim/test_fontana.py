"""Prove del codice a fontana: python3 -I tests/sim/test_fontana.py"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import fontana as fo  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


rng = random.Random(7)
K, L = 40, 16
src = [bytes(rng.getrandbits(8) for _ in range(L)) for _ in range(K)]

# sistematico senza perdite: i primi K simboli sono i sorgenti
check(all(fo.codifica(src, 9, i) == src[i] for i in range(K)), "sistematico: ESI < K sono i simboli sorgente")

# decodifica con perdita del 40 %, ESI consecutivi
d = fo.Decodificatore(K, L, 9)
esi = 0
while not d.completo:
    if rng.random() >= 0.4:
        d.aggiungi(esi, fo.codifica(src, 9, esi))
    esi += 1
check(d.risultato() == src, f"decodifica esatta con il 40 % di perdita ({d.ricevuti} simboli ricevuti per K={K})")

# senza sistematico, solo simboli di codice
d = fo.Decodificatore(K, L, 3, False)
e = 0
while not d.completo:
    d.aggiungi(e, fo.codifica(src, 3, e, False))
    e += 1
check(d.risultato() == src, "decodifica esatta anche senza simboli sistematici")

# piu' sorgenti: ESI = contatore*M + indice; M=3 membri, ciascuno perde il 50 %
M = 3
d = fo.Decodificatore(K, L, 5)
cnt = 0
usati = set()
while not d.completo:
    for idx in range(M):
        e = cnt * M + idx
        assert e not in usati
        usati.add(e)
        if rng.random() >= 0.5:
            d.aggiungi(e, fo.codifica(src, 5, e))
    cnt += 1
check(d.risultato() == src, f"tre membri con ESI = contatore*3+indice, perdita 50 % ciascuno: decodifica esatta (ESI tutti distinti: {len(usati)})")

# la sovrapposizione misurata e' vicina al valore teorico (1,6 simboli)
ov = fo.sovrappiu_medio(64, 600, 2)
check(1.3 < ov < 2.0, f"sovrapposizione media con K=64: {ov:.2f} simboli (teoria ~1,6)")
ovs = fo.sovrappiu_medio(64, 300, 4, True, 0.3)
check(1.2 < ovs < 2.1, f"sovrapposizione con sistematico e perdita 30 %: {ovs:.2f} simboli")

print("fontana: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
