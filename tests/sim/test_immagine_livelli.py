"""Prove dell'immagine a livelli (JPEG progressivo, tools/immagine_livelli.py): python3 -I tests/sim/test_immagine_livelli.py. Serve Pillow e numpy."""
import io
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
try:
    import numpy as np
    from PIL import Image
except ImportError:
    print("salto: servono Pillow e numpy")
    sys.exit(0)
import ble_bridge as bb  # noqa: E402
import immagine_livelli as il  # noqa: E402
import protocollo_immagini as pi  # noqa: E402
import sim_immagini as si  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


def foto(w=640, h=480, seed=3):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    a = np.zeros((h, w, 3), float)
    a[..., 0] = 128 + 100 * np.sin(x / 60.0) * np.cos(y / 90.0)
    a[..., 1] = 128 + 90 * np.cos(x / 34.0 + y / 80.0)
    a[..., 2] = 100 + 80 * np.sin((x + y) / 50.0)
    a[h // 4:h * 4 // 7, w // 3:w * 2 // 3] = [220, 40, 40]
    a += rng.normal(0, 6, a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"))


img = foto()
r = il.codifica(img, 10000)
d, ends = r["data"], r["ends"]
check(len(d) <= 10000 and d[:2] == b"\xff\xd8" and d[-2:] == il.EOI and il.e_progressivo(d), f"JPEG progressivo di {len(d)} byte ({r['width']}x{r['height']}, qualita' {r['quality']}) dentro il limite di 10000")
sc = il.scansioni(d)
check(len(sc) == 10 and sc[0]["ss"] == 0 and sc[0]["ah"] == 0 and sc[0]["al"] == 1 and sc[-1]["ah"] == 1 and sc[-1]["al"] == 0 and all(a["end"] < b["end"] for a, b in zip(sc, sc[1:])), "dieci scansioni (DC, AC a bande, rifiniture), con i confini crescenti")
check(len(ends) == 3 and ends[0] < ends[1] < ends[2] == len(d), f"tre livelli: fine a {ends} byte (l'ultimo e' l'oggetto intero)")
check(ends[0] % pi.PIECE == 0 and ends[1] % pi.PIECE == 0, f"i confini dei livelli cadono su confini di pezzo da {pi.PIECE} byte (segmento COM di riempimento)")
raw = io.BytesIO()
base_im = img.convert("RGB").resize((r["width"], r["height"]), Image.LANCZOS)
base_im.save(raw, "JPEG", quality=r["quality"], progressive=True, optimize=True)
check(0 <= len(d) - len(raw.getvalue()) <= 2 * 19 and il.decodifica(d).tobytes() == il.decodifica(raw.getvalue()).tobytes(), f"il riempimento costa {len(d) - len(raw.getvalue())} byte e non cambia nemmeno un pixel")
frac = [e / len(d) for e in ends]
check(0.1 < frac[0] < 0.45 and 0.35 < frac[1] < 0.75, f"il primo livello pesa {100 * frac[0]:.0f}% e i primi due {100 * frac[1]:.0f}%: la parte utile arriva presto")
ref = il.decodifica(d)
ps = []
for n in (1, 2, 3):
    p = il.prefisso(d, ends, n)
    im = il.decodifica(p)
    ps.append(il.psnr(im, ref))
    check(im.size == ref.size, f"il livello {n} ({len(p)} byte) e' un JPEG valido e si decodifica alla stessa dimensione")
check(ps[0] < ps[1] < ps[2] and ps[0] > 20.0 and ps[2] == 99.0, f"la qualita' cresce a ogni livello: {ps[0]:.1f} < {ps[1]:.1f} < intero (identico): il primo livello e' gia' una immagine riconoscibile")
orig_small = img.resize(ref.size)
check(il.psnr(il.decodifica(il.prefisso(d, ends, 1)), orig_small) > 18.0, "il primo livello e' vicino all'immagine originale (PSNR oltre 18 dB)")
# limiti di dimensione
prev = None
for mb in (2000, 5000, 10000, 20000, 40000):
    q = il.codifica(img, mb)
    check(q is not None and len(q["data"]) <= mb, f"limite {mb} byte: JPEG di {len(q['data'])} byte, {q['width']}x{q['height']}, qualita' {q['quality']}")
    if prev:
        check(q["width"] * q["height"] >= prev["width"] * prev["height"], "piu' budget non da' un'immagine piu' piccola")
    prev = q
check(il.codifica(img, 150) is None, "un limite impossibile (150 byte): nessuna immagine, non un errore")
g = il.codifica(img, 5000, gray=True)
check(g and len(g["ends"]) == 3 and il.e_progressivo(g["data"]) and len(il.scansioni(g["data"])) == 6, "bianco e nero: sei scansioni e comunque tre livelli")
gr = il.decodifica(g["data"])
check(all(il.decodifica(il.prefisso(g["data"], g["ends"], n)).size == gr.size for n in (1, 2, 3)), "anche in bianco e nero ogni livello si decodifica")
# JPEG non progressivo
b = io.BytesIO()
img.resize((160, 120)).save(b, "JPEG", quality=70)
check(not il.e_progressivo(b.getvalue()) and il.livelli(b.getvalue()) == [len(b.getvalue())], "un JPEG normale (baseline) ha un solo livello")
for bad in (b"", b"abcd", b"\xff\xd8\xff"):
    try:
        il.scansioni(bad)
        ok = bad == b"\xff\xd8\xff"
    except (ValueError, IndexError):
        ok = True
    check(ok, f"dati non JPEG {bad[:4]!r}: errore pulito")
# pezzi dell'OFFER e protocollo
pz = il.pezzi(ends)
check(pz == [-(-e // pi.PIECE) for e in ends] and pz == sorted(pz) and pz[-1] == -(-len(d) // pi.PIECE), f"layer_ends in pezzi da {pi.PIECE} byte: {pz}")
offer = si.enc_offer(0x1234, "IU5HJU", 0, len(d), pi.PIECE, pz[-1], r["width"], r["height"], pz, 0)
dd = si.decode(offer)
check(dd and dd["layer_ends"] == pz, "l'OFFER del protocollo immagini porta i livelli dell'immagine vera")
begin = bb.dec_begin(bb.enc_begin(5, bb.KIND_IMAGE, d, "IK5XYZ", "foto.jpg", r["width"], r["height"], ends))
check(begin["layer_ends"] == ends and begin["size"] == len(d), "il BEGIN del ponte BLE porta le fine dei livelli in byte")
# tempi e budget
t = il.tempi(ends, 5)
check(t[0] < t[1] < t[2] and abs(t[2] - pi.estimate_seconds(len(d), 5, "SX1278")) < 1e-9, f"tempi cumulati a R5: {[round(x) for x in t]} s")
check(il.livelli_nel_budget(ends, 5, 600) == 3 and il.livelli_nel_budget(ends, 10, 600) == 3 and il.livelli_nel_budget(ends, 10, 300) == 2 and il.livelli_nel_budget(ends, 10, 60) == 0, "budget: a R5 e a R10 entrano tre livelli in 10 minuti; a R10 in 5 minuti ne entrano due, in 60 s nessuno")
# attraverso il simulatore del protocollo, con l'oggetto vero e un budget che taglia l'ultimo livello
sim_ok = si.Simulator(len(d), (1.0,), si.Channel(-100.0, rng=random.Random(2)), "SX1278", "SX1278", 600.0, 4, data=d, layer_pieces=pz)
res = sim_ok.run()
check(res.ok and res.layers_delivered == 3 and res.bytes_delivered == len(d) and res.crc_ok, f"nel simulatore (-100 dBm) arrivano tutti e tre i livelli: {res.bytes_delivered} byte")
sim_cut = si.Simulator(len(d), (1.0,), si.Channel(-136.0, rng=random.Random(2)), "SX1278", "SX1278", 240.0, 4, data=d, layer_pieces=pz)
rc = sim_cut.run()
ok_cut = rc.layers_delivered >= 1 and rc.bytes_delivered in ends
check(ok_cut, f"con un budget di 4 minuti su un canale debole il mittente si ferma a un confine di livello: {rc.layers_delivered} livelli, {rc.bytes_delivered} byte")
if ok_cut and rc.layers_delivered < 3:
    parz = il.decodifica(il.prefisso(d, ends, rc.layers_delivered))
    check(parz.size == ref.size and il.psnr(parz, ref) < 99.0, f"i {rc.bytes_delivered} byte consegnati si decodificano in una immagine utile (PSNR {il.psnr(parz, ref):.1f} dB)")
print("immagine a livelli: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
