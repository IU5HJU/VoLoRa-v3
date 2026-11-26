"""Interoperabilita' del reflector V3 in C++ (third_party/VoLoRa-v2 + reflector/v3.patch) su veri socket UDP:
 1) due VERI vlnode della v2 (testo e voce con RELAYED) come col reflector v2;
 2) due client V3 (tools/nodelink.py con dichiarazione) e un client v2: annuncio, busta, esito, e il client v2 non vede nulla del V3.
Salta se manca il compilatore o il submodule.   python3 tests/interop/test_reflector_cpp.py"""
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import frame_mesh as fm  # noqa: E402
import nodelink as nl  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


src = os.path.join(ROOT, "third_party", "VoLoRa-v2")
if not os.path.exists(os.path.join(src, "tools", "vlnode.cpp")) or not shutil.which("g++") or not shutil.which("make"):
    print("salto: manca il submodule della v2 o il compilatore")
    sys.exit(0)
tmp = tempfile.mkdtemp(prefix="vl3-cpp-")
try:
    r = subprocess.run([os.path.join(ROOT, "reflector", "build.sh"), os.path.join(tmp, "ref")], capture_output=True, text=True)
    if r.returncode != 0:
        print("FALLITO: la patch non si applica o non compila:\n", r.stdout[-800:], r.stderr[-1500:])
        sys.exit(1)
    refl = os.path.join(tmp, "ref", "build", "vlreflector")
    cp = os.path.join(tmp, "v2")
    shutil.copytree(src, cp, ignore=shutil.ignore_patterns(".git", "build"))
    rr = subprocess.run(["make", "build/vlnode"], cwd=cp, capture_output=True, text=True)
    vlnode = os.path.join(cp, "build", "vlnode")
    if rr.returncode != 0 or not os.path.exists(vlnode):
        print("salto: vlnode non si compila:", rr.stderr[-300:])
        sys.exit(0)
    keys = {2: "000102030405060708090a0b0c0d0e0f", 3: "101112131415161718191a1b1c1d1e1f", 4: "20" * 16, 5: "30" * 16, 6: "40" * 16}
    conf = os.path.join(tmp, "ref.conf")
    open(conf, "w").write("".join(f"{i} {k} nodo{i}\n" for i, k in keys.items()))

    tokf = os.path.join(tmp, "admin.token")
    open(tokf, "w").write("token-di-prova-0123456789\n")
    os.chmod(tokf, 0o600)

    def start(port):
        p = subprocess.Popen([refl, "--config", conf, "--port", str(port), "--id", "1000", "--voice-mode", "1", "--duration", "60", "--web", str(port + 1), "--admin-token-file", tokf], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(0.5)
        return p

    # --- 1) due vlnode veri
    port = random.randint(30000, 60000)
    p = start(port)
    b = subprocess.Popen([vlnode, "--id", "3", "--peer-id", "1000", "--key", keys[3], "--listen", "0", "--peer", f"127.0.0.1:{port}", "--duration", "14"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(3)
    a = subprocess.run([vlnode, "--id", "2", "--peer-id", "1000", "--key", keys[2], "--listen", "0", "--peer", f"127.0.0.1:{port}", "--send-text", "IU5HJU", "Prova via reflector C++",
                        "--send-voice", "IZ5IOF", "--frames", "60", "--duration", "8"], capture_output=True, text=True, timeout=60)
    ob = b.communicate(timeout=60)[0]
    check("collegamento ATTIVO" in a.stdout and "collegamento ATTIVO" in ob, "i due vlnode della v2 si collegano al reflector C++ con la patch")
    check('testo "Prova via reflector C++"' in ob and "IU5HJU" in ob, "il testo arriva")
    check("modo 1 sessione" in ob and "IZ5IOF" in ob and ob.count("(ripetuto)") >= 10, f"la voce arriva con RELAYED ({ob.count('(ripetuto)')} pacchetti)")
    check("firme errate 0" in a.stdout and "firme errate 0" in ob, "nessuna firma rifiutata dai nodi v2")
    p.terminate()
    p.wait(timeout=10)

    # --- 2) client V3 e client v2 in Python su socket veri
    port = random.randint(30000, 60000)
    p = start(port)
    rng = random.Random(5)
    ext = b"V3" + bytes([1, 3])

    class C:
        def __init__(self, cid, v3):
            self.id, self.v3 = cid, v3
            self.link = nl.NodeLink(cid, 1000, bytes.fromhex(keys[cid]), 700 + cid, lambda: rng.getrandbits(32), ext=ext if v3 else b"")
            self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.s.bind(("127.0.0.1", 0))
            self.s.setblocking(False)
            self.got = []

        def pump(self, now):
            m = self.link.maintenance(now)
            if m:
                self.s.sendto(m, ("127.0.0.1", port))
            while True:
                try:
                    d, _ = self.s.recvfrom(2048)
                except BlockingIOError:
                    break
                x = self.link.on_datagram(d, now)
                for rep in x.replies:
                    self.s.sendto(rep, ("127.0.0.1", port))
                if x.kind == nl.PACKET_OK:
                    self.got.append(x.packet)

        def send(self, wire):
            self.s.sendto(self.link.make_packet(wire), ("127.0.0.1", port))

    cl = {i: C(i, v) for i, v in ((4, True), (5, True), (6, False))}

    def run(sec):
        t0 = time.time()
        while time.time() - t0 < sec:
            now = int((time.time() - T0) * 1000)
            for c in cl.values():
                c.pump(now)
            time.sleep(0.02)

    T0 = time.time()
    run(6)
    check(all(c.link.link_up(int((time.time() - T0) * 1000)) for c in cl.values()), "i tre client (due V3 e uno v2) sono collegati")
    ANA, ANB = "IZ5AAA", "IZ5BBB"
    cl[4].send(fm.enc_refl_annuncio([(ANA, 10), (ANB, 20)]))
    run(0.5)
    inner = bytes([0x3E, 1, 2, 3])
    cl[5].send(fm.enc_refl_inoltro(ANA, "IU5HJU", 3, inner))
    run(1)
    check(any(len(g) > 14 and g[1] == 81 and g.endswith(inner) for g in cl[4].got), "la busta arriva al gateway che sente la destinazione")
    check(any(len(g) == 9 and g[1] == 82 and g[8] == fm.ESITO_CONSEGNATO for g in cl[5].got), "il mittente riceve l'esito CONSEGNATO")
    cl[5].got.clear()
    cl[5].send(fm.enc_refl_inoltro("IZ5ZZZ", "IU5HJU", 3, inner))
    run(1)
    check(any(len(g) == 9 and g[1] == 82 and g[8] == fm.ESITO_NON_TROVATO for g in cl[5].got), "destinazione ignota: esito NON TROVATO")
    cl[6].send(fm.enc_refl_annuncio([(ANA, 1)]))
    run(0.5)
    check(not cl[6].got and not any(g[0] == 0x3E for g in cl[4].got[1:] if g[1] == 80), "il client v2 non puo' iscrivere ne' ricevere frame V3")
    run(21)  # la dichiarazione del reflector viaggia nel KEEPALIVE successivo (20 s): i frame V3 non la aspettano
    check(cl[4].link.peer_ext[:2] == b"V3" and cl[5].link.peer_ext[:2] == b"V3", "il reflector C++ risponde (nel KEEPALIVE) con la dichiarazione V3 ai client V3")
    check(cl[6].link.peer_ext == b"", "e non manda nulla in piu' al client v2")
    import json
    import urllib.request
    rq = urllib.request.Request(f"http://127.0.0.1:{port + 1}/api/status", headers={"X-Token": "token-di-prova-0123456789"})
    st = json.loads(urllib.request.urlopen(rq, timeout=5).read())
    flags = {c["id"]: c.get("v3") for c in st["clients"]}
    check(flags.get(4) is True and flags.get(5) is True and flags.get(6) is False, f"la pagina di amministrazione segna V3 solo sui nodi V3 {flags}")
    check(st["stats"]["v3Forwarded"] == 1 and st["stats"]["v3Announces"] >= 1 and st["stats"]["v3Refused"] >= 1, f"contatori V3 nello stato: {st['stats']}")
    html = urllib.request.urlopen(f"http://127.0.0.1:{port + 1}/", timeout=5).read().decode()
    check("<th" in html and ">V3</th>" in html and "c.v3" in html, "la pagina ha la colonna V3")
    p.terminate()
    out = p.communicate(timeout=10)[0]
    check("Traceback" not in out and "AddressSanitizer" not in out, "il reflector non da' errori")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("interoperabilita' C++: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
