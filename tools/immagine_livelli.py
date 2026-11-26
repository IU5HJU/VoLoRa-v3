#!/usr/bin/env python3
"""Immagine a livelli per il protocollo V3 (decisione del 26/11/2026: JPEG PROGRESSIVO preparato sul PC o sul telefono).
Una immagine JPEG progressiva e' una sequenza di *scansioni*: le prime danno l'immagine a bassa qualita', le altre la rifiniscono. Si raggruppano in tre LIVELLI
(OFFER del protocollo immagini: `layer_ends`); un ricevitore che ha solo i primi livelli aggiunge la fine del file (EOI) e decodifica una immagine meno dettagliata ma utile.
Qui sta la parte da PC (Pillow/libjpeg). La parte da telefono (browser) non c'e' ancora: la canvas non scrive JPEG progressivi (docs/immagine-livelli.md).
Provato sul PC: tests/sim/test_immagine_livelli.py. Uso:
  python3 tools/immagine_livelli.py foto.png --max-bytes 10000 -o foto.jpg"""
import argparse
import io
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocollo_immagini as pi  # noqa: E402

EOI = b"\xff\xd9"
PIECE = pi.PIECE
SIDES = (320, 256, 192, 160, 128, 96, 64, 48, 32)       # lati massimi provati, dal piu' grande
QUALITIES = (85, 75, 65, 55, 45, 35, 25, 15)


def scansioni(data):
    """Le scansioni di un JPEG: [{'ncomp', 'ss', 'se', 'ah', 'al', 'end'}] con `end` = offset del primo byte dopo i dati della scansione. Un JPEG normale (baseline) ne ha una."""
    if data[:2] != b"\xff\xd8":
        raise ValueError("non e' un JPEG")
    i, out = 2, []
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            raise ValueError("JPEG rovinato")
        m = data[i + 1]
        if m == 0xD9:
            break
        ln = int.from_bytes(data[i + 2:i + 4], "big")
        if m == 0xDA:
            hdr = data[i + 4:i + 2 + ln]
            n = hdr[0]
            ss, se, a = hdr[1 + 2 * n], hdr[2 + 2 * n], hdr[3 + 2 * n]
            j = i + 2 + ln
            while True:
                k = data.find(b"\xff", j)
                if k < 0 or k + 1 >= len(data):
                    raise ValueError("JPEG troncato")
                if data[k + 1] == 0 or 0xD0 <= data[k + 1] <= 0xD7:
                    j = k + 2
                    continue
                break
            out.append(dict(ncomp=n, ss=ss, se=se, ah=a >> 4, al=a & 15, end=k))
            i = k
        else:
            i += 2 + ln
    return out


def e_progressivo(data):
    return any(m in (b"\xff\xc2", b"\xff\xc6", b"\xff\xca", b"\xff\xce") for m in (data[k:k + 2] for k in range(2, min(len(data), 700))))


def livelli(data):
    """Fine di ogni livello, in byte (offset): tre livelli per un JPEG progressivo di libjpeg.
      1: la scansione DC e le prime 5 componenti di luminanza (immagine a bassa risoluzione e senza dettagli)
      2: fino alla rifinitura di luminanza a meta' precisione (colore e dettaglio medio)
      3: tutto
    Per un JPEG che non e' progressivo il livello e' uno solo (l'oggetto intero)."""
    sc = scansioni(data)
    if len(sc) < 4:
        return [len(data)]
    l1 = next((k for k, s in enumerate(sc) if s["ncomp"] == 1 and s["ss"] == 1 and s["se"] == 5), None)
    l2 = max((k for k, s in enumerate(sc) if s["ah"] == 2 and s["al"] == 1), default=None)
    if l1 is None or l2 is None or not l1 < l2 < len(sc) - 1:
        # forma di script non riconosciuta: si scelgono le scansioni piu' vicine a un terzo e a due terzi dei byte
        tot = len(data)
        ends = [s["end"] for s in sc]
        l1 = min(range(len(sc) - 2), key=lambda k: abs(ends[k] - tot / 3))
        l2 = min(range(l1 + 1, len(sc) - 1), key=lambda k: abs(ends[k] - 2 * tot / 3))
    return [sc[l1]["end"], sc[l2]["end"], len(data)]


def allinea(data, ends, piece=PIECE):
    """Fa cadere la fine di ogni livello su un confine di pezzo. Il protocollo lavora a pezzi (16 byte): senza questo il ricevitore che ha n livelli avrebbe qualche byte della
    scansione successiva dopo il confine, e il file troncato potrebbe finire dentro l'intestazione di una scansione. Si inserisce un segmento COM (commento JPEG, ignorato
    da ogni decodificatore) dopo l'ultima scansione del livello: al massimo 19 byte per livello. Ritorna (dati, fine dei livelli: tutte multiple del pezzo salvo l'ultima)."""
    out, new_ends, shift = bytearray(data), [], 0
    for e in ends[:-1]:
        pos = e + shift
        pad = (-pos) % piece
        if pad:
            n = pad if pad >= 4 else pad + piece          # un COM occupa almeno 4 byte (marcatore 2 + lunghezza 2)
            out[pos:pos] = b"\xff\xfe" + (n - 2).to_bytes(2, "big") + bytes(n - 4)
            shift += n
        new_ends.append(pos + (n if pad else 0))
    new_ends.append(len(out))
    return bytes(out), new_ends


def prefisso(data, ends, n):
    """I primi n livelli come JPEG valido (prefisso + EOI): e' quello che un ricevitore con solo n livelli decodifica."""
    if not 1 <= n <= len(ends):
        raise ValueError("livelli da 1 a %d" % len(ends))
    return data if n == len(ends) else data[:ends[n - 1]] + EOI


def pezzi(ends, piece=PIECE):
    """`layer_ends` dell'OFFER del protocollo immagini: indice (a partire da 1) del pezzo che chiude ogni livello. Il confine puo' cadere dentro un pezzo: il livello
    si chiude al pezzo che contiene la sua ultima scansione."""
    return [max(1, math.ceil(e / piece)) for e in ends]


def codifica(img, max_bytes, max_side=SIDES[0], gray=False):
    """Immagine (PIL) -> {'data', 'ends', 'width', 'height', 'quality'}: il JPEG progressivo piu' grande e di migliore qualita' che sta in max_bytes. None se non ci sta."""
    from PIL import Image  # noqa: F401
    base = img.convert("L" if gray else "RGB")
    for side in [s for s in SIDES if s <= max_side]:
        sc = min(1.0, side / max(base.size))
        im = base if sc == 1.0 else base.resize((max(1, round(base.width * sc)), max(1, round(base.height * sc))), Image.LANCZOS)
        for q in QUALITIES:
            b = io.BytesIO()
            im.save(b, "JPEG", quality=q, progressive=True, optimize=True)
            d = b.getvalue()
            d, ends = allinea(d, livelli(d))
            if len(d) <= max_bytes:
                return dict(data=d, ends=ends, width=im.width, height=im.height, quality=q)
    return None


def psnr(a, b):
    """PSNR in dB fra due immagini PIL della stessa dimensione."""
    import numpy as np
    x, y = np.asarray(a.convert("RGB"), dtype=float), np.asarray(b.convert("RGB"), dtype=float)
    mse = float(((x - y) ** 2).mean())
    return 99.0 if mse == 0 else 10 * math.log10(255.0 ** 2 / mse)


def decodifica(data):
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def tempi(ends, rung, chip="SX1278"):
    """Tempo stimato (s) per consegnare i primi 1, 2, 3 livelli al gradino `rung` (stessa stima del protocollo: protocollo_immagini.estimate_seconds)."""
    return [pi.estimate_seconds(e, rung, chip) for e in ends]


def livelli_nel_budget(ends, rung, budget_s=600.0, chip="SX1278"):
    """Quanti livelli entrano nel budget di tempo (di base 10 minuti) al gradino dato, come decide il mittente (docs/protocollo-immagini.md: si ferma a un confine di livello)."""
    return sum(1 for t in tempi(ends, rung, chip) if t <= budget_s)


def main():
    from PIL import Image
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("immagine")
    ap.add_argument("--max-bytes", type=int, default=10000)
    ap.add_argument("--max-side", type=int, default=SIDES[0])
    ap.add_argument("--gray", action="store_true", help="bianco e nero: meno byte")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    r = codifica(Image.open(a.immagine), a.max_bytes, a.max_side, a.gray)
    if r is None:
        sys.exit("non entra in %d byte: alzare il limite" % a.max_bytes)
    d, ends = r["data"], r["ends"]
    print(f"{r['width']}x{r['height']}, qualita' {r['quality']}, {len(d)} byte, {len(ends)} livelli, pezzi da {PIECE} byte: {pezzi(ends)}")
    ref = decodifica(d)
    for n in range(1, len(ends) + 1):
        p = prefisso(d, ends, n)
        print(f"  livello {n}: {len(p):6d} byte ({100 * len(p) / len(d):3.0f}%), PSNR {psnr(decodifica(p), ref):5.1f} dB, "
              + ", ".join(f"R{r_}: {pi.fmt_time(pi.estimate_seconds(ends[n - 1], r_))}" for r_ in (4, 5, 8, 10)))
    if a.out:
        open(a.out, "wb").write(d)
        print("scritto", a.out)


if __name__ == "__main__":
    main()
