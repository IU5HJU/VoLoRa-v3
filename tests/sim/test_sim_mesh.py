"""Prove del simulatore mesh: python3 -I tests/sim/test_sim_mesh.py"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import mesh_beacon as mb  # noqa: E402
import protocollo_immagini as pi  # noqa: E402
import sim_mesh as sm  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


# ---- beacon: la simulazione concorda con le formule ----
bw, sf = mb.GRADINI["R14"]
t = mb.tempo_aria(sf, bw, mb.BYTE_SOLO_NOMINATIVO)[0]
T = 600.0
rng = random.Random(1)
for n in (5, 20):
    sim = sm.beacon_puro(n, t, T, 3000, rng)
    form = mb.aloha_puro(n, t, T)
    check(abs(sim - form) < 0.04, f"beacon puro, {n} stazioni a R14: simulato {sim * 100:.1f} %, formula {form * 100:.1f} %")
slots = int(T // t)
sl = sm.beacon_slot(20, t, T, 4000, rng)
check(abs(sl - (1 - 1 / slots) ** 19) < 0.03, f"slot dal nominativo, 20 stazioni: simulato {sl * 100:.1f} %, atteso {(1 - 1 / slots) ** 19 * 100:.1f} %")
ad5 = sm.beacon_slot_adattivo(5, t, T, 200, rng)
check(ad5 > 0.99, f"slot adattivo con 5 stazioni: {ad5 * 100:.1f} % (nessuna collisione dopo l'assestamento)")
ad20, pu20 = sm.beacon_slot_adattivo(20, t, T, 200, rng), sm.beacon_puro(20, t, T, 2000, rng)
check(ad20 > 0.95 and ad20 > pu20 + 0.4, f"slot adattivo con 20 stazioni: {ad20 * 100:.1f} % contro {pu20 * 100:.1f} % del puro")
pu50, as50 = sm.beacon_puro(50, t, T, 1500, rng), sm.beacon_ascolto(50, t, T, 600, rng, vuln=2 * 2 ** sf / (bw * 1000))
check(as50 > pu50 + 0.3, f"ascolto prima di parlare con 50 stazioni: {as50 * 100:.1f} % contro {pu50 * 100:.1f} % del puro")
# terminali nascosti: piu' stazioni non si sentono, peggio l'ascolto
v = 2 * 2 ** sf / (bw * 1000)
h0, h2, h5 = (sm.beacon_ascolto(50, t, T, 300, random.Random(1), v, h) for h in (0.0, 0.2, 0.5))
check(h0 > h2 > h5, f"terminali nascosti, 50 stazioni: {h0 * 100:.0f} % senza, {h2 * 100:.0f} % con 20 %, {h5 * 100:.0f} % con 50 % di coppie nascoste")
check(sm.EPS < 0.02, f"sovrapposizione della fontana misurata: {sm.EPS * 100:.2f} % (non piu' l'ipotesi del 5 %)")
# l'ordine dei metodi con 5 stazioni
check(sm.beacon_puro(5, t, T, 3000, rng) < sm.beacon_slot(5, t, T, 3000, rng) < 1.0, "con 5 stazioni: slot meglio del puro")

# ---- collegamenti ----
check(sm.best_rung(-60.0) == 0 and sm.best_rung(-200.0) is None, "gradino piu' veloce con segnale forte, nessuno con segnale assente")
rungs = [sm.best_rung(p) for p in (-100, -110, -120, -130, -135, -140)]
check(all(a is not None for a in rungs) and rungs == sorted(rungs), f"piu' debole il segnale, gradino piu' lento (indice piu' alto): {rungs}")

# ---- la regola pochi e veloci ----
c5 = [("A", 4, 4, 4), ("B", 5, 5, 5), ("C", 6, 6, 6), ("D", 7, 7, 7), ("E", 10, 10, 10)]
check([m[0] for m in sm.policy_rule(c5, 2, 1)] == ["A", "B"], "5 candidati (R4, R5, R6, R7, R10): la regola 2/1 sceglie A e B")
check([m[0] for m in sm.policy_rule([("A", 4, 4, 4), ("B", 7, 7, 7)], 2, 1)] == ["A"], "il secondo e' troppo lento (3 gradini): resta solo il migliore")
check([m[0] for m in sm.policy_rule(c5, 3, 2)] == ["A", "B", "C"], "regola 3/2: tre stazioni se la terza e' entro 2 gradini")
check(sm.policy_rule([], 2, 1) == [], "nessun candidato: nessun gruppo")
t_rule = sm.time_group(20000, sm.policy_rule(c5, 2, 1))
t_all = sm.time_group(20000, c5)
check(t_all > 10 * t_rule, f"tutti e cinque: {pi.fmt_time(t_all)} contro {pi.fmt_time(t_rule)} con la regola (la quinta stazione costa piu' di 10 volte)")
# il gradino comune e' quello del piu' lento dei membri, i membri in piu' non aggiungono velocita'
t1 = sm.time_group(20000, c5[:1], fountain=False)
t2 = sm.time_group(20000, [("A", 4, 4, 4), ("A2", 4, 4, 4)])
check(t2 >= t1 and t2 < 1.2 * t1, f"due membri alla stessa qualita': tempo quasi uguale ({pi.fmt_time(t1)} e {pi.fmt_time(t2)}): la ridondanza non dà velocita'")

# ---- Monte Carlo ----
r1 = sm.run_gruppo(3, 25.0, scenarios=500, seed=3)
r2 = sm.run_gruppo(3, 25.0, scenarios=500, seed=3)
check(r1 == r2, "stessa semente, stesso risultato")
check(r1["tutti"]["tempo_mediano"] > 3 * r1["regola"]["tempo_mediano"], f"tutti i ripetitori contro la regola: {pi.fmt_time(r1['tutti']['tempo_mediano'])} contro {pi.fmt_time(r1['regola']['tempo_mediano'])}")
check(r1["regola"]["completamento"] > r1["migliore"]["completamento"] + 0.03, f"la regola completa piu' spesso del solo migliore: {r1['regola']['completamento'] * 100:.1f} % contro {r1['migliore']['completamento'] * 100:.1f} %")
check(r1["regola"]["tempo_mediano"] < r1["diretto"]["tempo_mediano"] / 2, f"a 25 km la ripetizione e' molto piu' veloce del diretto: {pi.fmt_time(r1['regola']['tempo_mediano'])} contro {pi.fmt_time(r1['diretto']['tempo_mediano'])}")
check(r1["diretto o regola"]["tempo_mediano"] <= r1["regola"]["tempo_mediano"] and r1["regola"]["copertura"] > 0.9, "diretto-o-regola non e' mai peggiore della regola")
tar = sm.run_tara(3, 25.0, [(1, 0), (2, 1), (3, 4)], scenarios=400, seed=2)
check(tar[(2, 1)][1] > tar[(1, 0)][1] and tar[(3, 4)][0] > 3 * tar[(2, 1)][0], "taratura: 2/1 piu' affidabile di 1/0; tolleranza 4 molto piu' lenta")


# ---- terminali nascosti nel gruppo di ripetitori ----
def _sc(dx1, dx2):
    sc = sm.Scenario(random.Random(5), 0, 25.0, extra_db=15.0, shadow_sigma=0.0)
    sc.pos["R0"], sc.pos["R1"] = (12.0, dx1), (12.0, dx2)
    sc.relays = ["R0", "R1"]
    sc._shadow[("R0", "R1")] = -60.0          # i due ripetitori non si sentono (terminali nascosti)
    return sc


mem = [("R0", 4, 4, 4), ("R1", 4, 4, 4)]
sym = _sc(2.0, -2.0)
check(sm.coppie_nascoste(sym, mem) == 1 and not sym.hears("R0", "R1", 4), "scenario costruito: due ripetitori che non si sentono")
check(sm.efficienza_canale(sym, mem, "turni", random.Random(1)) == 1.0, "turni dall'orologio: il canale rende il 100 % anche con i terminali nascosti")
check(sm.efficienza_canale(sym, mem, "ascolto", random.Random(1)) == 0.0, "ascolto con due nascosti ugualmente forti: parlano insieme e si perdono sempre")
asym = _sc(0.2, 30.0)
e_cap = sm.efficienza_canale(asym, mem, "ascolto", random.Random(1))
check(e_cap > 0.9, f"se uno e' piu' forte di 6 dB la cattura salva il canale: {e_cap * 100:.0f} %")
vis = _sc(2.0, -2.0)
vis._shadow[("R0", "R1")] = 0.0
check(sm.efficienza_canale(vis, mem, "ascolto", random.Random(1)) == 1.0, "se i due si sentono l'ascolto basta: 100 %")
nr1, nr2 = sm.run_nascosti(4, 25.0, scenarios=300, seed=4), sm.run_nascosti(4, 25.0, scenarios=300, seed=4)
check(nr1 == nr2, "stessa semente, stesso risultato")
check(nr1["turni"]["efficienza"] == 1.0 and nr1["ascolto"]["efficienza"] < 1.0 and nr1["ascolto"]["completamento"] < nr1["turni"]["completamento"],
      f"con i nascosti l'ascolto rende {nr1['ascolto']['efficienza'] * 100:.0f} % e completa {nr1['ascolto']['completamento'] * 100:.1f} % contro {nr1['turni']['completamento'] * 100:.1f} % dei turni")
print("simulatore mesh: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
