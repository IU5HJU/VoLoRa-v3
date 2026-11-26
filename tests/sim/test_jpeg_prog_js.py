"""Prova del trasformatore JPEG baseline -> progressivo senza perdite in JavaScript (site/jpeg_prog.js) contro libjpeg (Pillow).
Serve node, Pillow e numpy; salta se mancano.   python3 -I tests/sim/test_jpeg_prog_js.py"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
try:
    import numpy as np
    from PIL import Image
except ImportError:
    print("salto: servono Pillow e numpy")
    sys.exit(0)
if not shutil.which("node"):
    print("salto: manca node")
    sys.exit(0)
import immagine_livelli as il  # noqa: E402
import protocollo_immagini as pi  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


def foto(w, h, seed=3):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    a = np.zeros((h, w, 3), float)
    a[..., 0] = 128 + 100 * np.sin(x / 30.0) * np.cos(y / 45.0)
    a[..., 1] = 128 + 90 * np.cos(x / 17.0 + y / 40.0)
    a[..., 2] = 100 + 80 * np.sin((x + y) / 25.0)
    a[h // 4:h // 2, w // 3:w * 2 // 3] = [220, 40, 40]
    a += rng.normal(0, 6, a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"))


tmp = tempfile.mkdtemp(prefix="vl3-jpg-")
CLI = os.path.join(ROOT, "tests", "page", "jpeg_prog_cli.js")


def trans(baseline_bytes, name):
    src, dst = os.path.join(tmp, name + ".jpg"), os.path.join(tmp, name + ".prog.jpg")
    open(src, "wb").write(baseline_bytes)
    r = subprocess.run(["node", CLI, src, dst], capture_output=True, text=True)
    if r.returncode != 0:
        return None, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "errore"
    return (open(dst, "rb").read(), json.loads(r.stdout)), ""


def baseline(im, **kw):
    b = io.BytesIO()
    im.save(b, "JPEG", **kw)
    return b.getvalue()


def dec(d):
    im = Image.open(io.BytesIO(d))
    im.load()
    return im


try:
    casi = [
        ("colore 4:2:0 320x240", foto(320, 240), dict(quality=75, subsampling=2)),
        ("colore 4:4:4 320x240", foto(320, 240), dict(quality=75, subsampling=0)),
        ("colore 4:2:2 160x120", foto(160, 120), dict(quality=60, subsampling=1)),
        ("colore dimensioni dispari 251x187", foto(251, 187, 5), dict(quality=80, subsampling=2)),
        ("colore piccolo 33x17", foto(33, 17, 6), dict(quality=50, subsampling=2)),
        ("colore 1x1", foto(1, 1, 7), dict(quality=90)),
        ("colore qualita' bassa 640x480", foto(640, 480), dict(quality=15, subsampling=2)),
        ("colore qualita' alta 192x144", foto(192, 144, 8), dict(quality=95, subsampling=0)),
        ("bianco e nero 320x240", foto(320, 240).convert("L"), dict(quality=75)),
        ("bianco e nero dispari 77x41", foto(77, 41, 9).convert("L"), dict(quality=70)),
        ("con intervalli di ripartenza", foto(320, 240, 10), dict(quality=75, subsampling=2, restart_marker_blocks=7)),
    ]
    for nome, im, kw in casi:
        base = baseline(im, **kw)
        if "restart_marker_blocks" in kw:
            check(b"\xff\xdd" in base, f"{nome}: il JPEG di partenza ha davvero l'intervallo di ripartenza (DRI)")
        res, err = trans(base, nome.split()[0] + str(len(base)))
        if res is None:
            if "restart_marker" in str(kw):
                check(False, f"{nome}: {err}")
            else:
                check(False, f"{nome}: errore del trasformatore: {err}")
            continue
        prog, ends = res
        a, b = dec(base), dec(prog)
        n_scans = len(il.scansioni(prog))
        gray = im.mode == "L"
        check(il.e_progressivo(prog) and a.size == b.size and a.mode == b.mode and a.tobytes() == b.tobytes(), f"{nome}: JPEG progressivo con gli STESSI pixel del baseline ({len(base)} -> {len(prog)} byte)")
        check(n_scans == (6 if gray else 10), f"{nome}: {n_scans} scansioni (come libjpeg)")
        check(len(ends) == 3 and ends[2] == len(prog) and ends[0] < ends[1] < ends[2] and ends[0] % 16 == 0 and ends[1] % 16 == 0, f"{nome}: tre livelli con i confini su pezzo da 16: {ends}")
        # i livelli sono prefissi validi e la qualita' cresce
        ps = [il.psnr(dec(il.prefisso(prog, ends, k)), b) for k in (1, 2, 3)] if max(a.size) > 1 else [99, 99, 99]
        if max(a.size) >= 32:
            check(ps[0] <= ps[1] <= ps[2] and ps[2] == 99.0 and all(dec(il.prefisso(prog, ends, k)).size == b.size for k in (1, 2, 3)), f"{nome}: ogni livello si decodifica e la qualita' cresce ({ps[0]:.1f} -> {ps[1]:.1f} -> identico)")
        # stesso raggruppamento in livelli del programma da PC
        py = il.livelli(prog)
        check(py[2] == len(prog) and py[0] <= ends[0] and ends[0] - py[0] < 20 and py[1] <= ends[1] and ends[1] - py[1] < 20, f"{nome}: i livelli coincidono con quelli di tools/immagine_livelli.py (scarto dovuto al riempimento: {ends[0] - py[0]} e {ends[1] - py[1]} byte)")
    # confronto di dimensione con libjpeg
    im = foto(320, 240)
    base = baseline(im, quality=75, subsampling=2)
    prog_js, ends_js = trans(base, "conf")[0]
    ref = io.BytesIO()
    im.save(ref, "JPEG", quality=75, subsampling=2, progressive=True, optimize=True)
    check(len(prog_js) <= 1.05 * len(ref.getvalue()), f"dimensione vicina a quella di libjpeg (progressivo ottimizzato): {len(prog_js)} contro {len(ref.getvalue())} byte")
    # ingressi non validi: errore pulito, nessun crollo
    for nome, bad in (("vuoto", b""), ("testo", b"non e' un jpeg"), ("troncato", base[:300]), ("gia' progressivo", prog_js)):
        res, err = trans(bad, "bad" + nome[:3])
        check(res is None and err, f"ingresso {nome}: errore chiaro ({err[:60]})")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("trasformatore JPEG progressivo in JavaScript: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
