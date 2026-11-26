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
    CH_SERVICE: (433850, 125.0, "servizio fra i nodi (VOTO) e trasferimenti stretti con ascolto prima di parlare"),
    CH_NARROW: (433955, 62.5, "trasferimenti con i gradini stretti (R11-R14)"),
}
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


def table_markdown():
    rows = ["| Canale | Frequenza (MHz) | Larghezza max | Gradini ammessi | Uso |", "|---|---|---|---|---|"]
    for i in sorted(PROFILE0):
        f, bw, uso = PROFILE0[i]
        rows.append(f"| {i} | {f / 1000:.3f} | {bw:g} kHz | {', '.join('R' + str(r) for r in allowed_rungs(i))} | {uso} |")
    rows.append(f"| {RESERVED_FROM}-15 | — | — | — | riservati (tabella estesa) |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(table_markdown())
