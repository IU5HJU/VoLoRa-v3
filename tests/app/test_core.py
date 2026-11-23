"""Prove della logica dell'applicazione: python3 -I tests/app/test_core.py"""
import math
import os
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "app"))
from volora_misure import core, runner, serialio  # noqa: E402

fails = 0


def check(c, msg):
    global fails
    if not c:
        print("FALLITO:", msg)
        fails += 1


# modi
names = dict(core.mode_names())
check(len(names) == 19 and "L9" in names and "F6" in names, "elenco dei modi")
check(core.mode_command("L4") == "MODE LORA 250 7 5", "comando L4")
check(core.mode_command("l9") == "MODE LORA 125 12 5", "comando L9 minuscolo")
check(core.mode_command("F2", "SX1278") == "MODE FSK 150 50 250", "FSK 150k con banda limitata a 250 sull'SX1278")
check(core.mode_command("F1", "SX1262") == "MODE FSK 300 100 467", "FSK 300k con banda limitata a 467 sull'SX1262")
check(abs(core.sens_estimate("L4") + 122) < 1, "sensibilita' L4")

# righe
k, d = core.parse_line("RXSUM ok=18 bad=1 lost=1 dup=0 bit_err=3 first=1 last=20 rssi=-100.5 snr=nan fei_hz=-120")
check(k == "RXSUM" and d["ok"] == 18 and d["rssi"] == -100.5 and math.isnan(d["snr"]) and d["fei_hz"] == -120, "RXSUM")
k, d = core.parse_line("TXSUM sent=20 toa_mean_us=200123 calc_us=200000")
check(k == "TXSUM" and d["sent"] == 20, "TXSUM")
check(core.parse_line("ERR radio st=-2")[0] == "ERR" and core.parse_line("")[0] is None and core.parse_line("boh")[0] is None, "altre righe")

# riga di risultato e CSV
_, t = core.parse_line("TXSUM sent=200 toa_mean_us=1000 calc_us=1000")
_, r = core.parse_line("RXSUM ok=190 bad=2 lost=8 rssi=-110.0 snr=-3.0 fei_hz=50")
row = core.new_row("L5", 433.475, 2, 112.0, t, r)
check(row["p_rx_dbm"] == -110.0 and row["loss_pct"] == 5.0 and row["rx_ok"] == 190, "riga di risultato")
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "r.csv")
    core.save_csv(p, [row])
    back = core.load_csv(p)
    check(len(back) == 1 and back[0]["mode"] == "L5" and back[0]["sent"] == 200 and back[0]["p_rx_dbm"] == -110.0, "CSV salva e rilegge")
rows = [dict(row, att_db=a, p_rx_dbm=2 - a, loss_pct=l) for a, l in ((110, 0.0), (120, 4.0), (125, 40.0))]
s = core.sensitivities(rows)
check(s["L5"][0] == -118 and abs(s["L5"][1] - (-118 - core.sens_estimate("L5"))) < 1e-9, "sensibilita' dal CSV")
md = core.results_markdown(rows, "IU5HJU", "T3", "T3", "misura 0.1.0", "prova")
check("| L5 |" in md and "Sensibilità" in md and "IU5HJU" in md, "pagina di note")

# GitHub: indirizzo precompilato
u = core.issue_url("IU5HJU/VoLoRa-v3", "Misure - IU5HJU - 2026-11-21", "riga\n" * 3000, max_url=2000)
check(u.startswith("https://github.com/IU5HJU/VoLoRa-v3/issues/new?") and len(u) <= 2100 and "accorciato" in u.replace("%20", " ").replace("%28", "(") or "accorciato" in __import__("urllib.parse").parse.unquote(u), "indirizzo della segnalazione accorciato")
u2 = core.issue_url("a/b", "t", "corto")
check("body=corto" in u2, "indirizzo corto senza tagli")

# GitHub: caricamento con rete finta
calls = []


def fake_http(method, url, token, payload):
    calls.append((method, url.replace("https://api.github.com/repos/", ""), payload))
    if method == "GET":
        return 200, {"object": {"sha": "abc123"}}
    if url.endswith("/git/refs"):
        return 201, {}
    if "/contents/" in url:
        return 201, {}
    if url.endswith("/pulls"):
        return 201, {"html_url": "https://github.com/x/y/pull/7"}
    return 404, {}


pr = core.upload_to_github("TOKEN", "IU5HJU/VoLoRa-v3", "main", {"a.csv": b"x,y\n1,2\n", "a.md": b"# n\n"}, "IU5HJU", fake_http)
check(pr == "https://github.com/x/y/pull/7", "indirizzo della PR")
check([c[0] for c in calls] == ["GET", "POST", "PUT", "PUT", "POST"], "sequenza delle chiamate: " + str([c[0] for c in calls]))
check(calls[1][2]["sha"] == "abc123" and calls[1][2]["ref"].startswith("refs/heads/misure/IU5HJU-"), "ramo nuovo dal ramo base")
check(calls[2][2]["branch"] == calls[1][2]["ref"][len("refs/heads/"):] and calls[2][1].endswith("docs/misure/a.csv"), "file in docs/misure sul ramo nuovo")
import base64
check(base64.b64decode(calls[2][2]["content"]) == b"x,y\n1,2\n", "contenuto del file")
try:
    core.upload_to_github("T", "a/b", "main", {"a": b"x"}, "X", lambda *a: (403, {"message": "no"}))
    check(False, "errore atteso senza ramo")
except RuntimeError as e:
    check("non trovato" in str(e), "errore leggibile")
try:
    state = {"n": 0}
    def h2(method, url, token, payload):
        state["n"] += 1
        return (200, {"object": {"sha": "s"}}) if method == "GET" else (403, {"message": "Resource not accessible"})
    core.upload_to_github("T", "a/b", "main", {"a": b"x"}, "X", h2)
    check(False, "errore atteso senza permesso")
except RuntimeError as e:
    check("permesso di scrittura" in str(e), "senza permesso: messaggio chiaro")

# immagini fittizie
b = core.make_blob(5000, seed=3)
check(len(b) == 5000 and core.check_blob(b) and core.make_blob(5000, seed=3) == b and core.make_blob(5000, seed=4) != b, "blocco di prova riproducibile con CRC")
bad = bytearray(b); bad[100] ^= 1
check(not core.check_blob(bytes(bad)), "il CRC del blocco rileva un bit")
png = core.make_test_png(64, 48)
check(png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (64, 48), "PNG: firma e dimensioni")
try:
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(png)); im.load()
    check(im.size == (64, 48) and im.mode == "L", "PNG leggibile da Pillow")
    j = core.make_test_jpeg(64, 48)
    check(j is not None and Image.open(io.BytesIO(j)).format == "JPEG", "JPEG di prova")
except ImportError:
    pass
check(len(core.make_test_png(200, 100)) > len(core.make_test_png(64, 48)) // 2, "PNG piu' grande")
rows_est = core.estimate_rows(5000)
check(len(rows_est) == 15 and rows_est[0][0].startswith("R0"), "stime per gradino")

# SerialBoard: la prima scrittura e' una riga vuota, poi il comando intero
import types
writes = []


class _FakeSerial:
    def __init__(self, port, baud, timeout=0):
        pass

    def read(self, n):
        import time as _t
        _t.sleep(0.02)
        return b""

    def write(self, b):
        writes.append(b)

    def close(self):
        pass


sys.modules["serial"] = types.SimpleNamespace(Serial=_FakeSerial)
sb = serialio.SerialBoard("A", "/dev/ttyACM0")
sb.send("INFO")
sb.send("SHOW")
sb.close()
check(writes == [b"\n", b"INFO\n", b"SHOW\n"], f"seriale: riga vuota prima del primo comando, poi i comandi interi: {writes}")
del sys.modules["serial"]

# sequenza di misura con le schede finte
link, a, bb = serialio.fake_pair(speed=200)
link.att_db = 100
runner.configure([a, bb], "L4", 2, 433.475, 64, "IU5HJU")
row = runner.run_point(a, bb, "L4", 20, 300, 2, 100.0, 433.475)
check(row["sent"] == 20 and row["rx_ok"] == 20 and row["loss_pct"] == 0.0, "misura finta con segnale forte")
link.att_db = 140
row = runner.run_point(a, bb, "L4", 20, 300, 2, 140.0, 433.475)
check(row["rx_ok"] <= 1 and row["loss_pct"] >= 90.0, "misura finta con segnale sotto la sensibilita'")
# serie di modi
check(core.parse_series("R11, R12;R13 R14") == ["L10", "L11", "L12", "L13"], "serie: R11-R14 diventano L10-L13")
try:
    core.parse_series("R99")
    check(False, "serie con modo sconosciuto deve dare errore")
except ValueError:
    check(True, "serie con modo sconosciuto: errore")
check(core.interval_ms("L13", 26) > 30000 and core.interval_ms("L4", 26) == 300, f"intervallo dal tempo in aria: L13 {core.interval_ms('L13', 26)} ms, L4 {core.interval_ms('L4', 26)} ms")
link.att_db = 100
got = []
rows = runner.run_series(a, bb, ["L4", "L5"], 5, 2, 100.0, 433.475, 26, "IU5HJU", on_row=got.append)
check([r["mode"] for r in rows] == ["L4", "L5"] and len(got) == 2 and all(r["rx_ok"] == 5 for r in rows), "serie finta L4, L5: due righe, 5/5")
import threading
ev = threading.Event(); ev.set()
check(runner.run_series(a, bb, ["L4"], 5, 2, 100.0, 433.475, 26, "IU5HJU", stop=ev) == [], "serie gia' fermata: nessuna misura")
try:
    runner.command(a, "FREQ", "MODE", timeout=1)
    check(False, "FREQ senza argomento deve dare errore")
except Exception:
    pass

if fails:
    print(fails, "prove fallite")
    sys.exit(1)
print("app: tutte le prove passate")
