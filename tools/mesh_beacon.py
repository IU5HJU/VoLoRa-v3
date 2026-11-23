#!/usr/bin/env python3
"""Tempo in aria e carico del beacon del mesh V3 (docs/mesh-v3.md). Formule LoRa di Semtech; stima ALOHA senza coordinamento.

  python3 tools/mesh_beacon.py            # tabelle del documento
  python3 tools/mesh_beacon.py --stazioni 30 --intervallo 15 --gradino R12
"""
import argparse
import math

# gradino: (banda kHz, SF)
GRADINI = {"R10": (125.0, 12), "R11": (62.5, 12), "R12": (31.25, 12), "R13": (15.6, 12), "R14": (7.8, 12)}
BYTE_SOLO_NOMINATIVO = 7          # tipo (1) + nominativo compresso a 6 bit per carattere, 8 caratteri (6)
BYTE_NOMINATIVO_POSIZIONE = 14    # + posizione di 7 byte (stato 1, latitudine 3, longitudine 3)


def tempo_aria(sf, bw_khz, payload, preambolo=8, esplicita=True, crc=True, cr=1):
    """Secondi totali e secondi del solo preambolo."""
    ts = 2 ** sf / (bw_khz * 1000.0)
    de = 1 if ts > 0.016 else 0
    h = 0 if esplicita else 1
    n = max(math.ceil((8 * payload - 4 * sf + 28 + (16 if crc else 0) - 20 * h) / (4 * (sf - 2 * de))) * (cr + 4), 0) + 8
    pre = (preambolo + (6.25 if sf < 7 else 4.25)) * ts
    return pre + n * ts, pre


def aloha_puro(n, t_beacon, intervallo_s):
    """Probabilita' che un beacon arrivi senza collisione: e^(-2G), G = carico offerto (n stazioni, un beacon ogni intervallo)."""
    g = n * t_beacon / intervallo_s
    return math.exp(-2 * g)


def aloha_slot(n, t_beacon, intervallo_s):
    """Con slot sincronizzati dall'orologio: e^(-G)."""
    return math.exp(-n * t_beacon / intervallo_s)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stazioni", type=int)
    ap.add_argument("--intervallo", type=float, default=10.0, help="minuti fra un beacon e il successivo")
    ap.add_argument("--gradino", default="R14", choices=list(GRADINI))
    a = ap.parse_args()
    if a.stazioni:
        bw, sf = GRADINI[a.gradino]
        t = tempo_aria(sf, bw, BYTE_SOLO_NOMINATIVO)[0]
        print(f"{a.gradino}, {a.stazioni} stazioni, un beacon ogni {a.intervallo:g} min: beacon da {t:.1f} s, "
              f"successo senza coordinamento {100 * aloha_puro(a.stazioni, t, a.intervallo * 60):.0f} %, con slot {100 * aloha_slot(a.stazioni, t, a.intervallo * 60):.0f} %")
        return
    print("Tempo in aria del beacon (CR 4/5, preambolo 8, intestazione esplicita, CRC), secondi")
    print("| byte | contenuto | " + " | ".join(GRADINI) + " |")
    print("|---|---|" + "---|" * len(GRADINI))
    for pl, desc in ((BYTE_SOLO_NOMINATIVO, "solo nominativo (compresso)"), (BYTE_NOMINATIVO_POSIZIONE, "nominativo + posizione")):
        print(f"| {pl} | {desc} | " + " | ".join(f"{tempo_aria(sf, bw, pl)[0]:.1f}" for bw, sf in GRADINI.values()) + " |")
    print()
    print("Beacon da 7 byte: quanto pesa la parte fissa e cosa fa risparmiare l'intestazione implicita, senza CRC, preambolo di 6 simboli")
    print("| gradino | totale | di cui preambolo | a lunghezza fissa | risparmio |")
    print("|---|---|---|---|---|")
    for g, (bw, sf) in GRADINI.items():
        tot, pre = tempo_aria(sf, bw, BYTE_SOLO_NOMINATIVO)
        fis = tempo_aria(sf, bw, BYTE_SOLO_NOMINATIVO, preambolo=6, esplicita=False, crc=False)[0]
        print(f"| {g} | {tot:.1f} s | {pre:.1f} s ({100 * pre / tot:.0f} %) | {fis:.1f} s | {100 * (1 - fis / tot):.0f} % |")
    print()
    print("Beacon solo nominativo (7 byte), un beacon ogni 10 minuti: probabilita' di arrivare senza collisione")
    print("| stazioni | " + " | ".join(f"{g} (senza / con slot)" for g in ("R10", "R12", "R14")) + " |")
    print("|---|---|---|---|")
    for n in (10, 20, 50, 100):
        cells = []
        for g in ("R10", "R12", "R14"):
            bw, sf = GRADINI[g]
            t = tempo_aria(sf, bw, BYTE_SOLO_NOMINATIVO)[0]
            cells.append(f"{100 * aloha_puro(n, t, 600):.0f} % / {100 * aloha_slot(n, t, 600):.0f} %")
        print(f"| {n} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
