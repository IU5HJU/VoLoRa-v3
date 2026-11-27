// Disegno delle schermate (display_model.h) con la sola API di Adafruit_GFX: stesse coordinate, stessi font e stessa barra di avanzamento della v2 (src/ui.cpp).
// Separato dal pilota dell'SSD1306 (display_oled.h) perche' cosi' gira anche sul PC contro la libreria VERA (Adafruit_GFX 2.0.0, GFXcanvas1): tests/test_oled_real.cpp.
// Non cancella lo schermo e non chiama display(): lo fa chi lo usa. STUDIO: mai visto su un OLED vero.
#pragma once
#include <Adafruit_GFX.h>

#include <cstring>

#include "display_model.h"

namespace v3 {
namespace disp {

constexpr uint16_t kOn = 1, kOff = 0;          // SSD1306_WHITE e SSD1306_BLACK

// Riga grande (testo 2: 12 px per carattere, 10 caratteri): se e' piu' lunga scende al testo piccolo, senza andare a capo (come bigText della v2)
inline void bigText(Adafruit_GFX& d, int y, const char* text, bool fits) {
  d.setTextSize(fits ? 2 : 1);
  d.setCursor(0, fits ? y : y + 4);
  d.print(text);
}

inline void drawBadge(Adafruit_GFX& d, char b) {
  const char* const* g = glyph(b);
  for (int y = 0; y < 9; y++) for (int x = 0; x < 10; x++) if (g[y][x] == 'X') d.drawPixel(118 + x, y, kOn);
}

// ultima riga: testo a sinistra e batteria a destra (in negativo se e' scarica, come la v2)
inline void drawBottom(Adafruit_GFX& d, const Screen& s) {
  d.setTextSize(1);
  d.setCursor(0, 56);
  d.print(s.left);
  const int len = static_cast<int>(std::strlen(s.batt));
  const int x = 128 - len * 6;
  if (s.lowBatt) { d.fillRect(x - 1, 55, 128 - x + 1, 9, kOn); d.setTextColor(kOff); }
  d.setCursor(x, 56);
  d.print(s.batt);
  d.setTextColor(kOn);
}

inline void drawScreen(Adafruit_GFX& d, const Screen& s) {
  d.setTextColor(kOn);
  d.setTextSize(1);
  if (s.kind == Kind::Message) {                          // avvio: nominativo, riga grande, riga in basso (showMessage della v2)
    d.setCursor(0, 0);
    d.println(s.head);
    bigText(d, 20, s.big, std::strlen(s.big) <= 10);
    d.setTextSize(1);
    d.setCursor(0, 52);
    d.println(s.footer);
    return;
  }
  d.setCursor(0, 0);
  d.print(s.head);
  if (s.badge) drawBadge(d, s.badge);                      // variante C: nessuna lettera in condizioni normali
  d.drawFastHLine(0, 10, 128, kOn);
  if (s.kind == Kind::Menu || s.kind == Kind::Info) {      // menu (come la v2: voce scelta in negativo) e informazioni
    d.setTextSize(1);
    for (int i = 0; i < 5; i++) {
      if (!s.rows[i][0]) continue;
      const int y = 12 + i * 9;
      const bool sel = i == s.rowSel;
      if (sel) { d.fillRect(0, y - 1, 128, 9, kOn); d.setTextColor(kOff); }
      d.setCursor(2, y);
      d.print(s.rows[i]);
      d.setTextColor(kOn);
    }
    if (s.footer[0]) { d.setCursor(0, 57); d.print(s.footer); }
    return;
  }
  if (s.kind == Kind::Pairing) {                           // come la schermata Wi-Fi della v2: il codice in carattere doppio e in grassetto
    d.setCursor(0, 13);
    d.print(s.l38);
    d.setTextSize(2);
    for (int dx = 0; dx < 2; dx++) { d.setCursor(dx, 24); d.print(s.code); }
    d.setTextSize(1);
    d.setCursor(0, 44);
    d.print(s.name);
    drawBottom(d, s);
    return;
  }
  bigText(d, 16, s.big, s.bigFits);
  d.setTextSize(1);
  d.setCursor(0, 38);
  d.print(s.l38);
  if (s.bar >= 0) {                                        // barra di avanzamento sulla riga 47 (come la v2)
    d.drawRect(0, 47, 128, 7, kOn);
    d.fillRect(2, 49, (124 * s.bar) / 100, 3, kOn);
  } else if (s.l47[0]) {
    d.setCursor(0, 47);
    d.print(s.l47);
  }
  drawBottom(d, s);
}

}  // namespace disp
}  // namespace v3
