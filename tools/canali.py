"""Tabella dei canali del profilo 0 (banda 430-440 MHz) e del profilo 2 (modulo UART a 2,4 GHz). Decisa il 26/11/2026 sul band plan ARI
(docs/band-plan.md). Il nostro riferimento resta lo studio: il piano non e' un vincolo, ma qui si cerca dove si disturba meno.
Provata sul PC in tests/sim/test_canali.py, NON con schede."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocollo_immagini as pi  # noqa: E402

SEGMENT_KHZ = (433600, 434000)        # segmento "tutti i modi", 20 kHz, canali digitali 433,625-433,775 (band plan ARI)
CH_MEETING, CH_SERVICE, CH_NARROW = 0, 1, 2

# indice -> (frequenza centrale kHz, larghezza massima occupata kHz, uso)
PROFILE0 = {
    CH_MEETING: (433700, 125.0, "incontro: beacon, polling, HELLO e trasferimenti stretti"),
    CH_SERVICE: (433850, 125.0, "canale di servizio del voto (variante 70 cm) o trasferimenti stretti con ascolto prima di parlare"),
    CH_NARROW: (433955, 62.5, "trasferimenti con i gradini stretti (R11-R14)"),
}
SERVICE_2M_KHZ = 144900                # canale di servizio del VOTO, fisso, in banda 2 m (deciso il 26/11/2026; 144,850 era un canale dei gateway voce digitale: spostato a 144,900): la stessa antenna bibanda serve le due radio con un duplexer
# Canale di servizio del voto: DUE possibilita' (26/11/2026). 2 m: una sola antenna bibanda col duplexer, ma solo con un SX1278 (137-175 MHz).
# 70 cm: va con qualunque chip (anche SX1262), ma servono due antenne separate perche' la radio del voto e quella principale sono nella stessa banda.
SERVICE_CHANNELS = {"2m": (SERVICE_2M_KHZ, "FSK stretto (9,6 kHz)"), "70cm": (433850, "FSK R2 o LoRa 125 kHz")}
CAP_SERVICE_2M, CAP_SERVICE_70CM = 1, 2        # maschera di capacita' del nodo (frame NODE_INFO)
RESERVED_FROM = 3                      # 3-15: riservati (tabella estesa, frequenze da definire)


def occupied_khz(rid):
    """Larghezza occupata di un gradino (LoRa: banda; FSK: bit rate + 2 x deviazione, come nella stima del rumore)."""
    _, kind, (a, b), _ = pi.RUNGS[rid]
    return a if kind == "LORA" else a + 2 * b


def frequency_khz(idx):
    if idx not in PROFILE0:
        raise ValueError("canale non definito (riservato)")
    return PROFILE0[idx][0]


def span_khz(idx):
    f, bw, _ = PROFILE0[idx]
    return f - bw / 2, f + bw / 2


def allowed_rungs(idx):
    """Gradini che stanno nella larghezza massima del canale."""
    return [rid for rid in range(len(pi.RUNGS)) if occupied_khz(rid) <= PROFILE0[idx][1]]


def best_channel_for(rid, busy=()):
    """Primo canale libero (non in `busy`) che ospita il gradino rid, in ordine di indice; None se nessuno (gradino largo: serve altra banda)."""
    for idx in sorted(PROFILE0):
        if idx not in busy and rid in allowed_rungs(idx):
            return idx
    return None


def guard_khz(a, b):
    sa, sb = span_khz(a), span_khz(b)
    return max(sb[0] - sa[1], sa[0] - sb[1])


# ---------------------------------------------------------------------------------------------------- frequenze configurabili (nota dell'autore, 26/11/2026)
# Nel firmware OGNI frequenza dei canali di T3 e T-Beam e' liberamente configurabile; la tabella PROFILE0 e' solo il valore di partenza.
# Le frequenze a 2,4 GHz del modulo sono configurabili a piacere dentro la banda assegnata ai radioamatori (qui 2400-2450 MHz, band plan ARI),
# sulla griglia del modulo (2400 + CHAN x passo).
CHIP_RANGES_KHZ = {"SX1278": [(137000, 175000), (410000, 525000)], "SX1262": [(150000, 960000)]}     # datasheet Semtech (docs/confronto-datasheet.md); 395-410 MHz funziona in RadioLib ma non e' garantito
HAM_2G4_KHZ = (2400000, 2450000)


def harmonic_khz(khz, n):
    """Frequenza dell'n-esima armonica: la terza del canale di servizio (3 x 144,900 = 434,700 MHz) cade in 70 cm, vicino ai nostri canali."""
    return khz * n


def valid_frequency(chip, khz):
    """True se la frequenza e' nel campo di sintonia del chip (T3: SX1278; T-Beam: SX1278 o SX1262)."""
    return any(lo <= khz <= hi for lo, hi in CHIP_RANGES_KHZ[chip])


def service_options(chip):
    """Canali di servizio utilizzabili con un chip: ['2m', '70cm'] con l'SX1278, ['70cm'] con l'SX1262 (che parte da 150 MHz)."""
    return [k for k, (khz, _) in SERVICE_CHANNELS.items() if valid_frequency(chip, khz)]


def caps_for_chip(chip):
    m = 0
    for k in service_options(chip):
        m |= CAP_SERVICE_2M if k == "2m" else CAP_SERVICE_70CM
    return m


def common_service(caps_a, caps_b, prefer="2m"):
    """Canale di servizio che due nodi possono usare insieme: il preferito se ce l'hanno entrambi, altrimenti l'altro, altrimenti None (non possono votare)."""
    both = caps_a & caps_b
    order = ("2m", "70cm") if prefer == "2m" else ("70cm", "2m")
    for k in order:
        if both & (CAP_SERVICE_2M if k == "2m" else CAP_SERVICE_70CM):
            return k
    return None


def make_plan(config, chip="SX1278"):
    """Tabella dei canali da una configurazione {indice: (kHz, larghezza kHz, uso)} (per esempio letta da un file): si valida ma NON si limita alla banda 430-440.
    Ritorna un dizionario indice -> (kHz, larghezza, uso). ValueError se una frequenza e' fuori dal campo del chip o due canali si sovrappongono."""
    plan = {}
    for idx, (f, bw, uso) in config.items():
        if not 0 <= idx <= 255 or not valid_frequency(chip, f) or bw <= 0:
            raise ValueError(f"canale {idx}: frequenza {f} kHz o larghezza non valida per {chip}")
        plan[idx] = (f, float(bw), uso)
    items = sorted(plan.items(), key=lambda kv: kv[1][0])
    for (ia, (fa, ba, _)), (ib, (fb, bb, _)) in zip(items, items[1:]):
        if fa + ba / 2 > fb - bb / 2:
            raise ValueError(f"i canali {ia} e {ib} si sovrappongono")
    return plan


def chan_for_frequency_2g4(khz, air_code, baud=9600):
    """CHAN del modulo Ebyte per una frequenza a 2,4 GHz: la frequenza deve stare sulla griglia 2400 + CHAN x passo (1, 2, 3 o 5 MHz secondo la velocita' d'aria)
    e dentro la banda radioamatoriale 2400-2450 MHz. ValueError altrimenti."""
    import ebyte_e28 as eb
    if not HAM_2G4_KHZ[0] <= khz <= HAM_2G4_KHZ[1]:
        raise ValueError("fuori dalla banda radioamatoriale 2400-2450 MHz")
    step = eb.channel_step_mhz(air_code, baud) * 1000
    if (khz - 2400000) % step:
        raise ValueError(f"la griglia del modulo a questa velocita' e' di {step // 1000} MHz: {khz / 1000:g} MHz non e' un canale")
    return (khz - 2400000) // step


def table_markdown():
    rows = ["| Canale | Frequenza (MHz) | Larghezza max | Gradini ammessi | Uso |", "|---|---|---|---|---|"]
    for i in sorted(PROFILE0):
        f, bw, uso = PROFILE0[i]
        rows.append(f"| {i} | {f / 1000:.3f} | {bw:g} kHz | {', '.join('R' + str(r) for r in allowed_rungs(i))} | {uso} |")
    rows.append(f"| {RESERVED_FROM}-15 | — | — | — | riservati (tabella estesa) |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(table_markdown())
