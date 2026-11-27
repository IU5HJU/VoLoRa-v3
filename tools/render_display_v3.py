#!/usr/bin/env python3
"""Mockup dell'OLED della scheda mobile V3: esempi di come affiancare gli elementi della v2 a quelli del V3 (docs/images/display-v3-esempi.png).

Usa lo stesso modello di Adafruit_GFX dello script della v2 (third_party/VoLoRa-v2/tools/render_display.py: font 5x7, coordinate, ritorno a capo).
E' UN MOCKUP disegnato a mano con le coordinate di src/ui.cpp della v2: non e' una foto di uno schermo. Il font e' quello di Adafruit_GFX (identico nelle versioni 1.2.9 e 2.0.0).
Per il disegno ESATTO della libreria vera (Adafruit_GFX 2.0.0) vedi firmware/v3/tests/test_oled_real.cpp (make -C firmware/v3 oled-real), che scrive le schermate come PBM.
Uso:  python3 tools/render_display_v3.py PERCORSO/glcdfont.c [uscita.png]
"""
import importlib.util
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("v2render", os.path.join(HERE, "..", "third_party", "VoLoRa-v2", "tools", "render_display.py"))
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)

BADGES = dict(v2.BADGES)
BADGES["V"] = ["XX......XX", "XX......XX", "XX......XX", "XXX....XXX", ".XX....XX.", ".XXX..XXX.", "..XX..XX..", "...XXXX...", "....XX...."]
BADGES["B"] = ["XXXXXXXX..", "XXXXXXXXX.", "XX.....XXX", "XXXXXXXXX.", "XXXXXXXX..", "XX.....XXX", "XX.....XXX", "XXXXXXXXX.", "XXXXXXXX.."]
BADGES["I"] = ["XXXXXXXXXX", "XXXXXXXXXX", "....XX....", "....XX....", "....XX....", "....XX....", "....XX....", "XXXXXXXXXX", "XXXXXXXXXX"]
CALL, FREQ = "IU5HJU", "433.700"


def head(o, badge):
    o.set_size(1); o.set_cursor(0, 0); o.write(f"{CALL} {FREQ}MHz")
    if badge:
        for y, row in enumerate(BADGES[badge]):
            for x, ch in enumerate(row):
                if ch == "X":
                    o.px[y][118 + x] = True
    o.hline(0, 10, 128)


def batt(o, text="(Batt=4.12V)"):
    x = 128 - len(text) * 6
    o.set_size(1); o.set_cursor(x, 56); o.write(text)


def body(o, big, l38, l47, bar=None):
    v2.big_text(o, 16, big)
    o.set_size(1); o.set_cursor(0, 38); o.write(l38)
    if bar is not None:
        o.draw_rect(0, 47, 128, 7)
        o.fill_rect(2, 49, (124 * bar) // 100, 3)
    elif l47:
        o.set_cursor(0, 47); o.write(l47)


# stati: idle, invio 40%, ricezione
STATES = {
    "a riposo": ("ASCOLTO", "Telefono collegato", "Pos JN53ab", None),
    "invio 40%": ("INVIO", "Invio immagine 40%", "", 40),
    "ricezione": ("RX IZ5FSN", "Ricevo messaggio 63%", "125.8km  RSSI -97", None),
}


def variant_a(font, st):                       # come adesso: lettera V/B/I e R/potenza al posto di Vol
    o = v2.Oled(font); head(o, "V"); body(o, *STATES[st])
    o.set_size(1); o.set_cursor(0, 56); o.write("R10 17dBm"); batt(o)
    return o


def variant_b(font, st):                       # v2 intatta (lettera S, Vol) e il V3 sulla riga libera
    big, l38, l47, bar = STATES[st]
    o = v2.Oled(font); head(o, "S")
    if st == "a riposo":
        l47 = "R10 17dBm  Pos JN53ab"
    elif st == "invio 40%":
        l47 = None
    body(o, big, l38, l47, bar)
    if st == "invio 40%":                      # con la barra la riga 47 e' occupata: il V3 va nella riga di mezzo
        pass
    o.set_size(1); o.set_cursor(0, 56); o.write("Vol 7/10"); batt(o)
    return o


def variant_c(font, st):                       # lettera solo se il livello e' a rischio, rung e potenza in basso, Vol tolto
    big, l38, l47, bar = STATES[st]
    o = v2.Oled(font); head(o, None); body(o, big, l38, l47, bar)
    o.set_size(1); o.set_cursor(0, 56); o.write("R10 17dBm"); batt(o)
    return o


def variant_c_boost(font):
    o = v2.Oled(font); head(o, "B"); body(o, *STATES["a riposo"])
    o.set_size(1); o.set_cursor(0, 56); o.write("R10 20dBm"); batt(o)
    return o


def to_image(o, scale=3):
    im = Image.new("RGB", (v2.W * scale, v2.H * scale), (8, 12, 20))
    d = ImageDraw.Draw(im)
    for y in range(v2.H):
        for x in range(v2.W):
            if o.px[y][x]:
                d.rectangle([x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1], fill=(120, 200, 255))
    return im


def main():
    font = v2.load_font(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "docs", "images", "display-v3-esempi.png")
    rows = [("A  come adesso: lettera V/B/I e R10 17dBm al posto di Vol", variant_a),
            ("B  v2 intatta (lettera S, Vol 7/10) e il V3 sulla riga libera", variant_b),
            ("C  senza lettera, R10 17dBm in basso (Vol tolto)", variant_c)]
    scale, pad, capH = 3, 12, 22
    w = 3 * (v2.W * scale + pad) + pad
    h = len(rows) * (v2.H * scale + capH + pad) + pad + (v2.H * scale + capH + pad)
    im = Image.new("RGB", (w, h), (30, 34, 44))
    d = ImageDraw.Draw(im)
    f = ImageFont.load_default()
    y = pad
    for title, fn in rows:
        d.text((pad, y), title, fill=(255, 255, 255), font=f)
        for i, st in enumerate(STATES):
            im.paste(to_image(fn(font, st), scale), (pad + i * (v2.W * scale + pad), y + capH))
        y += v2.H * scale + capH + pad
    d.text((pad, y), "con BOOST attivo (variante A): lettera B e 20 dBm; con IOF MODE: lettera I e 22 dBm", fill=(255, 255, 255), font=f)
    im.paste(to_image(variant_c_boost(font), scale), (pad, y + capH))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    im.save(out)
    print("scritto", out, im.size)


if __name__ == "__main__":
    main()
