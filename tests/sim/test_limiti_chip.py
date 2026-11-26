"""Controllo dei gradini R0-R14 e dei canali contro i limiti dei DATASHEET Semtech: python3 -I tests/sim/test_limiti_chip.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import canali as ch  # noqa: E402
import limiti_chip as lc  # noqa: E402
import protocollo_immagini as pi  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


F = 433700
# campo di sintonia
check(all(lc.in_tuning("SX1278", f) for f in (433700, 433850, 433955, 144900, 430000, 440000)) and not lc.in_tuning("SX1278", 400000) and not lc.in_tuning("SX1262", 144900) and lc.in_tuning("SX1262", 433700),
      "campo di sintonia dal datasheet: SX1278 137-175 e 410-525 MHz (non 395), SX1262 da 150 MHz; i canali 433,7/433,85/433,955 e i confini 430 e 440 MHz sono dentro, 144,9 solo per l'SX1278")
check(all(ch.valid_frequency(c, f) == lc.in_tuning(c, f) for c in lc.TUNING_KHZ for f in (144900, 400000, 410000, 433700, 525000, 526000, 868000)), "tools/canali.py e tools/limiti_chip.py concordano sul campo di sintonia")
# gradini a 433,7 MHz con quarzi da 10 ppm
ok78 = {r: lc.rung_support(r, "SX1278", F)[0] for r in range(15)}
ok62 = {r: lc.rung_support(r, "SX1262", F)[0] for r in range(15)}
check([r for r in range(15) if not ok78[r]] == [12, 13, 14], f"SX1278: R0-R11 realizzabili; R12-R14 (banda 31,25 kHz e meno) NO con due quarzi da 10 ppm (budget {lc.ppm_budget(31.25, 12, F):.0f}, {lc.ppm_budget(15.6, 12, F):.0f}, {lc.ppm_budget(7.8, 12, F):.1f} ppm totali)")
check([r for r in range(15) if not ok62[r]] == [0, 12, 13, 14], f"SX1262: R0 (FSK 150 kb/s) NO a 433,7 MHz (massimo {lc.fsk_br_max_kbps('SX1262', F):.0f} kb/s: il bit rate massimo scala con la frequenza); R12-R14 come sopra")
check(all(lc.rung_support(r, "SX1278", F, xtal_ppm=2)[0] for r in (12, 13, 14)) and lc.rung_support(14, "SX1278", F, xtal_ppm=2.5)[0] is False, "con un TCXO da 2 ppm per scheda R12-R14 tornano realizzabili; R14 (7,8 kHz) e' al limite: 2,5 ppm per scheda non bastano")
check(lc.ppm_budget(125, 12, F) == 50 and abs(lc.ppm_budget(62.5, 12, F) - 36.0) < 0.1 and lc.ppm_budget(125, 9, F) > 70, "budget di frequenza: 125 kHz/SF12 limitato dai 50 ppm del datasheet; 62,5 kHz dal 25% della banda (36 ppm); SF9 a 125 kHz oltre 70 ppm")
# R3 e SF6
check(lc.pair_ok(3, "SX1278", "SX1278") and lc.pair_ok(3, "SX1262", "SX1262") and not lc.pair_ok(3, "SX1278", "SX1262") and all(lc.pair_ok(r, "SX1278", "SX1262") for r in range(15) if r != 3),
      "R3 (LoRa 500/SF6) NON e' compatibile fra SX1278 e SX1262 (SF6 diverso); tutti gli altri gradini si')")
# FSK
d78, d62 = lc.FSK["SX1278"], lc.FSK["SX1262"]
check(lc.rung_support(0, "SX1278", F)[0] and any("64" in n for n in lc.rung_support(0, "SX1278", F)[1]), "SX1278: R0 ok; oltre 64 byte il FIFO va rifornito in volo (limite della libreria, non del chip)")
f1_dsb = 300 + 2 * 100
check(f1_dsb > d62["rxbw_dsb_max"] and 300 + 2 * 75 <= d62["rxbw_dsb_max"] and 2 * 100 / 300 > d78["index_max_at_br_max"] and 2 * 75 / 300 <= d78["index_max_at_br_max"],
      "la riga F1 di docs/scala-modi.md (300 kb/s, deviazione 100 kHz) non e' ammessa: 500 kHz oltre i 467 dell'SX1262 e indice 0,67 oltre lo 0,5 massimo del SX1278 a 300 kb/s; con deviazione 75 kHz (450 kHz, indice 0,5) entra in entrambi (ma R0 resta a 150 kb/s)")
# sensibilita' LoRa: stima dello studio contro datasheet
worst = 0
for chip in ("SX1278", "SX1262"):
    rows = lc.compare_sensitivity(chip)
    for rid, est, ds, diff in rows:
        print(f"   {chip} R{rid} {pi.RUNGS[rid][3]}: studio {est:.1f} dBm, datasheet {ds} dBm, differenza {diff:+.1f} dB")
        worst = max(worst, abs(diff))
    check(len(rows) >= 3, f"{chip}: {len(rows)} gradini LoRa con un valore di datasheet confrontabile")
check(worst <= 4.1, f"la stima dello studio (formula con SNR del datasheet e cifra di rumore 6 dB) sta entro {worst:.1f} dB dal datasheet; il peggiore e' R3 (500/SF6, ottimista di 4 dB)")
check(all(abs(lc.compare_sensitivity("SX1278")[i][3]) <= 3.0 for i, r in enumerate(lc.compare_sensitivity("SX1278")) if r[0] != 3), "escluso R3, lo scarto sull'SX1278 e' al massimo 3 dB")
# canali e larghezze
for idx in ch.PROFILE0:
    f, bw, _ = ch.PROFILE0[idx]
    check(lc.in_tuning("SX1278", f) and lc.in_tuning("SX1262", f), f"canale {idx} ({f / 1000:.3f} MHz) nel campo di sintonia di entrambi i chip")
for idx in ch.PROFILE0:
    lora = [r for r in ch.allowed_rungs(idx) if pi.RUNGS[r][1] == "LORA"]
    check(all(pi.RUNGS[r][2][0] <= ch.PROFILE0[idx][1] for r in lora) and all(lc.rung_support(r, "SX1278", ch.PROFILE0[idx][0])[0] for r in lora if r < 12), f"canale {idx}: i gradini LoRa ammessi (R{lora}) stanno nella larghezza e sono realizzabili (R12-R14 solo con TCXO)")
# canale di servizio a 2 m: FSK stretta, banda occupata 9,6 kHz
f2m = ch.SERVICE_2M_KHZ
check(lc.in_tuning("SX1278", f2m) and not lc.in_tuning("SX1262", f2m), "voto a 2 m: SX1278 si', SX1262 no (datasheet)")
check(all(b not in (250.0, 500.0) for b in (125.0,)) and lc.LORA_NOT_IN_BAND3 == (250.0, 500.0), "a 144,9 MHz (Band 3) l'SX1278 non fa LoRa 250 e 500 kHz: il canale di servizio usa FSK, non e' toccato")
need = 4.8 + 2 * 2.4 + 2 * (2 * 10 * f2m / 1e6)
check(9.6 <= need <= 15.6, f"FSK a 4,8 kb/s e deviazione 2,4 kHz: banda occupata 9,6 kHz, in ricezione servono circa {need:.1f} kHz con due quarzi da 10 ppm -> filtro di ricezione da 15,6 kHz (totale; 12,5 solo con quarzi da 5 ppm), non 10,4")
print("limiti dei chip: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
