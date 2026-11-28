// Pilota dell'OLED SSD1306 128x64: cerca il display, ridisegna solo se cambia qualcosa. Il disegno delle schermate (stesse coordinate, font e barra della v2, src/ui.cpp) e' in display_draw.h.
// T3 V1.6.1: OLED a bordo (SDA 21, SCL 22). Heltec V3: OLED a bordo (SDA 17, SCL 18), acceso da pmuBegin() (Vext). T-Beam: display esterno facoltativo. Si prova 0x3C e poi 0x3D come nella v2; se il display non c'e' tutto resta muto.
// Disegnare costa circa 25 ms (I2C): non piu' di 10 volte al secondo, e `DISPLAY 0` lo spegne (la radio si accorge dei pacchetti dopo il disegno, non durante). STUDIO: mai visto su un OLED vero.
#pragma once
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Arduino.h>
#include <Wire.h>

#include "board.h"
#include "display_draw.h"
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
  void draw(const v3::disp::Screen& s) {
    d_.clearDisplay();
    v3::disp::drawScreen(d_, s);                            // il disegno vero e proprio e' in display_draw.h (provato sul PC con la libreria Adafruit_GFX)
    d_.display();
  }

  Adafruit_SSD1306 d_{128, 64, &Wire, -1};
  bool ok_ = false, enabled_ = true, haveLast_ = false;
  uint32_t lastMs_ = 0;
  v3::disp::Screen last_;
};
