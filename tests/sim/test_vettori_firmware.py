"""I vettori di prova del firmware V3 nel repository sono quelli che il riferimento Python genera oggi? python3 -I tests/sim/test_vettori_firmware.py
(se il riferimento cambia, rigenerare: python3 tools/gen_vettori_firmware.py, e rifare le prove del nucleo C++: make -C firmware/v3 test)"""
import filecmp
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_vettori_firmware as gen  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


repo = os.path.join(ROOT, "firmware", "v3", "tests", "vettori")
with tempfile.TemporaryDirectory() as tmp:
    nomi = gen.genera(tmp)
    check(len(nomi) == 15, f"il generatore produce {len(nomi)} file di vettori")
    for n in nomi:
        a, b = os.path.join(tmp, n + ".txt"), os.path.join(repo, n + ".txt")
        check(os.path.exists(b) and filecmp.cmp(a, b, shallow=False), f"vettori '{n}' aggiornati nel repository")
    extra = sorted(set(f[:-4] for f in os.listdir(repo) if f.endswith(".txt")) - set(nomi))
    check(not extra, f"nessun file di vettori in piu' ({extra})")
print("vettori del firmware: tutti aggiornati" if not fails else f"{fails} prove fallite: rigenerare con tools/gen_vettori_firmware.py")
sys.exit(1 if fails else 0)
