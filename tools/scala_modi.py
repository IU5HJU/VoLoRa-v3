#!/usr/bin/env python3
"""Tabelle della scala dei modi (docs/scala-modi.md): LoRa calcolata con le formule Semtech, FSK orientativa.
SNR di demodulazione LoRa (dB) per SF, valori da datasheet Semtech a memoria: DA VERIFICARE (vedi docs/radio-limiti.md).
Cifra di rumore del ricevitore ipotizzata: 6 dB."""
import math
SNR = {5: -2.5, 6: -5, 7: -7.5, 8: -10, 9: -12.5, 10: -15, 11: -17.5, 12: -20}
NF = 6.0

def lora_toa(sf, bw_khz, cr=1, payload=255, preamble=8):
    ts = 2 ** sf / (bw_khz * 1000)
    de = 1 if ts > 0.016 else 0
    n = max(math.ceil((8 * payload - 4 * sf + 28 + 16) / (4 * (sf - 2 * de))) * (cr + 4), 0) + 8
    return (preamble + 4.25) * ts + n * ts

def fmt(sec):
    return f"{sec:.0f} s" if sec < 600 else f"{sec/60:.0f} min" if sec < 7200 else f"{sec/3600:.1f} h"

LORA = [(500, 5), (500, 6), (500, 7), (250, 7), (250, 8), (250, 9), (125, 9), (125, 10), (125, 12),
        (62.5, 12), (31.25, 12), (15.6, 12), (7.8, 12)]
FSK = [(300, 100), (150, 50), (100, 50), (50, 25), (19.2, 10), (4.8, 5)]  # (kbit/s, deviazione kHz)

def sens_lora(bw, sf):
    return -174 + 10 * math.log10(bw * 1000) + NF + SNR[sf]

def main(size=20000):
    ref = sens_lora(250, 7)
    print("LoRa (CR 4/5, pacchetti da 255 byte, preambolo 8, CRC, intestazione esplicita)")
    for i, (bw, sf) in enumerate(LORA, 1):
        br = sf * bw * 1000 / 2 ** sf * 0.8
        t = lora_toa(sf, bw)
        eff = 255 * 8 / t
        print(f"L{i} BW {bw:g} SF {sf}: {br/1000:.2f} kbit/s, {t*1000:.0f} ms, {sens_lora(bw, sf):.0f} dBm, "
              f"{sens_lora(bw, sf)-ref:+.1f} dB, {size} byte in {fmt(size*8/eff)}")
    print("FSK (orientativo: RxBw = bit rate + 2 x deviazione, SNR richiesto 12 dB)")
    for i, (br, dev) in enumerate(FSK, 1):
        bw = br + 2 * dev
        sens = -174 + 10 * math.log10(bw * 1000) + NF + 12
        print(f"F{i} {br:g} kbit/s dev {dev} kHz: RxBw {bw:g} kHz, {sens:.0f} dBm, {size} byte (solo dati) in {fmt(size*8/(br*1000))}")

if __name__ == "__main__":
    main()
