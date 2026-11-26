"""Simulatore dell'elezione fra due nodi che ricevono insieme la stessa stazione (voting / isofrequenza), per docs/voting-isofrequenza.md.

Situazione: due nodi sulla STESSA frequenza con coperture che si sovrappongono in una zona. Una stazione mobile, a riposo, comincia a trasmettere e la
sentono tutti e due. Chi deve ritrasmetterla verso la rete e verso gli altri ripetitori? Mai tutti e due insieme.

Politiche (come ogni nodo decide quando partire):
  nessuna   : tutti quelli che hanno decodificato partono subito
  casuale   : ritardo casuale e ascolto: chi sente partire un altro si ferma
  qualita   : ritardo proporzionale alla qualita' misurata (meglio il segnale, prima si parte) e ascolto
Canale con cui un nodo viene a sapere che l'altro e' partito (annuncio):
  rf        : sente il preambolo dell'altro (solo se i due nodi si sentono, dopo la finestra di rilevamento)
  rete      : annuncio via rete (Internet o collegamento dati fra i nodi), con una latenza
  nessuno   : non lo viene a sapere
Modello di studio, NON misure: collegamenti stimati e ombreggiamento casuale."""
import argparse
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocollo_immagini as pi  # noqa: E402
import scala_modi as scm  # noqa: E402
import sim_mesh as sm  # noqa: E402

RUNG = 6               # gradino della voce (ipotesi: dipende dal profilo VoLoRa v2 scelto)
VULN = 0.010           # s: finestra in cui due partenze non si sentono (circa due simboli)
W = 0.200              # s: ritardo massimo di partenza
SPAN_DB = 20.0         # dB che coprono il ritardo da 0 a W
MEAS_SIGMA = 1.0       # dB: errore di misura dell'SNR in un nodo
LAT_RETE = 0.050       # s: latenza dell'annuncio via rete


def fspl_db_f(d_km, f_mhz):
    return 32.45 + 20 * math.log10(f_mhz) + 20 * math.log10(max(d_km, 0.05))


def _prx(rng, d_km, extra, shadow=None, sigma=8.0, f_mhz=None):
    loss = sm.fspl_db(d_km) if f_mhz is None else fspl_db_f(d_km, f_mhz)
    return 10.0 - loss - extra + (rng.gauss(0.0, sigma) if shadow is None else shadow)


def ritardo(politica, snr, rng, rid=RUNG):
    if politica == "nessuna":
        return 0.0
    if politica == "casuale":
        return rng.uniform(0.0, W)
    m = snr + rng.gauss(0.0, MEAS_SIGMA) - (pi.sensitivity_dbm(rid))     # margine misurato
    q = min(1.0, max(0.0, m / SPAN_DB))
    return W * (1.0 - q)


def elezione(delays, sentono, canale):
    """delays: ritardi di partenza dei nodi che hanno decodificato; sentono[i][j]: i sente j in RF. Ritorna l'elenco di chi trasmette davvero."""
    n = len(delays)
    order = sorted(range(n), key=lambda i: delays[i])
    partiti = []
    for i in order:
        ferma = False
        for j in partiti:
            gap = delays[i] - delays[j]
            if canale == "rf" and sentono[i][j] and gap >= VULN:
                ferma = True
            elif canale == "rete" and gap >= LAT_RETE:
                ferma = True
        if not ferma:
            partiti.append(i)
    return partiti


def run_elezione(politica, canale, dist_km=20.0, scenari=3000, seed=1, extra=25.0, nodi_si_sentono=None):
    """Due nodi a dist_km; la mobile in un punto casuale della zona fra i due. Conta solo quando entrambi la decodificano.
    nodi_si_sentono: None = calcolato dal collegamento fra i nodi; True/False = forzato (per separare l'effetto)."""
    rng = random.Random(seed)
    sens = pi.sensitivity_dbm(RUNG)
    n = doppi = migliore = 0
    ritardi = []
    for _ in range(scenari):
        x, y = rng.uniform(0.0, dist_km), rng.uniform(-0.3 * dist_km, 0.3 * dist_km)
        d1, d2 = math.hypot(x, y), math.hypot(dist_km - x, y)
        p1, p2 = _prx(rng, d1, extra), _prx(rng, d2, extra)
        if p1 < sens or p2 < sens:
            continue
        n += 1
        hear = _prx(rng, dist_km, extra) >= sens if nodi_si_sentono is None else nodi_si_sentono
        sentono = [[True, hear], [hear, True]]
        dl = [ritardo(politica, p1, rng), ritardo(politica, p2, rng)]
        tx = elezione(dl, sentono, canale)
        if len(tx) > 1:
            doppi += 1
        else:
            migliore += 1 if (p1 >= p2) == (tx[0] == 0) else 0
            ritardi.append(dl[tx[0]])
    ok = n - doppi
    return {"casi": n, "doppio_accesso": doppi / n if n else float("nan"), "migliore_se_unico": migliore / ok if ok else float("nan"),
            "ritardo_medio_s": statistics.mean(ritardi) if ritardi else float("nan")}


GUARD_VOTO = 0.010     # s fra uno slot di voto e il successivo
VOTE_BYTES = 12        # frame_mesh.enc_vote


# Modi del canale di servizio (433,850 MHz, 125 kHz di banda: docs/band-plan.md): FSK R2 e LoRa a 125 kHz. (nome, sensibilita' dBm, tempo in aria del VOTO s)
SERVICE_MODES = [("R2 FSK 50k", pi.sensitivity_dbm(2), pi.frame_airtime_s(2, VOTE_BYTES)),
                 ("125/SF7", scm.sens_lora(125, 7), scm.lora_toa(7, 125, 1, VOTE_BYTES, 8)),
                 ("125/SF8", scm.sens_lora(125, 8), scm.lora_toa(8, 125, 1, VOTE_BYTES, 8)),
                 ("125/SF9 (R8)", scm.sens_lora(125, 9), scm.lora_toa(9, 125, 1, VOTE_BYTES, 8)),
                 ("125/SF10 (R9)", scm.sens_lora(125, 10), scm.lora_toa(10, 125, 1, VOTE_BYTES, 8)),
                 ("125/SF12 (R10)", scm.sens_lora(125, 12), scm.lora_toa(12, 125, 1, VOTE_BYTES, 8))]


def _fsk_mode(br, dev):
    """(nome, sensibilita' dBm con la stessa formula delle altre stime, tempo in aria del VOTO) di un modo FSK stretto."""
    bw = br + 2 * dev
    return (f"FSK {br:g}k dev {dev:g} ({bw:g} kHz)", -174 + 10 * math.log10(bw * 1000) + scm.NF + 12, (pi.FSK_PHY_BYTES + VOTE_BYTES) * 8 / (br * 1000))


# Servizio a 144,850 MHz (2 m, deciso il 26/11/2026): modi stretti (banda occupata sotto 15 kHz, adatti ai segmenti digitali dei 2 m) e perdita a 144,85 MHz
SERVICE_MODES_2M = [_fsk_mode(4.8, 2.4), _fsk_mode(2.4, 1.2)]
SERVICE_F_MHZ = {"2m": 144.85, "70cm": None}
SERVICE_MODES_BY_BAND = {"2m": SERVICE_MODES_2M, "70cm": SERVICE_MODES}


def rung_collegamento(dist_km, extra_nodi, rng, sigma=4.0, band="2m"):
    """Modo piu' veloce del canale di servizio con 6 dB di margine fra i due nodi (antenne in alto: perdita extra piccola): (nome, tempo in aria); None se non si sentono."""
    prx = _prx(rng, dist_km, extra_nodi, sigma=sigma, f_mhz=SERVICE_F_MHZ[band])
    for name, sens_dbm, toa in SERVICE_MODES_BY_BAND[band]:
        if prx - sens_dbm >= sm.MARGIN_DB:
            return name, toa
    return None


def run_voto_radio(dist_nodi_km, extra_mobile=25.0, extra_nodi=10.0, p_loss=0.03, repeat=1, scenari=3000, seed=1, band="2m"):
    """Voto sul canale di servizio fra i nodi, via radio (Internet non e' affidabile). Dopo la fine del primo pacchetto della mobile ogni nodo che l'ha
    decodificata manda un VOTO nel proprio slot (ordine per identificativo); vince il margine migliore, a parita' l'identificativo piu' basso.
    Un VOTO perso (probabilita' p_loss per tentativo, `repeat` tentativi) fa partire anche il perdente: doppio accesso. Se i nodi non si sentono a nessun gradino
    il voto non e' possibile (doppio accesso). Il perdente deve comunque aver sentito il VOTO del vincitore: conta solo la perdita di quel frame."""
    rng = random.Random(seed)
    sens = pi.sensitivity_dbm(RUNG)
    n = doppi = migliore = senza_link = 0
    durate = []
    rungs = []
    for _ in range(scenari):
        x, y = rng.uniform(0.0, dist_nodi_km), rng.uniform(-0.3 * dist_nodi_km, 0.3 * dist_nodi_km)
        d1, d2 = math.hypot(x, y), math.hypot(dist_nodi_km - x, y)
        p1, p2 = _prx(rng, d1, extra_mobile), _prx(rng, d2, extra_mobile)
        if p1 < sens or p2 < sens:
            continue
        n += 1
        rl = rung_collegamento(dist_nodi_km, extra_nodi, rng, band=band)
        if rl is None:
            senza_link += 1
            doppi += 1
            continue
        rungs.append(rl[0])
        slot = rl[1] + GUARD_VOTO
        durate.append(2 * slot * repeat)
        m = [p1 - sens + rng.gauss(0, MEAS_SIGMA), p2 - sens + rng.gauss(0, MEAS_SIGMA)]
        win = 0 if m[0] >= m[1] else 1
        if all(rng.random() < p_loss for _ in range(repeat)):       # il perdente non ha sentito il VOTO del vincitore
            doppi += 1
        else:
            migliore += 1 if (p1 >= p2) == (win == 0) else 0
    ok = n - doppi
    return {"casi": n, "doppio_accesso": doppi / n if n else float("nan"), "senza_collegamento": senza_link / n if n else float("nan"),
            "migliore_se_unico": migliore / ok if ok else float("nan"), "durata_voto_s": statistics.median(durate) if durate else float("nan"),
            "gradino_mediano": max(set(rungs), key=rungs.count) if rungs else None}


def run_percorso(isteresi_db, passi=60, dist_km=20.0, seed=1, extra=25.0, fading_db=3.0, prove=300):
    """Una stazione si muove da un nodo all'altro e trasmette ogni `passi`-esimo punto. Conta i cambi di nodo (ognuno e' un possibile doppio accesso o un taglio).
    isteresi_db = 0: sempre il migliore del momento; altrimenti si resta col nodo di prima finche' l'altro non lo supera di tanti dB."""
    rng = random.Random(seed)
    cambi = []
    for _ in range(prove):
        sh1, sh2 = rng.gauss(0, 4.0), rng.gauss(0, 4.0)        # ombreggiamento lento, fisso per la prova
        cur = None
        n = 0
        for k in range(passi):
            x = dist_km * (0.1 + 0.8 * k / (passi - 1))
            p1 = _prx(rng, max(x, 0.05), extra, sh1 + rng.gauss(0, fading_db))
            p2 = _prx(rng, max(dist_km - x, 0.05), extra, sh2 + rng.gauss(0, fading_db))
            best = 0 if p1 >= p2 else 1
            if cur is None:
                cur = best
            elif best != cur and abs(p1 - p2) >= isteresi_db:
                cur = best
                n += 1
        cambi.append(n)
    return statistics.mean(cambi)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--distanza", type=float, default=20.0)
    ap.add_argument("--scenari", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    print(f"Due nodi a {a.distanza:g} km sulla stessa frequenza, gradino della voce R{RUNG}; solo i casi in cui la mobile e' decodificata da entrambi.")
    print("| politica | annuncio | nodi si sentono | doppio accesso | nodo migliore (se unico) | ritardo medio |")
    print("|---|---|---|---|---|---|")
    for pol, can, hear in (("nessuna", "nessuno", None), ("casuale", "rf", True), ("casuale", "rf", False), ("qualita", "rf", True), ("qualita", "rf", False),
                           ("qualita", "rete", False)):
        r = run_elezione(pol, can, a.distanza, a.scenari, a.seed, nodi_si_sentono=hear)
        print(f"| {pol} | {can} | {'si' if hear else ('no' if hear is False else '-')} | {100 * r['doppio_accesso']:.1f} % | {100 * r['migliore_se_unico']:.0f} % | {1000 * r['ritardo_medio_s']:.0f} ms |")
    global W
    print("\nCompromesso: ritardo massimo di partenza W contro doppio accesso (qualita', nodi che non si sentono, annuncio via rete 50 ms; qualita', nodi che si sentono in RF):")
    print("| W | doppio accesso via rete | doppio accesso in RF | ritardo medio via rete |")
    print("|---|---|---|---|")
    w0 = W
    for W in (0.1, 0.2, 0.4, 0.8):
        r1 = run_elezione("qualita", "rete", a.distanza, a.scenari, a.seed, nodi_si_sentono=False)
        r2 = run_elezione("qualita", "rf", a.distanza, a.scenari, a.seed, nodi_si_sentono=True)
        print(f"| {1000 * W:.0f} ms | {100 * r1['doppio_accesso']:.1f} % | {100 * r2['doppio_accesso']:.1f} % | {1000 * r1['ritardo_medio_s']:.0f} ms |")
    W = w0
    print("\nVoto via radio sul canale di servizio a 144,850 MHz (2 m), FSK stretto; antenne in alto: perdita extra 10 dB; VOTO da 12 byte; un VOTO su 33 si perde; un solo tentativo:")
    print("| distanza fra i nodi | nodi si sentono | gradino del voto | durata del voto (2 slot) | entra in 200 ms | doppio accesso | nodo migliore |")
    print("|---|---|---|---|---|---|---|")
    for dk in (5.0, 10.0, 20.0, 30.0, 50.0, 70.0):
        r = run_voto_radio(dk, scenari=a.scenari, seed=a.seed)
        durata = r["durata_voto_s"]
        gr = "-" if r["gradino_mediano"] is None else r["gradino_mediano"]
        print(f"| {dk:g} km | {100 * (1 - r['senza_collegamento']):.0f} % | {gr} | {1000 * durata:.0f} ms | {'si' if durata <= W else 'NO'} | {100 * r['doppio_accesso']:.1f} % | {100 * r['migliore_se_unico']:.0f} % |")
    print("\nCambi di nodo lungo un percorso fra i due (media per prova):")
    for h in (0.0, 3.0, 6.0):
        print(f"  isteresi {h:g} dB: {run_percorso(h, dist_km=a.distanza, seed=a.seed):.1f}")


if __name__ == "__main__":
    main()
