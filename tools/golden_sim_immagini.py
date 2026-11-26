#!/usr/bin/env python3
"""Risultati di riferimento del simulatore del protocollo immagini su una griglia di scenari (catturati PRIMA del rifacimento in mittente e ricevitore indipendenti).
Il rifacimento deve riprodurli esattamente (tests/sim/test_golden_sim_immagini.py).   python3 tools/golden_sim_immagini.py [scrivi]"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_immagini as si  # noqa: E402

GOLDEN = os.path.join(HERE, "..", "tests", "sim", "golden_sim_immagini.json")


def scenari():
    out = []
    for chips in (("SX1278", "SX1278"), ("SX1278", "SX1262"), ("SX1262", "SX1262")):
        for prx in (-100.0, -118.0, -128.0, -136.0, -142.0):
            for scen in ("costante", "degrada", "gradino", "oscilla"):
                for seed in (1, 2):
                    out.append(dict(chips=chips, prx=prx, scen=scen, seed=seed, size=20000 if prx > -130 else 4000, tcxo=False, ricerca="calendario", incontro="hello"))
    for seed in (3, 4):
        for ric in ("calendario", "r10"):
            for inc in ("hello", "probe"):
                out.append(dict(chips=("SX1278", "SX1278"), prx=-136.0, scen="gradino", seed=seed, size=6000, tcxo=True, ricerca=ric, incontro=inc))
    for seed in (5, 6, 7):
        out.append(dict(chips=("SX1278", "SX1262"), prx=-125.0, scen="oscilla", seed=seed, size=30000, tcxo=False, ricerca="calendario", incontro="hello", budget=120.0))
        out.append(dict(chips=("SX1278", "SX1278"), prx=-90.0, scen="costante", seed=seed, size=65000, tcxo=False, ricerca="calendario", incontro="hello", layers=(0.1, 0.3, 0.6, 1.0)))
    return out


def esegui(sc):
    ch = si.Channel(sc["prx"], sc["scen"], extra_db=11.0 if sc["scen"] != "oscilla" else 14.0, when_s=60.0, span_s=300.0, rng=random.Random(sc["seed"] + 1))
    sim = si.Simulator(sc["size"], sc.get("layers", (1 / 3, 2 / 3, 1.0)), ch, sc["chips"][0], sc["chips"][1], sc.get("budget", 600.0), sc["seed"], ricerca=sc["ricerca"], incontro=sc["incontro"],
                       tcxo_a=sc["tcxo"], tcxo_b=sc["tcxo"], max_time_s=6 * 3600.0)
    r = sim.run()
    return dict(ok=r.ok, reason=r.reason, time=repr(r.time_s), transfer=repr(r.transfer_s), layers=r.layers_delivered, nbytes=r.bytes_delivered, crc=r.crc_ok, frames=r.frames, retx=r.retx_frames,
                data=r.data_frames, fallbacks=r.fallbacks, rung_time={str(k): repr(v) for k, v in sorted(r.rung_time.items())}, changes=[list(map(repr, c)) for c in r.rung_changes], t_hello=repr(r.t_hello))


def tutti():
    return [dict(sc=sc, res=esegui(sc)) for sc in scenari()]


if __name__ == "__main__":
    dati = tutti()
    if len(sys.argv) > 1 and sys.argv[1] == "scrivi":
        with open(GOLDEN, "w") as f:
            json.dump(dati, f, sort_keys=True)
        print("scritti", len(dati), "scenari in", GOLDEN)
    else:
        print(len(dati), "scenari;", sum(1 for d in dati if d["res"]["ok"]), "riusciti")
