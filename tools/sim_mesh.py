#!/usr/bin/env python3
"""Simulatore mesh V3 (bozza, docs/mesh-v3.md): beacon con collisioni e scelta del gruppo di ripetitori a fontana.

  python3 tools/sim_mesh.py beacon --stazioni 5 --gradino R14          # collisioni dei beacon: puro, slot, slot adattivo, ascolto
  python3 tools/sim_mesh.py gruppo --ripetitori 3 --distanza 25        # regola "pochi e veloci" contro le alternative

Modello (ipotesi di lavoro, NON misure):
 * beacon: tempo in aria da tools/mesh_beacon.py; tutte le stazioni sentono tutte (nessun terminale nascosto); un beacon collide se si sovrappone a un altro;
 * collegamenti: perdita in spazio libero a 433,5 MHz piu' una perdita extra media (ostacoli) con ombreggiamento casuale fisso per collegamento;
   un collegamento usa il gradino piu' veloce che ha almeno 6 dB di margine sulla sensibilita' STIMATA (docs/scala-modi.md);
 * il canale e' uno solo: i membri di un gruppo trasmettono a turni allo stesso gradino, quindi la velocita' e' quella del gradino comune (il piu' lento
   dei membri); piu' membri danno ridondanza, non velocita'."""
import argparse
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mesh_beacon as mb  # noqa: E402
import protocollo_immagini as pi  # noqa: E402

MARGIN_DB = 6.0
N_RUNGS = len(pi.RUNGS)


# ------------------------------------------------------------------------------------------------------------------- beacon
def _overlap(starts, t):
    """Per ogni inizio, True se si sovrappone a un altro beacon (durata t)."""
    order = sorted(range(len(starts)), key=lambda i: starts[i])
    bad = [False] * len(starts)
    for a, b in zip(order, order[1:]):
        if starts[b] - starts[a] < t:
            bad[a] = bad[b] = True
    return bad


def beacon_puro(n, t, period, cycles, rng):
    """Ogni stazione sceglie un istante a caso in ogni periodo. Ritorna la frazione di beacon senza collisione."""
    ok = tot = 0
    for _ in range(cycles):
        bad = _overlap([rng.uniform(0, period - t) for _ in range(n)], t)
        ok += n - sum(bad)
        tot += n
    return ok / tot


def beacon_slot(n, t, period, cycles, rng):
    """Slot fissi dall'orologio: ogni stazione ha uno slot calcolato dal nominativo (casuale ma fisso)."""
    slots = max(1, int(period // t))
    ok = tot = 0
    for _ in range(cycles):                       # un insieme nuovo di nominativi per ciclo = media su tanti nominativi
        mine = [rng.randrange(slots) for _ in range(n)]
        for s in mine:
            ok += mine.count(s) == 1
        tot += n
    return ok / tot


def beacon_slot_adattivo(n, t, period, cycles, rng, warmup=10):
    """Slot con ascolto: chi collide sceglie un nuovo slot fra quelli che ha sentito liberi nel ciclo precedente. Misura dopo `warmup` cicli."""
    slots = max(1, int(period // t))
    mine = [rng.randrange(slots) for _ in range(n)]
    ok = tot = 0
    for c in range(cycles + warmup):
        counts = {}
        for s in mine:
            counts[s] = counts.get(s, 0) + 1
        occupied_ok = {s for s, k in counts.items() if k == 1}
        if c >= warmup:
            ok += sum(1 for s in mine if counts[s] == 1)
            tot += n
        free = [s for s in range(slots) if s not in counts]
        for i, s in enumerate(mine):
            if counts[s] > 1:
                pool = free if free else list(range(slots))
                mine[i] = rng.choice(pool)
                if mine[i] in free:
                    free.remove(mine[i])
    return ok / tot


def beacon_ascolto(n, t, period, cycles, rng, vuln=None):
    """Ascolto prima di parlare: una stazione che trova il canale occupato aspetta la fine e un ritardo casuale; collide solo se due iniziano entro la
    finestra di rilevamento `vuln` (di base 2 simboli LoRa: il preambolo non si sente subito)."""
    ok = tot = 0
    for _ in range(cycles):
        want = sorted((rng.uniform(0, period - t), i) for i in range(n))
        busy_until = -1.0
        last_start = -1e9
        started = []
        queue = list(want)
        while queue:
            queue.sort()
            s, i = queue.pop(0)
            if s < busy_until and s - last_start >= (vuln or 0.0):
                queue.append((busy_until + rng.uniform(0, 4 * t), i))     # canale occupato e rilevato: ritarda
                continue
            started.append(s)
            last_start = s
            busy_until = max(busy_until, s + t)
        bad = _overlap(started, t)
        ok += n - sum(bad)
        tot += n
    return ok / tot


# --------------------------------------------------------------------------------------------------------------- collegamenti
def fspl_db(d_km):
    return 85.2 + 20 * math.log10(max(d_km, 0.05))


def best_rung(prx_dbm):
    """Il gradino piu' veloce (indice piu' basso) con almeno MARGIN_DB di margine; None se nessuno."""
    for rid in range(N_RUNGS):
        if prx_dbm - pi.sensitivity_dbm(rid) >= MARGIN_DB:
            return rid
    return None


class Scenario:
    def __init__(self, rng, n_relays, dist_km, ptx=10.0, extra_db=25.0, shadow_sigma=8.0):
        self.rng = rng
        self.dist = dist_km
        self.pos = {"S": (0.0, 0.0), "D": (dist_km, 0.0)}
        for i in range(n_relays):
            self.pos[f"R{i}"] = (rng.uniform(-0.1 * dist_km, 1.1 * dist_km), rng.uniform(-0.5 * dist_km, 0.5 * dist_km))
        self.ptx, self.extra, self.sigma = ptx, extra_db, shadow_sigma
        self._shadow = {}
        self.relays = [k for k in self.pos if k.startswith("R")]

    def rung(self, a, b):
        key = tuple(sorted((a, b)))
        if key not in self._shadow:
            self._shadow[key] = self.rng.gauss(0.0, self.sigma)
        (x1, y1), (x2, y2) = self.pos[a], self.pos[b]
        d = math.hypot(x1 - x2, y1 - y2)
        prx = self.ptx - fspl_db(d) - self.extra + self._shadow[key]
        return best_rung(prx)


def candidates(sc):
    """[(nome, rung S->R, rung R->D, qualita'=il piu' lento dei due)] ordinati dal migliore, solo quelli che hanno entrambi i collegamenti."""
    out = []
    for r in sc.relays:
        r1, r2 = sc.rung("S", r), sc.rung(r, "D")
        if r1 is not None and r2 is not None:
            out.append((r, r1, r2, max(r1, r2)))
    return sorted(out, key=lambda c: c[3])


# ------------------------------------------------------------------------------------------------------------------ politiche
EPS = 0.05    # sovrapposizione della fontana: servono K(1+eps) simboli


def time_group(size, members, fountain=True):
    """Fase 1: il mittente trasmette l'oggetto a tutti i membri al gradino del piu' lento dei suoi collegamenti. Fase 2: i membri trasmettono a turni
    verso il destinatario al gradino comune (il piu' lento dei loro collegamenti). Un solo canale: la velocita' e' quella del gradino comune."""
    r1 = max(m[1] for m in members)
    r2 = max(m[2] for m in members)
    return pi.estimate_seconds(size, r1) + pi.estimate_seconds(int(size * ((1 + EPS) if fountain and len(members) > 1 else 1)), r2)


def policy_rule(cands, n_min=2, tol=1):
    """Gruppo piu' piccolo di almeno n_min stazioni il cui gradino comune non e' piu' lento del migliore di oltre `tol` gradini; altrimenti solo il migliore."""
    if not cands:
        return []
    if len(cands) >= n_min and cands[n_min - 1][3] <= cands[0][3] + tol:
        return cands[:n_min]
    return cands[:1]


def evaluate(policy, sc, size, p_fail):
    """(tempo in s, probabilita' di completare) per una politica; None se non c'e' percorso."""
    cands = candidates(sc)
    if policy == "diretto":
        r = sc.rung("S", "D")
        return None if r is None else (pi.estimate_seconds(size, r), 1.0)
    if policy == "migliore":
        members = cands[:1]
    elif policy == "tutti":
        members = cands
    elif policy == "regola":
        members = policy_rule(cands)
    else:
        raise ValueError(policy)
    if not members:
        return None
    return time_group(size, members), 1.0 - p_fail ** len(members)


def run_gruppo(n_relays, dist_km, size=20000, scenarios=2000, p_fail=0.15, seed=1, extra_db=25.0):
    rng = random.Random(seed)
    res = {k: {"t": [], "p": [], "cover": 0} for k in ("diretto", "migliore", "tutti", "regola", "diretto o regola")}
    for _ in range(scenarios):
        sc = Scenario(rng, n_relays, dist_km, extra_db=extra_db)
        ev = {k: evaluate(k, sc, size, p_fail) for k in ("diretto", "migliore", "tutti", "regola")}
        # "diretto o regola": il diretto se c'e' ed e' piu' veloce del gruppo, altrimenti il gruppo
        d, g = ev["diretto"], ev["regola"]
        if d and (not g or d[0] <= g[0]):
            ev["diretto o regola"] = d
        else:
            ev["diretto o regola"] = g
        for k, v in ev.items():
            if v:
                res[k]["cover"] += 1
                res[k]["t"].append(v[0])
                res[k]["p"].append(v[1])
    out = {}
    for k, r in res.items():
        out[k] = {"copertura": r["cover"] / scenarios,
                  "tempo_mediano": statistics.median(r["t"]) if r["t"] else float("nan"),
                  "completamento": statistics.mean(r["p"]) if r["p"] else float("nan")}
    return out


def run_tara(n_relays, dist_km, combos, size=20000, scenarios=2000, p_fail=0.15, seed=1, extra_db=25.0):
    """Per ogni (n_min, tolleranza) il tempo mediano e la probabilita' media di completare, sugli stessi scenari."""
    rng = random.Random(seed)
    acc = {c: {"t": [], "p": []} for c in combos}
    for _ in range(scenarios):
        sc = Scenario(rng, n_relays, dist_km, extra_db=extra_db)
        cands = candidates(sc)
        for (n_min, tol) in combos:
            members = policy_rule(cands, n_min, tol)
            if members:
                acc[(n_min, tol)]["t"].append(time_group(size, members))
                acc[(n_min, tol)]["p"].append(1.0 - p_fail ** len(members))
    return {c: (statistics.median(v["t"]), statistics.mean(v["p"])) for c, v in acc.items() if v["t"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("beacon")
    b.add_argument("--stazioni", type=int, default=5)
    b.add_argument("--gradino", default="R14", choices=list(mb.GRADINI))
    b.add_argument("--intervallo", type=float, default=10.0, help="minuti")
    b.add_argument("--cicli", type=int, default=3000)
    b.add_argument("--seed", type=int, default=1)
    tr = sub.add_parser("tara", help="confronta i valori di N_min e tolleranza della regola")
    tr.add_argument("--ripetitori", type=int, default=3)
    tr.add_argument("--distanza", type=float, default=25.0)
    tr.add_argument("--scenari", type=int, default=2000)
    tr.add_argument("--guasto", type=float, default=0.15)
    tr.add_argument("--seed", type=int, default=1)
    g = sub.add_parser("gruppo")
    g.add_argument("--ripetitori", type=int, default=3)
    g.add_argument("--distanza", type=float, default=25.0, help="km fra mittente e destinatario")
    g.add_argument("--dimensione", type=int, default=20000)
    g.add_argument("--scenari", type=int, default=2000)
    g.add_argument("--guasto", type=float, default=0.15, help="probabilita' che un ripetitore cada durante il trasferimento")
    g.add_argument("--extra", type=float, default=25.0, help="perdita extra media (ostacoli), dB")
    g.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    if a.cmd == "beacon":
        bw, sf = mb.GRADINI[a.gradino]
        t = mb.tempo_aria(sf, bw, mb.BYTE_SOLO_NOMINATIVO)[0]
        T = a.intervallo * 60
        rng = random.Random(a.seed)
        print(f"{a.stazioni} stazioni, beacon da {t:.1f} s a {a.gradino}, uno ogni {a.intervallo:g} min (carico G = {a.stazioni * t / T:.3f}); percentuale di beacon senza collisione:")
        print(f"  ALOHA puro (formula)  {100 * mb.aloha_puro(a.stazioni, t, T):5.1f} %")
        print(f"  puro (simulato)       {100 * beacon_puro(a.stazioni, t, T, a.cicli, rng):5.1f} %")
        print(f"  slot dal nominativo   {100 * beacon_slot(a.stazioni, t, T, a.cicli, rng):5.1f} %")
        print(f"  slot adattivo         {100 * beacon_slot_adattivo(a.stazioni, t, T, 300, rng):5.1f} %")
        print(f"  ascolto prima         {100 * beacon_ascolto(a.stazioni, t, T, min(a.cicli, 1500), rng, vuln=2 * 2 ** sf / (bw * 1000)):5.1f} %")
        return
    if a.cmd == "tara":
        combos = [(1, 0), (2, 0), (2, 1), (2, 2), (3, 1), (3, 2), (3, 4)]
        res = run_tara(a.ripetitori, a.distanza, combos, scenarios=a.scenari, p_fail=a.guasto, seed=a.seed)
        print(f"{a.ripetitori} ripetitori, {a.distanza:g} km, un ripetitore su {1 / a.guasto:.0f} cade, {a.scenari} scenari")
        print("| N_min | tolleranza | tempo mediano | completa |")
        print("|---|---|---|---|")
        for c in combos:
            tm, pc = res[c]
            print(f"| {c[0]} | {c[1]} | {pi.fmt_time(tm)} | {100 * pc:.1f} % |")
        return
    res = run_gruppo(a.ripetitori, a.distanza, a.dimensione, a.scenari, a.guasto, a.seed, a.extra)
    print(f"{a.ripetitori} ripetitori candidati, mittente e destinatario a {a.distanza:g} km, oggetto {a.dimensione} byte, perdita extra {a.extra:g} dB, "
          f"un ripetitore su {1 / a.guasto:.0f} cade, {a.scenari} scenari")
    print("| politica | copertura | tempo mediano | completa |")
    print("|---|---|---|---|")
    for k, r in res.items():
        tm = pi.fmt_time(r["tempo_mediano"]) if r["tempo_mediano"] == r["tempo_mediano"] else "—"
        print(f"| {k} | {100 * r['copertura']:.0f} % | {tm} | {100 * r['completamento']:.1f} % |")


if __name__ == "__main__":
    main()
