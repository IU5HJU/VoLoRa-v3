#!/usr/bin/env python3
"""Tabelle e stime del protocollo immagini V3 (bozza, docs/protocollo-immagini.md).

Contiene la scala dei gradini (rung), la dimensione dei frame per gradino, e la stima del tempo per trasferire un oggetto di N byte.
Le cifre di sensibilita' sono le stime dello studio (docs/scala-modi.md), non misure. Usato anche dall'applicazione (app/)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scala_modi as sm  # noqa: E402

DATA_HEADER = 6          # versione/tipo 1, sessione 2, flag 1, indice del pezzo 2
STATUS_BYTES = 18        # intestazione 4 + base 2 + bitmap 8 + rssi 1 + snr 1 + perdite 1 + riservato 1
FSK_PHY_BYTES = 9        # preambolo 4, sincronismo 2, lunghezza 1, CRC 2
SX1278_FSK_FRAME_MAX = 64   # FIFO dell'SX1278 (da confermare con la misura M5)
FRAME_MAX = 255
CHUNK_AIRTIME_TARGET = 3.0  # secondi: un pezzo non dovrebbe durare di piu' (perdite e tempi di ritorno)
MIN_CHUNK = 32

# id, tipo, parametri, nome. R0-R2 FSK (kbit/s, deviazione kHz); R3-R14 LoRa (BW kHz, SF), CR 4/5.
RUNGS = [
    (0, "FSK", (150.0, 50.0), "FSK 150k"),
    (1, "FSK", (100.0, 50.0), "FSK 100k"),
    (2, "FSK", (50.0, 25.0), "FSK 50k"),
    (3, "LORA", (500.0, 6), "LoRa 500/SF6"),
    (4, "LORA", (500.0, 7), "LoRa 500/SF7"),
    (5, "LORA", (250.0, 7), "LoRa 250/SF7"),
    (6, "LORA", (250.0, 8), "LoRa 250/SF8"),
    (7, "LORA", (250.0, 9), "LoRa 250/SF9"),
    (8, "LORA", (125.0, 9), "LoRa 125/SF9"),
    (9, "LORA", (125.0, 10), "LoRa 125/SF10"),
    (10, "LORA", (125.0, 12), "LoRa 125/SF12"),
    (11, "LORA", (62.5, 12), "LoRa 62,5/SF12"),
    (12, "LORA", (31.25, 12), "LoRa 31,25/SF12"),
    (13, "LORA", (15.6, 12), "LoRa 15,6/SF12"),
    (14, "LORA", (7.8, 12), "LoRa 7,8/SF12"),
]
RENDEZVOUS = 10   # gradino di incontro: LoRa 125/SF12, come il profilo Messaggio della v2
TCXO_BELOW_BW = 125.0  # sotto questa banda LoRa serve verificare il quarzo (misura M6)


def sensitivity_dbm(rid):
    """Sensibilita' stimata dello studio (docs/scala-modi.md)."""
    _, kind, (a, b), _ = RUNGS[rid]
    if kind == "LORA":
        return sm.sens_lora(a, b)
    return -174 + 10 * math.log10((a + 2 * b) * 1000) + sm.NF + 12


def frame_airtime_s(rid, frame_bytes):
    """Tempo in aria di un frame di frame_bytes byte (comprese le parti della radio)."""
    _, kind, (a, b), _ = RUNGS[rid]
    if kind == "LORA":
        return sm.lora_toa(b, a, 1, frame_bytes, 8)
    return (FSK_PHY_BYTES + frame_bytes) * 8 / (a * 1000.0)


def max_frame(rid, chip="SX1278"):
    kind = RUNGS[rid][1]
    if kind == "FSK" and chip == "SX1278":
        return SX1278_FSK_FRAME_MAX
    return FRAME_MAX


def chunk_size(rid, chip="SX1278"):
    """Byte di dati per frame: il piu' grande (fino al massimo del chip) con tempo in aria entro il bersaglio, ma mai meno di MIN_CHUNK."""
    top = max_frame(rid, chip) - DATA_HEADER
    for c in range(top, MIN_CHUNK - 1, -1):
        if frame_airtime_s(rid, c + DATA_HEADER) <= CHUNK_AIRTIME_TARGET:
            return c
    return min(MIN_CHUNK, top)


def net_rate_bps(rid, chip="SX1278"):
    c = chunk_size(rid, chip)
    return c * 8 / frame_airtime_s(rid, c + DATA_HEADER)


def estimate_seconds(nbytes, rid, chip="SX1278", loss=0.05, window=16, guard_s=0.15):
    """Tempo stimato per trasferire nbytes di dati: frame, ritrasmissioni (perdita media `loss`), una STATUS per finestra e i tempi di commutazione."""
    c = chunk_size(rid, chip)
    frames = math.ceil(nbytes / c)
    tx = frames * frame_airtime_s(rid, c + DATA_HEADER) / (1.0 - loss)
    windows = math.ceil(frames / window)
    status = windows * (frame_airtime_s(rid, STATUS_BYTES) + 2 * guard_s)
    return tx + status


def fmt_time(sec):
    if sec < 90:
        return "%.0f s" % sec
    if sec < 5400:
        return "%.0f min" % (sec / 60.0)
    return "%.1f h" % (sec / 3600.0)


def table(chip="SX1278", sizes=(2000, 5000, 20000, 50000)):
    rows = []
    for rid, kind, _, name in RUNGS:
        c = chunk_size(rid, chip)
        rows.append((rid, name, c, frame_airtime_s(rid, c + DATA_HEADER), net_rate_bps(rid, chip), sensitivity_dbm(rid),
                     [estimate_seconds(n, rid, chip) for n in sizes]))
    return rows


def markdown_table(chip="SX1278", sizes=(2000, 5000, 20000, 50000)):
    head = "| R | Gradino | pezzo | frame | velocità netta | sens. stimata | " + " | ".join("%d kB" % (n // 1000) for n in sizes) + " |"
    sep = "|---|---|---|---|---|---|" + "---|" * len(sizes)
    out = [head, sep]
    for rid, name, c, t, bps, sens, times in table(chip, sizes):
        air = "%.0f ms" % (t * 1000) if t < 0.1 else "%.2f s" % t
        out.append("| R%d | %s | %d B | %s | %.2f kbit/s | %.0f dBm | %s |" % (rid, name, c, air, bps / 1000.0, sens, " | ".join(fmt_time(x) for x in times)))
    return "\n".join(out)


if __name__ == "__main__":
    print(markdown_table(sys.argv[1] if len(sys.argv) > 1 else "SX1278"))
