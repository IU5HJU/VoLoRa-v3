#!/usr/bin/env python3
"""Il PDF "modi e negoziazione" (docs/pdf/modi-e-negoziazione-v3.pdf): esiste, e le soglie che descrive sono quelle del firmware (img_proto.h)."""
import os, re, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
n = 0
def ok(c, m):
    global n
    n += 1
    if not c:
        print("FALLITO:", m); sys.exit(1)

pdf = open(os.path.join(ROOT, "docs", "pdf", "modi-e-negoziazione-v3.pdf"), "rb").read()
ok(pdf[:5] == b"%PDF-" and len(pdf) > 20000, "PDF mancante o troppo piccolo: python3 tools/gen_pdf_modi.py")
ok(len(re.findall(rb"/Type\s*/Page[^s]", pdf)) >= 6, "meno di 6 pagine")

hdr = open(os.path.join(ROOT, "firmware", "v3", "src", "img_proto.h"), encoding="utf-8").read()
gen = open(os.path.join(ROOT, "tools", "gen_pdf_modi.py"), encoding="utf-8").read()
def const(name):
    m = re.search(name + r"\s*=\s*([0-9.]+)", hdr)
    ok(m is not None, "costante %s non trovata in img_proto.h" % name)
    return float(m.group(1))
ok(const("kMarginUpDb") == 6.0 and '"6 dB"' in gen, "margine di salita")
ok(const("kLossDown") == 0.20 and '"20 %"' in gen, "perdita per la discesa")
ok(const("kLossUp") == 0.02 and '"2 %"' in gen, "perdita per la salita")
ok(const("kProbeOk") == 0.9 and '"90 %"' in gen, "quota di PROBE")
ok(const("kGuardS") == 0.15 and '"0,15 s"' in gen, "pausa di guardia")
ok(const("kGiveUpS") == 900.0 and '"900 s"' in gen, "tempo di rinuncia")
m = re.search(r"kScanOrder\[kMaxCalendar\]\s*=\s*\{([^}]*)\}", hdr)
ok(m and [int(x) for x in m.group(1).split(",")] == [10, 11, 10, 12, 10, 13, 10, 14] and "cal = [10, 11, 10, 12, 10, 13, 10, 14]" in gen, "calendario della ricerca")
ok("stime non misure" in gen and "non misurato sul campo" in gen, "avviso sullo stato")
print("OK test_pdf_modi: %d controlli" % n)
