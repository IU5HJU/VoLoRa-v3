#!/usr/bin/env python3
"""Mette in un foglio PNG le schermate scritte da firmware/v3/build/test_oled_real (PBM P1, 128x64): il disegno ESATTO della libreria Adafruit_GFX 2.0.0.
Uso:  python3 tools/pbm_to_sheet.py cartella-pbm uscita.png nome1 nome2 ...     (nome = parte del nome del file, per esempio B-riposo B-invio menu)
"""
import glob
import os
import sys

from PIL import Image, ImageDraw


def load(path):
    rows = [ln.strip() for ln in open(path) if ln.strip()][2:]
    im = Image.new("RGB", (128 * 3, 64 * 3), (8, 12, 20))
    d = ImageDraw.Draw(im)
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            if c == "1":
                d.rectangle([x * 3, y * 3, x * 3 + 2, y * 3 + 2], fill=(120, 200, 255))
    return im


def main():
    folder, out, names = sys.argv[1], sys.argv[2], sys.argv[3:]
    files = []
    for n in names:
        m = sorted(glob.glob(os.path.join(folder, "*-%s.pbm" % n)))
        if not m:
            raise SystemExit("manca %s" % n)
        files.append((n, m[0]))
    cols = 3
    rows = (len(files) + cols - 1) // cols
    pad = 10
    sheet = Image.new("RGB", (cols * (384 + pad) + pad, rows * (192 + 18 + pad) + pad), (30, 34, 44))
    d = ImageDraw.Draw(sheet)
    for i, (n, f) in enumerate(files):
        x, y = pad + (i % cols) * (384 + pad), pad + (i // cols) * (192 + 18 + pad)
        d.text((x, y), n, fill=(255, 255, 255))
        sheet.paste(load(f), (x, y + 16))
    sheet.save(out)
    print("scritto", out, sheet.size)


main()
