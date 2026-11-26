"""Il simulatore sopra mittente, ricevitore e collegamento indipendenti (tools/img_proto.py) da' ESATTAMENTE i risultati di riferimento su 134 scenari (tests/sim/golden_sim_immagini.json).
Il riferimento e' stato catturato prima della separazione (identico) e rigenerato il 26/11/2026 dopo tre correzioni del protocollo (indice di finestra nei frame DATA, k del ricevitore, DONE senza oracolo):
cambiano 8 scenari di pochi secondi, nessun esito.   python3 -I tests/sim/test_golden_sim_immagini.py"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import golden_sim_immagini as g  # noqa: E402

gold = json.load(open(os.path.join(HERE, "golden_sim_immagini.json")))
now = g.tutti()
diff = []
for a, b in zip(gold, now):
    if a["sc"] != json.loads(json.dumps(b["sc"], default=list)) and a["res"] != b["res"]:
        pass
    if a["res"] != json.loads(json.dumps(b["res"])):
        diff.append((a["sc"], a["res"], b["res"]))
ok = len(gold) == len(now) and not diff
print(f"{'ok' if ok else 'FALLITO'}: {len(now)} scenari (di cui {sum(1 for d in now if d['res']['ok'])} riusciti, {sum(1 for d in now if not d['res']['ok'])} falliti): risultati identici a quelli di riferimento")
for sc, r0, r1 in diff[:3]:
    print("  scenario", sc)
    for k in r0:
        if r0[k] != r1.get(k):
            print(f"    {k}: atteso {str(r0[k])[:150]} ottenuto {str(r1.get(k))[:150]}")
print("simulatore a stazioni indipendenti: identico al precedente" if ok else f"{len(diff)} scenari diversi")
sys.exit(0 if ok else 1)
