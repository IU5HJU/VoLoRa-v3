// Disegno delle schermate (display_model.h) sull'OLED SSD1306 128x64: stesse coordinate, stessi font e stessa barra di avanzamento della v2 (src/ui.cpp).
// T3 V1.6.1: OLED a bordo (SDA 21, SCL 22). T-Beam: display esterno facoltativo. Si prova 0x3C e poi 0x3D come nella v2; se il display non c'e' tutto resta muto.
// Disegnare costa circa 25 ms (I2C): non piu' di 10 volte al secondo, e `DISPLAY 0` lo spegne (la radio si accorge dei pacchetti dopo il disegno, non durante). STUDIO: mai visto su un OLED vero.
#pragma once
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Arduino.h>
#include <Wire.h>

#include "board.h"
#include "display_model.h"

class OledDisplay {
 public:
  bool begin() {
    Wire.begin(pins::kOledSda, pins::kOledScl);
    const uint8_t addrs[2] = {0x3C, 0x3D};
    for (uint8_t a : addrs) {
      ok_ = d_.begin(SSD1306_SWITCHCAPVCC, a);
      if (ok_) { Serial.printf("[avvio] display OLED trovato all'indirizzo 0x%02X\n", a); break; }
    }
    if (!ok_) Serial.println("[avvio] display OLED non trovato (normale sulla T-Beam senza display)");
    else { d_.setTextColor(SSD1306_WHITE); d_.clearDisplay(); d_.display(); }
    return ok_;
  }
  bool present() const { return ok_; }
  void enable(bool on) { enabled_ = on; if (on) last_ = v3::disp::Screen(), haveLast_ = false; }
  bool enabled() const { return enabled_; }

  // Ridisegna solo se la schermata e' cambiata (o a 4 Hz con `periodic`, per i tempi e le barre) e non piu' di 10 volte al secondo.
  void show(const v3::disp::Screen& s, uint32_t nowMs, bool periodic) {
    if (!ok_ || !enabled_) return;
    const bool changed = !haveLast_ || !(s == last_);
    if (!changed && !(periodic && nowMs - lastMs_ >= 250)) return;
    if (nowMs - lastMs_ < 100) return;
    last_ = s; haveLast_ = true; lastMs_ = nowMs;
    draw(s);
  }
  // La schermata di avvio (bloccante come in v2)
  void showNow(const v3::disp::Screen& s) { if (!ok_ || !enabled_) return; draw(s); }

 private:
  // Riga grande (testo 2: 12 px per carattere, 10 caratteri): se e' piu' lunga scende al testo piccolo, senza andare a capo (come bigText della v2)
  void bigText(int y, const char* text, bool fits) {
    d_.setTextSize(fits ? 2 : 1);
    d_.setCursor(0, fits ? y : y + 4);
    d_.print(text);
  }
  void badge(char b) {
    const char* const* g = v3::disp::glyph(b);
    for (int y = 0; y < 9; y++) for (int x = 0; x < 10; x++) if (g[y][x] == 'X') d_.drawPixel(118 + x, y, SSD1306_WHITE);
  }
  void drawBottom(const v3::disp::Screen& s) {
    d_.setTextSize(1);
    d_.setCursor(0, 56);
    d_.print(s.left);
    const int len = static_cast<int>(strlen(s.batt));
    const int x = 128 - len * 6;
    if (s.lowBatt) { d_.fillRect(x - 1, 55, 128 - x + 1, 9, SSD1306_WHITE); d_.setTextColor(SSD1306_BLACK); }   // batteria scarica: in negativo, come la v2
    d_.setCursor(x, 56);
    d_.print(s.batt);
    d_.setTextColor(SSD1306_WHITE);
  }
  void draw(const v3::disp::Screen& s) {
    d_.clearDisplay();
    d_.setTextColor(SSD1306_WHITE);
    d_.setTextSize(1);
    if (s.kind == v3::disp::Kind::Message) {              // avvio: nominativo, riga grande, riga in basso (showMessage della v2)
      d_.setCursor(0, 0);
      d_.println(s.head);
      bigText(20, s.big, strlen(s.big) <= 10);
      d_.setTextSize(1);
      d_.setCursor(0, 52);
      d_.println(s.footer);
      d_.display();
      return;
    }
    d_.setCursor(0, 0);
    d_.print(s.head);
    if (s.badge) badge(s.badge);                            // variante C: nessuna lettera in condizioni normali
    d_.drawFastHLine(0, 10, 128, SSD1306_WHITE);
    if (s.kind == v3::disp::Kind::Menu || s.kind == v3::disp::Kind::Info) {          // menu (come la v2: voce scelta in negativo) e informazioni
      d_.setTextSize(1);
      for (int i = 0; i < 5; i++) {
        if (!s.rows[i][0]) continue;
        const int y = 12 + i * 9;
        const bool sel = i == s.rowSel;
        if (sel) { d_.fillRect(0, y - 1, 128, 9, SSD1306_WHITE); d_.setTextColor(SSD1306_BLACK); }
        d_.setCursor(2, y);
        d_.print(s.rows[i]);
        d_.setTextColor(SSD1306_WHITE);
      }
      if (s.footer[0]) { d_.setCursor(0, 57); d_.print(s.footer); }
      d_.display();
      return;
    }
    if (s.kind == v3::disp::Kind::Pairing) {              // come la schermata Wi-Fi della v2: il codice in carattere doppio e in grassetto
      d_.setCursor(0, 13);
      d_.print(s.l38);
      d_.setTextSize(2);
      for (int dx = 0; dx < 2; dx++) { d_.setCursor(dx, 24); d_.print(s.code); }
      d_.setTextSize(1);
      d_.setCursor(0, 44);
      d_.print(s.name);
      drawBottom(s);
      d_.display();
      return;
    }
    bigText(16, s.big, s.bigFits);
    d_.setTextSize(1);
    d_.setCursor(0, 38);
    d_.print(s.l38);
    if (s.bar >= 0) {                                      // barra di avanzamento sulla riga 47 (come la v2)
      d_.drawRect(0, 47, 128, 7, SSD1306_WHITE);
      d_.fillRect(2, 49, (124 * s.bar) / 100, 3, SSD1306_WHITE);
    } else if (s.l47[0]) {
      d_.setCursor(0, 47);
      d_.print(s.l47);
    }
    drawBottom(s);
    d_.display();
  }

  Adafruit_SSD1306 d_{128, 64, &Wire, -1};
  bool ok_ = false, enabled_ = true, haveLast_ = false;
  uint32_t lastMs_ = 0;
  v3::disp::Screen last_;
};
