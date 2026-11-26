#!/usr/bin/env python3
"""Riferimento Python per la prova del MEZZO C++ (firmware/v3/tests/test_medium.cpp): gli stessi scenari, 8 semi ciascuno, con consegna e tempi del simulatore Python.
Il mezzo C++ NON e' uguale al mezzo Python (qui i tempi di risposta sono veri, li' sono modellati): si confronta il comportamento, non i bit.
  python3 tools/gen_riferimento_medio.py <file-di-uscita>"""
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_immagini as si  # noqa: E402

# nome: chip_a chip_b prx scenario extra when span size tcxo budget
SCENARI = {
    "vicino": ("SX1278", "SX1278", -100.0, "costante", 11.0, 60.0, 300.0, 5000, 0, 600.0),
    "medio": ("SX1278", "SX1278", -118.0, "costante", 11.0, 60.0, 300.0, 4000, 0, 600.0),
    "degrada": ("SX1278", "SX1278", -122.0, "degrada", 14.0, 60.0, 300.0, 4000, 0, 600.0),
    "gradino": ("SX1262", "SX1262", -128.0, "gradino", 11.0, 60.0, 300.0, 3000, 0, 600.0),
    "oscilla": ("SX1278", "SX1278", -125.0, "oscilla", 14.0, 60.0, 300.0, 3000, 0, 600.0),
    "misto": ("SX1278", "SX1262", -120.0, "costante", 11.0, 60.0, 300.0, 4000, 0, 600.0),
    "tcxo": ("SX1278", "SX1278", -136.0, "costante", 11.0, 60.0, 300.0, 2000, 1, 600.0),
    "budget": ("SX1278", "SX1262", -125.0, "oscilla", 14.0, 60.0, 300.0, 30000, 0, 120.0),
    "perso": ("SX1278", "SX1278", -150.0, "costante", 11.0, 60.0, 300.0, 2000, 0, 600.0),
}
SEMI = range(1, 9)


def esegui(sc, seed):
    ca, cb, prx, scen, extra, when, span, size, tcxo, budget = sc
    ch = si.Channel(prx, scen, extra_db=extra, when_s=when, span_s=span, rng=random.Random(seed + 1))
    sim = si.Simulator(size, (1 / 3, 2 / 3, 1.0), ch, ca, cb, budget, seed, tcxo_a=bool(tcxo), tcxo_b=bool(tcxo), max_time_s=6 * 3600.0)
    return sim.run()


def genera(path):
    with open(path, "w") as f:
        for nome, sc in SCENARI.items():
            res = [esegui(sc, s) for s in SEMI]
            ok = [r for r in res if r.ok or r.unconfirmed]
            tm = statistics.median(r.time_s for r in ok) if ok else 0.0
            f.write(f"{nome} {' '.join(str(x) for x in sc)} {len(res)} {len(ok)} {tm!r}\n")


if __name__ == "__main__":
    genera(sys.argv[1] if len(sys.argv) > 1 else "/tmp/riferimento_medio.txt")
    print(open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/riferimento_medio.txt").read())
