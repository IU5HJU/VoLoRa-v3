#!/usr/bin/env python3
"""Limiti dei chip radio dai DATASHEET Semtech (non piu' da fonti secondarie), per controllare i gradini R0-R14 e i canali del progetto.
Fonti: docs/datasheet/SX1276-77-78-79_datasheet_rev4.pdf (SX1278) e docs/datasheet/SX1261-2_datasheet_rev1.2.pdf (SX1262).
Riferimenti di pagina nel testo di docs/confronto-datasheet.md. Provato sul PC (tests/sim/test_limiti_chip.py), NON con schede."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocollo_immagini as pi  # noqa: E402
import scala_modi as sm  # noqa: E402

# ------------------------------------------------------------------------------------------------ campo di sintonia (kHz)
# SX1278: Table 7 (Band 3 137-175, Band 2 410-525 MHz). RadioLib accetta 395-410 ma il datasheet NON lo garantisce.
TUNING_KHZ = {"SX1278": [(137000, 175000), (410000, 525000)], "SX1262": [(150000, 960000)]}

# ------------------------------------------------------------------------------------------------ LoRa
LORA_BW_KHZ = {"SX1278": (7.8, 10.4, 15.6, 20.8, 31.25, 41.7, 62.5, 125.0, 250.0, 500.0), "SX1262": (7.8, 10.4, 15.6, 20.8, 31.25, 41.7, 62.5, 125.0, 250.0, 500.0)}
LORA_SF = {"SX1278": (6, 12), "SX1262": (5, 12)}
# Sensibilita' tipica (dBm) con CR 4/5, PER 1%, dal datasheet. SX1278: tabella "Band 3" (137-175 MHz, Table 10); per i 433 MHz (Band 2) il datasheet
# non da' una colonna propria. SX1262: Table 3-8 (quattro punti per banda).
SENS_SX1278 = {
    (500.0, 6): -112, (500.0, 7): -118, (500.0, 8): -121, (500.0, 9): -124, (500.0, 10): -127, (500.0, 11): -129, (500.0, 12): -130,
    (250.0, 6): -118, (250.0, 7): -122, (250.0, 8): -125, (250.0, 9): -128, (250.0, 10): -131, (250.0, 11): -133, (250.0, 12): -134,
    (125.0, 6): -121, (125.0, 7): -125, (125.0, 8): -128, (125.0, 9): -131, (125.0, 10): -134, (125.0, 11): -136, (125.0, 12): -137,
    (62.5, 6): -123, (62.5, 7): -128, (62.5, 8): -131, (62.5, 9): -134, (62.5, 10): -135, (62.5, 11): -137, (62.5, 12): -140,
    (7.8, 11): -145, (7.8, 12): -148,
}
SENS_SX1262 = {(500.0, 7): -117, (500.0, 12): -129, (250.0, 7): -121, (250.0, 12): -134, (125.0, 7): -124, (125.0, 12): -137, (10.4, 7): -134, (10.4, 12): -148}
SENS = {"SX1278": SENS_SX1278, "SX1262": SENS_SX1262}
# Tolleranza sull'errore di frequenza fra trasmettitore e ricevitore senza perdita: +-25% della banda; per SF10/11/12 anche +-200/100/50 ppm (si applica il piu' stretto).
PPM_LIMIT_SF = {10: 200.0, 11: 100.0, 12: 50.0}
# L'SX1278 a 169 MHz (Band 3) non supporta le bande LoRa 250 e 500 kHz (nota sotto la Table 15).
LORA_NOT_IN_BAND3 = (250.0, 500.0)

# ------------------------------------------------------------------------------------------------ FSK
FSK = {
    "SX1278": dict(br_min=1.2, br_max=300.0, fdev_min=0.6, fdev_max=200.0, rxbw_dsb_max=500.0, index_min=None, index_max_at_br_max=0.5, fifo=64),
    "SX1262": dict(br_min=0.6, br_max=300.0, fdev_min=0.6, fdev_max=200.0, rxbw_dsb_max=467.0, index_min=0.5, index_max_at_br_max=None, fifo=None),
}
SX1262_BR_SCALING_REF_KHZ = 915000   # nota 5 della Table 3-7: il bit rate massimo "scala con la frequenza" (300 kb/s a 869/915 MHz, 50 kb/s a 150 MHz)


def in_tuning(chip, khz):
    return any(lo <= khz <= hi for lo, hi in TUNING_KHZ[chip])


def fsk_br_max_kbps(chip, khz):
    """Bit rate FSK massimo alla frequenza data. SX1262: scala con la frequenza (nota del datasheet): circa 142 kb/s a 433,7 MHz. SX1278: 300 kb/s."""
    top = FSK[chip]["br_max"]
    return min(top, top * khz / SX1262_BR_SCALING_REF_KHZ) if chip == "SX1262" else top


def ppm_budget(bw_khz, sf, khz):
    """Errore di frequenza TOTALE ammesso fra trasmettitore e ricevitore (ppm, somma dei due quarzi) senza perdita di sensibilita'."""
    tol_khz = 0.25 * bw_khz
    ppm = tol_khz / khz * 1e6
    return min(ppm, PPM_LIMIT_SF.get(sf, 1e9))


def rung_support(rid, chip, khz=433700, xtal_ppm=10.0):
    """(ok, note): il gradino rid e' realizzabile dal chip alla frequenza khz con quarzi di xtal_ppm ciascuno? Le note spiegano le condizioni o il motivo."""
    _, kind, (a, b), name = pi.RUNGS[rid]
    notes = []
    if not in_tuning(chip, khz):
        return False, ["frequenza fuori dal campo di sintonia"]
    if kind == "FSK":
        d = FSK[chip]
        br, fdev = a, b
        if not d["br_min"] <= br <= fsk_br_max_kbps(chip, khz):
            return False, [f"bit rate oltre il massimo del chip a questa frequenza ({fsk_br_max_kbps(chip, khz):.0f} kb/s)"]
        if not d["fdev_min"] <= fdev <= d["fdev_max"] or fdev + br / 2 > 250:
            return False, ["deviazione fuori dai limiti (FDA + BR/2 <= 250 kHz)"]
        need = br + 2 * fdev + 2 * (2 * xtal_ppm * khz / 1e6)    # banda del segnale piu' due volte l'errore di frequenza (come scrive il datasheet SX1262)
        if need > d["rxbw_dsb_max"]:
            return False, [f"servono {need:.0f} kHz di banda di ricezione, il chip arriva a {d['rxbw_dsb_max']:.0f} kHz"]
        if d["index_min"] and 2 * fdev / br < d["index_min"]:
            return False, ["indice di modulazione sotto 0,5"]
        if d["fifo"] and br >= 100:
            notes.append(f"pacchetti oltre {d['fifo']} byte: il FIFO va rifornito durante la trasmissione (possibile, ma non con la libreria di base)")
        if br > 0.8 * fsk_br_max_kbps(chip, khz):
            notes.append("vicino al massimo del chip a questa frequenza: da misurare")
        return True, notes
    bw, sf = a, b
    lo, hi = LORA_SF[chip]
    if bw not in LORA_BW_KHZ[chip] or not lo <= sf <= hi:
        return False, [f"{chip} non fa SF{sf}"]
    if chip == "SX1278" and sf == 6:
        notes.append("SF6 solo con intestazione implicita (lunghezza fissa) e registri speciali; NON compatibile con l'SF6 dell'SX1262")
    if chip == "SX1262" and sf in (5, 6):
        notes.append("SF5/SF6: preambolo di 12 simboli consigliato; SF6 NON compatibile con l'SX1278")
    if chip == "SX1262" and bw == 500.0:
        notes.append("prima di trasmettere: bit 2 del registro 0x0889 a 0 (BW 500 kHz), a 1 per le altre bande")
    budget = ppm_budget(bw, sf, khz)
    if 2 * xtal_ppm > budget:
        notes.append(f"errore di frequenza totale {2 * xtal_ppm:.0f} ppm > {budget:.1f} ppm ammessi: serve un quarzo migliore (TCXO)")
        return False, notes
    return True, notes


def pair_ok(rid, chip_a, chip_b):
    """Due chip possono parlarsi a questo gradino? Falso per R3 (LoRa 500/SF6) fra SX1278 e SX1262, perche' l'SF6 e' diverso."""
    _, kind, (a, b), _ = pi.RUNGS[rid]
    if kind == "LORA" and b == 6 and chip_a != chip_b:
        return False
    return True


def sens_datasheet(chip, bw, sf):
    return SENS[chip].get((bw, sf))


def compare_sensitivity(chip):
    """[(gradino, stima dello studio, valore del datasheet, differenza)] per i gradini LoRa con un valore nel datasheet. Differenza > 0: lo studio e' ottimista."""
    out = []
    for rid, kind, (a, b), _ in pi.RUNGS:
        if kind != "LORA":
            continue
        ds = sens_datasheet(chip, a, b)
        if ds is not None:
            est = sm.sens_lora(a, b)
            out.append((rid, est, ds, est - ds))
    return out


if __name__ == "__main__":
    for chip in ("SX1278", "SX1262"):
        print(chip)
        for rid in range(len(pi.RUNGS)):
            ok, notes = rung_support(rid, chip)
            print(f"  R{rid:<2} {pi.RUNGS[rid][3]:<18} {'si' if ok else 'NO'}  {'; '.join(notes)}")
