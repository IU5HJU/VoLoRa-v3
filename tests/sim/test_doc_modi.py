#!/usr/bin/env python3
"""Il documento dei modi radio (docs/modi-radio-v3.md e site/modi.html) deve essere quello generato dai numeri del protocollo, e dire che sono stime."""
import os, subprocess, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_doc_modi as g
import protocollo_immagini as p

n = 0
def ok(c, m):
    global n
    n += 1
    if not c:
        print("FALLITO:", m); sys.exit(1)

md = open(os.path.join(ROOT, "docs", "modi-radio-v3.md"), encoding="utf-8").read()
ok(md == g.build_md(), "docs/modi-radio-v3.md non e' aggiornato: python3 tools/gen_doc_modi.py")
title, body = g.md_to_html(md)
page = open(os.path.join(ROOT, "site", "modi.html"), encoding="utf-8").read()
ok(g.PAGE.replace("@@TITLE@@", title).replace("@@BODY@@", body) == page, "site/modi.html non e' aggiornato")
for rid in range(15):
    ok("| **R%d**" % rid in md, "manca R%d nella tabella" % rid)
ok("stime di studio, non misure" in md, "manca l'avviso sulle stime")
ok(md.count("| **R") >= 18, "tabelle incomplete")
ok("viewport" in page and "overflow-x:auto" in page, "pagina non adatta al telefono")
ok(len(p.RUNGS) == 15, "la scala non ha 15 gradini")
print("OK test_doc_modi: %d controlli" % n)
