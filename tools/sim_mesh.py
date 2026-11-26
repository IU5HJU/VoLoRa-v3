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


def beacon_ascolto(n, t, period, cycles, rng, vuln=None, nascosti=0.0):
    """Ascolto prima di parlare: una stazione che trova il canale occupato aspetta la fine e un ritardo casuale; collide solo se due iniziano entro la
    finestra di rilevamento `vuln` (di base 2 simboli LoRa: il preambolo non si sente subito).
    `nascosti` = probabilita' che due stazioni non si sentano fra loro (terminali nascosti): ognuna ascolta solo chi sente."""
    ok = tot = 0
    for _ in range(cycles):
        sente = {}
        for i in range(n):
            for j in range(i + 1, n):
                sente[(i, j)] = sente[(j, i)] = rng.random() >= nascosti
        queue = sorted((rng.uniform(0, period - t), i) for i in range(n))
        tx = []                                    # (inizio, fine, stazione)
        started = []
        while queue:
            queue.sort()
            s, i = queue.pop(0)
            sentiti = [(a, b, j) for (a, b, j) in tx if sente[(i, j)] and a <= s < b and s - a >= (vuln or 0.0)]
            if sentiti:
                queue.append((max(b for _, b, _ in sentiti) + rng.uniform(0, 4 * t), i))
                continue
            tx.append((s, s + t, i))
            started.append(s)
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

    def prx(self, a, b):
        """Potenza ricevuta in dBm fra due stazioni (uguale nei due sensi)."""
        key = tuple(sorted((a, b)))
        if key not in self._shadow:
            self._shadow[key] = self.rng.gauss(0.0, self.sigma)
        (x1, y1), (x2, y2) = self.pos[a], self.pos[b]
        d = math.hypot(x1 - x2, y1 - y2)
        return self.ptx - fspl_db(d) - self.extra + self._shadow[key]

    def rung(self, a, b):
        return best_rung(self.prx(a, b))

    def hears(self, a, b, rid):
        """True se a e b si sentono al gradino rid (basta rilevare il segnale: sopra la sensibilita', senza margine). Altrimenti sono terminali nascosti."""
        return self.prx(a, b) - pi.sensitivity_dbm(rid) >= 0.0


def candidates(sc):
    """[(nome, rung S->R, rung R->D, qualita'=il piu' lento dei due)] ordinati dal migliore, solo quelli che hanno entrambi i collegamenti."""
    out = []
    for r in sc.relays:
        r1, r2 = sc.rung("S", r), sc.rung(r, "D")
        if r1 is not None and r2 is not None:
            out.append((r, r1, r2, max(r1, r2)))
    return sorted(out, key=lambda c: c[3])


# ------------------------------------------------------------------------------------------------------------------ politiche
EPS = 1.6 / 128    # sovrapposizione della fontana MISURATA con tools/fontana.py: ~1,6 simboli per generazione di 128 pezzi


CAPTURE_DB = 6.0     # LoRa: se un segnale supera l'altro di almeno 6 dB al ricevitore, il piu' forte si decodifica lo stesso


def efficienza_canale(sc, members, accesso, rng, slots=400):
    """Frazione del tempo di fase 2 che produce simboli utili al destinatario.
    'turni': un solo membro per volta, dai turni assegnati nel GRUPPO con l'orologio: 1.0.
    'ascolto': ogni membro ha sempre simboli da mandare e prima di parlare ascolta. Parla se non sente nessuno di quelli che hanno gia' cominciato.
    Due membri che non si sentono (terminali nascosti) parlano insieme: al destinatario si sovrappongono e si perdono, salvo la cattura (segnale piu' forte di 6 dB)."""
    if accesso == "turni" or len(members) < 2:
        return 1.0
    rid = max(m[2] for m in members)
    names = [m[0] for m in members]
    utili = 0
    for _ in range(slots):
        order = names[:]
        rng.shuffle(order)
        tx = []
        for n in order:
            if not any(sc.hears(n, o, rid) for o in tx):
                tx.append(n)
        if len(tx) == 1:
            utili += 1
        else:
            p = sorted((sc.prx(n, "D") for n in tx), reverse=True)
            utili += 1 if p[0] - p[1] >= CAPTURE_DB else 0
    return utili / slots


def coppie_nascoste(sc, members):
    """Numero di coppie di membri che non si sentono fra loro al gradino comune."""
    rid = max(m[2] for m in members)
    names = [m[0] for m in members]
    return sum(1 for i in range(len(names)) for j in range(i + 1, len(names)) if not sc.hears(names[i], names[j], rid))


def run_nascosti(n_relays, dist_km, size=20000, scenarios=1000, p_fail=0.15, seed=1, extra_db=25.0, n_min=2, tol=1):
    """La regola (n_min, tol) con i membri che si accordano con i turni dall'orologio, contro membri che parlano dopo aver ascoltato: stessi scenari."""
    rng = random.Random(seed)
    slot_rng = random.Random(seed + 1)
    acc = {a: {"t": [], "p": [], "eff": []} for a in ("turni", "ascolto")}
    eff_nasc = []
    n = nasc = 0
    for _ in range(scenarios):
        sc = Scenario(rng, n_relays, dist_km, extra_db=extra_db)
        members = policy_rule(candidates(sc), n_min, tol)
        if not members:
            continue
        n += 1
        hid = coppie_nascoste(sc, members) > 0
        nasc += 1 if hid else 0
        for a in acc:
            eff = efficienza_canale(sc, members, a, slot_rng)
            if hid and a == "ascolto":
                eff_nasc.append(eff)
            acc[a]["eff"].append(eff)
            acc[a]["t"].append(time_group(size, members, eff2=eff))
            acc[a]["p"].append((1.0 - p_fail ** len(members)) if eff > 0.02 else 0.0)
    out = {"scenari": n, "con_coppia_nascosta": nasc / n if n else float("nan"),
           "efficienza_con_coppia": statistics.mean(eff_nasc) if eff_nasc else float("nan")}
    for a, v in acc.items():
        out[a] = {"tempo_mediano": statistics.median(v["t"]), "completamento": statistics.mean(v["p"]), "efficienza": statistics.mean(v["eff"])}
    return out


def time_group(size, members, fountain=True, eff2=1.0):
    """Fase 1: il mittente trasmette l'oggetto a tutti i membri al gradino del piu' lento dei suoi collegamenti. Fase 2: i membri trasmettono a turni
    verso il destinatario al gradino comune (il piu' lento dei loro collegamenti). Un solo canale: la velocita' e' quella del gradino comune."""
    r1 = max(m[1] for m in members)
    r2 = max(m[2] for m in members)
    return pi.estimate_seconds(size, r1) + pi.estimate_seconds(int(size * ((1 + EPS) if fountain and len(members) > 1 else 1)), r2) / max(eff2, 0.02)


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


# ------------------------------------------------------------------------------------------------- risposte OFFERTA con terminali nascosti
OFFER_BYTES = 24      # frame_mesh.enc_offer_relay
SLOTS = 8             # slot della finestra di risposta
GUARD_S = 0.15


def _overlaps(iv, i, j):
    return iv[i][0] < iv[j][1] and iv[j][0] < iv[i][1]


def _round(policy, cands, sc, rng, t_o, vuln=0.05, slots=SLOTS, attempt=0):
    """Un giro di risposte OFFERTA al mittente. cands = nomi dei candidati ancora senza conferma. Ritorna {nome: istante di fine} per chi arriva integro."""
    iv = {}
    if policy == "ascolto":
        wend = slots * (t_o + GUARD_S)
        q = sorted((rng.uniform(0, wend - t_o), c) for c in cands)
        tx = []
        while q:
            q.sort()
            s, c = q.pop(0)
            heard = [e for (a, e, o) in tx if sc.hears(c, o, 10) and a <= s < e and s - a >= vuln]
            if heard:
                q.append((max(heard) + rng.uniform(0, t_o), c))
                continue
            tx.append((s, s + t_o, c))
            iv[c] = (s, s + t_o)
    elif policy == "slot_ascolto":                              # slot dal nominativo, e chi sente un altro in corso aspetta il primo slot libero dopo
        step = t_o + GUARD_S
        q = sorted((rng.randrange(slots) * step, c) for c in cands)
        tx = []
        while q:
            q.sort()
            s0, c = q.pop(0)
            heard = [e for (a, e, o) in tx if sc.hears(c, o, 10) and a <= s0 < e]
            if heard:
                q.append((math.ceil(max(heard) / step) * step + rng.randrange(0, 2) * step, c))
                continue
            tx.append((s0, s0 + t_o, c))
            iv[c] = (s0, s0 + t_o)
    else:
        sens = pi.sensitivity_dbm(10)
        for c in cands:
            if policy == "slot_nome":
                slot = rng.randrange(slots)                     # slot dal nominativo (e dal numero del tentativo)
            else:                                               # slot_qualita: 3 dB per slot, il migliore parte per primo; ai tentativi successivi si aggiunge un sorteggio
                m = sc.prx(c, "S") - sens + rng.gauss(0, 1.0)
                slot = min(slots - 1, max(0, int((30.0 - m) // 3.0)) + (rng.randrange(0, 3) if attempt else 0))
            iv[c] = (slot * (t_o + GUARD_S), slot * (t_o + GUARD_S) + t_o)
    ok = {}
    for c in iv:
        others = [o for o in iv if o != c and _overlaps(iv, c, o)]
        if not others:
            ok[c] = iv[c][1]
        else:                                                   # cattura: il piu' forte di 6 dB al mittente sopravvive
            pc = sc.prx(c, "S")
            if all(pc - sc.prx(o, "S") >= CAPTURE_DB for o in others):
                ok[c] = iv[c][1]
    return ok


def run_offerte(policy, n_relays=5, dist_km=25.0, extra_db=25.0, scenari=1500, seed=1, giri=3, slots=SLOTS):
    """Risposte OFFERTA alla RICHIESTA-RIPETITORI: tutti i candidati che sentono il mittente rispondono insieme. Quanti arrivano al primo giro, e in quanto tempo il mittente
    ha le due offerte migliori (quelle che la regola sceglierebbe). I candidati senza conferma ripetono al giro dopo."""
    rng = random.Random(seed)
    sens = pi.sensitivity_dbm(10)
    t_o = pi.frame_airtime_s(10, OFFER_BYTES)
    wend = slots * (t_o + GUARD_S)
    n = tutte = 0
    frac = []
    top2_ok = 0
    tempi = []
    nasc = 0
    for _ in range(scenari):
        sc = Scenario(rng, n_relays, dist_km, extra_db=extra_db)
        cands = [r for r in sc.relays if sc.hears("S", r, 10)]
        if len(cands) < 2:
            continue
        n += 1
        if any(not sc.hears(a, b, 10) for a in cands for b in cands if a < b):
            nasc += 1
        top2 = sorted(cands, key=lambda c: -sc.prx(c, "S"))[:2]
        pending, got = list(cands), {}
        for g in range(giri):
            ok = _round(policy, pending, sc, rng, t_o, slots=slots, attempt=g)
            for c, e in ok.items():
                got[c] = g * wend + e
            pending = [c for c in pending if c not in ok]
            if g == 0:
                frac.append(len(ok) / len(cands))
                tutte += 1 if not pending else 0
            if all(c in got for c in top2):
                break
        if all(c in got for c in top2):
            top2_ok += 1
            tempi.append(max(got[c] for c in top2))
    return {"scenari": n, "con_coppia_nascosta": nasc / n if n else float("nan"), "primo_giro": statistics.mean(frac), "tutte_al_primo_giro": tutte / n,
            "top2_entro_3_giri": top2_ok / n, "tempo_top2_mediano_s": statistics.median(tempi) if tempi else float("nan"), "giro_s": wend}


# ----------------------------------------------------------------------------------------------------- errore dell'orologio nei turni
def run_turni(sigma_s, turn_s, guard_s, membri=3, cicli=20000, seed=1):
    """Turni consecutivi dei membri del gruppo: ognuno parte all'ora del proprio orologio, sbagliata di un errore gaussiano (sigma_s). Fra due turni c'e' la guardia.
    Un turno e' rovinato se si sovrappone a quello vicino. Ritorna (frazione di turni utili, efficienza = utili x turno / (turno + guardia))."""
    rng = random.Random(seed)
    utili = tot = 0
    for _ in range(cicli):
        e = [rng.gauss(0.0, sigma_s) for _ in range(membri)]
        starts = [i * (turn_s + guard_s) + e[i] for i in range(membri)]
        for i in range(membri):
            tot += 1
            bad = False
            if i > 0 and starts[i - 1] + turn_s > starts[i]:
                bad = True
            if i < membri - 1 and starts[i] + turn_s > starts[i + 1]:
                bad = True
            utili += 0 if bad else 1
    f = utili / tot
    return f, f * turn_s / (turn_s + guard_s)


def guardia_minima(sigma_s, turn_s, soglia=0.98):
    """Guardia piu' piccola (a passi di 0,05 s) per cui almeno `soglia` dei turni sono utili."""
    g = 0.0
    while g < 20 * max(sigma_s, 0.05):
        if run_turni(sigma_s, turn_s, g, cicli=4000)[0] >= soglia:
            return g
        g += 0.05
    return g


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
    o = sub.add_parser("offerte", help="risposte OFFERTA alla richiesta di ripetitori con i terminali nascosti")
    o.add_argument("--ripetitori", type=int, default=5)
    o.add_argument("--scenari", type=int, default=1500)
    o.add_argument("--seed", type=int, default=1)
    tu = sub.add_parser("turni", help="errore dell'orologio nei turni del gruppo di ripetitori")
    h = sub.add_parser("nascosti", help="gruppo di ripetitori: turni dall'orologio contro ascolto prima di parlare, con i terminali nascosti")
    h.add_argument("--ripetitori", type=int, default=4)
    h.add_argument("--distanza", type=float, default=25.0)
    h.add_argument("--extra", type=float, default=25.0)
    h.add_argument("--scenari", type=int, default=1000)
    h.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    if a.cmd == "offerte":
        print(f"{a.ripetitori} ripetitori sparsi, 25 km, OFFERTA da {OFFER_BYTES} byte a R10 ({pi.frame_airtime_s(10, OFFER_BYTES):.2f} s), 3 giri al massimo")
        print("| come rispondono | slot | al primo giro | tutte al primo giro | le 2 migliori entro 3 giri | tempo mediano per le 2 migliori | durata del giro |")
        print("|---|---|---|---|---|---|---|")
        for pol, nome, sl in (("ascolto", "ascolto e ritardo casuale", 8), ("slot_nome", "slot dal nominativo", 8), ("slot_nome", "slot dal nominativo", 16), ("slot_nome", "slot dal nominativo", 32),
                              ("slot_qualita", "slot per qualità (il migliore per primo)", 8), ("slot_ascolto", "slot dal nominativo + ascolto", 8), ("slot_ascolto", "slot dal nominativo + ascolto", 16)):
            r = run_offerte(pol, a.ripetitori, scenari=a.scenari, seed=a.seed, slots=sl)
            print(f"| {nome} | {sl} | {100 * r['primo_giro']:.0f} % | {100 * r['tutte_al_primo_giro']:.0f} % | {100 * r['top2_entro_3_giri']:.0f} % | {r['tempo_top2_mediano_s']:.1f} s | {r['giro_s']:.0f} s |")
        print(f"(scenari con almeno una coppia di candidati nascosti: {100 * r['con_coppia_nascosta']:.0f} %; giro = {r['giro_s']:.1f} s)")
        return
    if a.cmd == "turni":
        print("Errore dell'orologio nei turni (3 membri). Guardia minima per il 98 % dei turni utili, e efficienza risultante:")
        print("| errore dell'orologio (sigma) | turno 2 s | turno 5 s | turno 10 s | turno 30 s |")
        print("|---|---|---|---|---|")
        for sg, nome in ((0.02, "NTP, 20 ms"), (0.1, "100 ms"), (0.4, "GPS Bluetooth, 400 ms"), (1.0, "1 s")):
            celle = []
            for tl in (2.0, 5.0, 10.0, 30.0):
                g = guardia_minima(sg, tl)
                _, eff = run_turni(sg, tl, g)
                celle.append(f"g = {g:.2f} s, {100 * eff:.0f} %")
            print(f"| {nome} | " + " | ".join(celle) + " |")
        return
    if a.cmd == "nascosti":
        r = run_nascosti(a.ripetitori, a.distanza, scenarios=a.scenari, seed=a.seed, extra_db=a.extra)
        print(f"{a.ripetitori} ripetitori, {a.distanza:g} km, perdita extra {a.extra:g} dB, regola 2/1, {r['scenari']} scenari con un gruppo; "
              f"gruppi con almeno una coppia nascosta: {100 * r['con_coppia_nascosta']:.0f} % (in questi l'ascolto rende il {100 * r['efficienza_con_coppia']:.0f} %)")
        print("| accesso dei membri | efficienza del canale | tempo mediano | completa |")
        print("|---|---|---|---|")
        for k in ("turni", "ascolto"):
            v = r[k]
            print(f"| {k} | {100 * v['efficienza']:.0f} % | {pi.fmt_time(v['tempo_mediano'])} | {100 * v['completamento']:.1f} % |")
        return
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
