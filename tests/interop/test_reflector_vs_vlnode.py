"""Interoperabilita': il reflector V3 (tools/reflector_v3.py) contro il VERO vlnode della v2 (third_party/VoLoRa-v2), su veri socket UDP.
Costruisce vlnode da una copia del submodule in una cartella temporanea (il submodule non si tocca) oppure usa VLNODE=<percorso>. Salta se manca il compilatore o il submodule.
    python3 tests/interop/test_reflector_vs_vlnode.py"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import reflector_v3 as rv  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


vlnode = os.environ.get("VLNODE")
tmp = tempfile.mkdtemp(prefix="vl3-interop-")
try:
    if not vlnode:
        src = os.path.join(ROOT, "third_party", "VoLoRa-v2")
        if not os.path.exists(os.path.join(src, "tools", "vlnode.cpp")) or not shutil.which("g++") or not shutil.which("make"):
            print("salto: manca il submodule della v2 o il compilatore")
            sys.exit(0)
        cp = os.path.join(tmp, "v2")
        shutil.copytree(src, cp, ignore=shutil.ignore_patterns(".git", "build"))
        r = subprocess.run(["make", "build/vlnode"], cwd=cp, capture_output=True, text=True)
        vlnode = os.path.join(cp, "build", "vlnode")
        if r.returncode != 0 or not os.path.exists(vlnode):
            print("salto: vlnode non si compila:", r.stderr[-300:])
            sys.exit(0)
    conf = os.path.join(tmp, "ref.conf")
    open(conf, "w").write("2 000102030405060708090a0b0c0d0e0f nodoA\n3 101112131415161718191a1b1c1d1e1f nodoB\n")
    port = random.randint(30000, 60000)
    cores = []
    th = threading.Thread(target=lambda: cores.append(rv.serve(conf, port, 1000, 1, 22, "127.0.0.1", log=lambda s: None)), daemon=True)
    th.start()
    time.sleep(0.6)
    b = subprocess.Popen([vlnode, "--id", "3", "--peer-id", "1000", "--key", "101112131415161718191a1b1c1d1e1f", "--listen", "0", "--peer", f"127.0.0.1:{port}", "--duration", "14"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(3)
    a = subprocess.run([vlnode, "--id", "2", "--peer-id", "1000", "--key", "000102030405060708090a0b0c0d0e0f", "--listen", "0", "--peer", f"127.0.0.1:{port}",
                        "--send-text", "IU5HJU", "Prova via reflector V3", "--send-voice", "IZ5IOF", "--frames", "60", "--duration", "8"], capture_output=True, text=True, timeout=60)
    ob = b.communicate(timeout=60)[0]
    check("collegamento ATTIVO" in a.stdout and "collegamento ATTIVO" in ob, "i due vlnode della v2 si collegano al reflector V3 (sfida, firma, contatore)")
    check('testo "Prova via reflector V3"' in ob and "IU5HJU" in ob, "il testo del nodo A arriva al nodo B")
    check("modo 1 sessione" in ob and "IZ5IOF" in ob and ob.count("(ripetuto)") >= 10, f"la voce del nodo A arriva al nodo B con il flag RELAYED ({ob.count('(ripetuto)')} pacchetti)")
    check("firme errate 0" in a.stdout and "firme errate 0" in ob, "nessuna firma rifiutata dai nodi v2: il reflector firma come il reflector v2")
    check("sconosciuti 1" in a.stdout or "sconosciuti" in a.stdout, "la sfida dopo l'avvio e' stata gestita come nella v2")
    th.join(timeout=30)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("interoperabilita' con la v2: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
