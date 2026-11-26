"""Prove dell'elezione fra due nodi in isofrequenza: python3 -I tests/sim/test_voting.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import sim_voting as sv  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


kw = dict(scenari=1500, seed=3)
nn = sv.run_elezione("nessuna", "nessuno", **kw)
check(nn["casi"] > 100 and nn["doppio_accesso"] == 1.0, f"senza regola i due nodi partono sempre insieme ({nn['casi']} casi)")
cr = sv.run_elezione("casuale", "rf", nodi_si_sentono=True, **kw)
qr = sv.run_elezione("qualita", "rf", nodi_si_sentono=True, **kw)
check(cr["doppio_accesso"] < 0.2 and qr["doppio_accesso"] < 0.2, f"se i nodi si sentono in RF l'ascolto evita quasi sempre il doppio accesso ({cr['doppio_accesso'] * 100:.1f} % e {qr['doppio_accesso'] * 100:.1f} %)")
check(qr["migliore_se_unico"] > 0.9 and cr["migliore_se_unico"] < 0.7, f"con il ritardo per qualita' parte il nodo migliore ({qr['migliore_se_unico'] * 100:.0f} %), con il ritardo casuale e' un sorteggio ({cr['migliore_se_unico'] * 100:.0f} %)")
hid = sv.run_elezione("qualita", "rf", nodi_si_sentono=False, **kw)
check(hid["doppio_accesso"] == 1.0, "nodi che non si sentono e nessun altro annuncio: doppio accesso sempre (serve un annuncio via rete)")
net = sv.run_elezione("qualita", "rete", nodi_si_sentono=False, **kw)
check(net["doppio_accesso"] < 0.6 and net["migliore_se_unico"] > 0.95, f"annuncio via rete: doppio accesso {net['doppio_accesso'] * 100:.0f} %, nodo migliore {net['migliore_se_unico'] * 100:.0f} %")
w0 = sv.W
sv.W = 0.8
big = sv.run_elezione("qualita", "rete", nodi_si_sentono=False, **kw)
sv.W = w0
check(big["doppio_accesso"] < net["doppio_accesso"] and big["ritardo_medio_s"] > net["ritardo_medio_s"], "ritardo massimo piu' grande: meno doppi accessi ma piu' ritardo")
c0, c3, c6 = (sv.run_percorso(h, prove=150, seed=2) for h in (0.0, 3.0, 6.0))
check(c0 > c3 > c6 and c0 > 2 * c3 - 1, f"isteresi lungo il percorso: cambi di nodo {c0:.1f} (0 dB), {c3:.1f} (3 dB), {c6:.1f} (6 dB)")
vr = sv.run_voto_radio(20.0, scenari=1500, seed=3)
vr2 = sv.run_voto_radio(20.0, scenari=1500, seed=3, repeat=2)
check(vr["senza_collegamento"] < 0.03 and vr["durata_voto_s"] <= sv.W, f"voto via radio a 20 km: modo {vr['gradino_mediano']}, durata {vr['durata_voto_s'] * 1000:.0f} ms (entra in {sv.W * 1000:.0f} ms)")
check(vr["doppio_accesso"] < 0.09 and vr["migliore_se_unico"] > 0.9, f"voto via radio: doppio accesso {vr['doppio_accesso'] * 100:.1f} %, nodo migliore {vr['migliore_se_unico'] * 100:.0f} %")
check(vr2["doppio_accesso"] < vr["doppio_accesso"] and vr2["durata_voto_s"] > vr["durata_voto_s"], "ripetere il VOTO: meno doppi accessi, voto piu' lungo")
far = sv.run_voto_radio(20.0, extra_nodi=60.0, scenari=800, seed=3)
check(far["doppio_accesso"] == 1.0 and far["senza_collegamento"] == 1.0, "nodi che non si sentono sul canale di servizio: nessun voto, doppio accesso (zona non ammessa)")
check(sv.run_elezione("qualita", "rete", nodi_si_sentono=False, **kw) == net, "stessa semente, stesso risultato")
print("voting: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
