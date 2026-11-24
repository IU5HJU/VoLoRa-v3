"""Prove della prova di collegamento con moduli UART finti: python3 tests/app/test_uartlink.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "app"))
from volora_misure import uartlink as ul  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


p = ul.make_payload(7, 50, 100, 1234)
check(len(p) == 100 and ul.check_payload(p) == (7, 50, 1234), "payload di prova: 100 byte, intestazione e riempimento verificabili")
bad = bytearray(p)
bad[50] ^= 1
check(ul.check_payload(bytes(bad)) is None, "un byte rovinato nel riempimento viene riconosciuto")

pair = ul.FakeModulePair(loss=0.0, seed=1)
r = ul.run_link_test(pair.a, pair.b, 30, 100, interval_s=0.005, wait_s=1.0)
check(r["sent"] == 30 and r["ok"] == 30 and r["loss_pct"] == 0.0 and r["bad_crc"] == 0, f"collegamento senza perdite: 30 su 30 ({ul.summary_line(r)})")
check(r["lat_mean_ms"] is not None and 0 <= r["lat_mean_ms"] < 500 and r["bps"] > 0, f"latenza media {r['lat_mean_ms']:.0f} ms, velocita' {r['bps'] / 1000:.1f} kbit/s")

pair = ul.FakeModulePair(loss=0.3, seed=2)
r = ul.run_link_test(pair.a, pair.b, 60, 100, interval_s=0.003, wait_s=1.0)
check(0 < r["ok"] < 60 and 10 < r["loss_pct"] < 60 and r["bad_content"] == 0, f"con il 30 % di pacchetti d'aria persi: {r['ok']} su 60 ricevuti, nessun contenuto sbagliato")

pair = ul.FakeModulePair(corrupt=0.5, seed=3)
r = ul.run_link_test(pair.a, pair.b, 60, 100, interval_s=0.003, wait_s=1.0)
check(r["bad_crc"] >= 5 and r["bad_content"] == 0 and r["ok"] + r["bad_crc"] >= 40, f"con byte rovinati: {r['bad_crc']} scartati dal CRC, nessuno accettato per errore")

pair = ul.FakeModulePair(loss=0.0, seed=4, air_max=60)
r = ul.run_link_test(pair.a, pair.b, 20, 200, interval_s=0.01, wait_s=1.0)
check(r["ok"] == 20, "frame piu' lunghi del pacchetto d'aria (60 byte): rimessi insieme dal flusso, 20 su 20")
print("moduli UART: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
