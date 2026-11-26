"""Prove del nodo a scheda singola: python3 -I tests/sim/test_nodo_semplice.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import nodo_semplice as ns  # noqa: E402
import sim_voting as sv  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


check(ns.azione_voce(True, 100.0, 200.0, 10.0) == ("rete", 0.0), "con Internet: la voce va in rete, nessuna ritrasmissione in RF")
check(ns.azione_voce(False, None, 1000.0, 10.0) == ("pappagallo", 0.0), "senza Internet e senza altri nodi sentiti: pappagallo senza attesa")
check(ns.azione_voce(False, 0.0, 1800.0, 10.0)[1] > 0.0 and ns.azione_voce(False, 0.0, 1801.0, 10.0)[1] == 0.0, "l'isolamento dura 30 minuti dall'ultimo nodo sentito")
az, d_forte = ns.azione_voce(False, 990.0, 1000.0, 30.0)
_, d_debole = ns.azione_voce(False, 990.0, 1000.0, 0.0)
check(az == "pappagallo" and abs(d_forte - 0.3) < 1e-9 and abs(d_debole - 0.7) < 1e-9, f"con vicini: 300 ms fissi + fino a 400 ms per qualita' ({d_forte * 1000:.0f}-{d_debole * 1000:.0f} ms)")
check(ns.deve_ripetere(False) and not ns.deve_ripetere(True), "ripete solo se non ha sentito partire un altro nodo")
r4, r8 = sv.run_due_muti(20.0, 0.4, scenari=2000, seed=3), sv.run_due_muti(20.0, 0.8, scenari=2000, seed=3)
r2 = sv.run_due_muti(20.0, 0.2, scenari=2000, seed=3)
check(r2["doppio_accesso"] > r4["doppio_accesso"] > r8["doppio_accesso"] and r4["doppio_accesso"] < 0.08, f"fra due nodi muti: piu' largo il ritardo, meno doppi accessi ({r2['doppio_accesso'] * 100:.1f} %, {r4['doppio_accesso'] * 100:.1f} %, {r8['doppio_accesso'] * 100:.1f} %)")
print("nodo a scheda singola: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
