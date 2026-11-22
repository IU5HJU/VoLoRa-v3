// Schermata di stato sull'OLED SSD1306 128x64 (T3 V1.6.1: a bordo, SDA 21 / SCL 22, indirizzo 0x3C; sulla T-Beam e' un display esterno facoltativo).
// Si prova 0x3C e poi 0x3D come nella v2. Se il display non c'e' tutto resta muto e il firmware funziona uguale.
// Disegnare costa circa 25 ms: durante un RX a pacchetti ravvicinati si puo' perdere un pacchetto, per questo c'e' il comando DISPLAY 0.
#pragma once
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Arduino.h>
#include <Wire.h>

#include "board.h"
#include "misura_core.h"

struct ScreenState {
  enum Kind { Idle, Tx, Rx, Cw } kind = Idle;
  uint32_t done = 0, total = 0;       // TX: inviati / da inviare; RX: ricevuti buoni
  uint32_t bad = 0;                   // RX: ricevuti rovinati
  int secondsLeft = 0;                // RX e CW
  float rssi = NAN, snr = NAN;
  const char* chip = "";
  const char* call = "";
  bool ready = false;                 // radio configurata
  const misura::Params* p = nullptr;
};

class StatusDisplay {
 public:
  bool begin() {
    Wire.begin(pins::kOledSda, pins::kOledScl);
    const uint8_t addrs[2] = {0x3C, 0x3D};
    for (uint8_t a : addrs) {
      ok_ = d_.begin(SSD1306_SWITCHCAPVCC, a);
      if (ok_) {
        Serial.printf("[avvio] display OLED trovato all'indirizzo 0x%02X\n", a);
        break;
      }
    }
    if (!ok_) Serial.println("[avvio] display OLED non trovato (normale sulla T-Beam senza display)");
    if (ok_) {
      d_.setTextColor(SSD1306_WHITE);
      d_.clearDisplay();
      d_.display();
    }
    return ok_;
  }

  bool present() const { return ok_; }
  void enable(bool on) { enabled_ = on; }
  bool enabled() const { return enabled_; }

  // Ridisegna al massimo ogni `minGapMs` (0 = subito).
  void draw(const ScreenState& s, uint32_t minGapMs = 0) {
    if (!ok_ || !enabled_) return;
    const uint32_t now = millis();
    if (minGapMs && now - last_ < minGapMs) return;
    last_ = now;
    d_.clearDisplay();
    d_.setTextSize(1);
    char b[32];
    d_.setCursor(0, 0);
    snprintf(b, sizeof(b), "V3 misura %-9s", s.chip);
    d_.print(b);
    d_.drawFastHLine(0, 9, 128, SSD1306_WHITE);
    if (s.p) {
      d_.setCursor(0, 12);
      if (s.p->fsk) snprintf(b, sizeof(b), "FSK %gk d%g rx%g", s.p->kbps, s.p->devKhz, s.p->rxBwKhz);
      else snprintf(b, sizeof(b), "LoRa %gk SF%d 4/%d", s.p->bwKhz, s.p->sf, s.p->cr);
      d_.print(b);
      d_.setCursor(0, 21);
      snprintf(b, sizeof(b), "%.3fMHz %+ddBm", s.p->freqMhz, s.p->powerDbm);
      d_.print(b);
      d_.setCursor(0, 30);
      snprintf(b, sizeof(b), "pkt %dB pre %d", s.p->payload, s.p->preamble);
      d_.print(b);
    }
    d_.setCursor(0, 39);
    snprintf(b, sizeof(b), "call %s", s.call[0] ? s.call : "(manca CALL)");
    d_.print(b);
    d_.drawFastHLine(0, 48, 128, SSD1306_WHITE);
    d_.setCursor(0, 51);
    switch (s.kind) {
      case ScreenState::Idle:
        snprintf(b, sizeof(b), "%s", s.ready ? "pronta - HELP" : "radio NON pronta");
        d_.print(b);
        break;
      case ScreenState::Tx:
        snprintf(b, sizeof(b), "TX %lu/%lu", static_cast<unsigned long>(s.done), static_cast<unsigned long>(s.total));
        d_.print(b);
        break;
      case ScreenState::Rx:
        snprintf(b, sizeof(b), "RX ok%lu bad%lu %ds", static_cast<unsigned long>(s.done), static_cast<unsigned long>(s.bad), s.secondsLeft);
        d_.print(b);
        d_.setCursor(0, 57);
        if (!std::isnan(s.rssi)) {
          if (std::isnan(s.snr)) snprintf(b, sizeof(b), "RSSI %.0f", s.rssi);
          else snprintf(b, sizeof(b), "RSSI %.0f SNR %.1f", s.rssi, s.snr);
          d_.print(b);
        }
        break;
      case ScreenState::Cw:
        snprintf(b, sizeof(b), "PORTANTE %ds", s.secondsLeft);
        d_.print(b);
        break;
    }
    d_.display();
  }

 private:
  Adafruit_SSD1306 d_{128, 64, &Wire, -1};
  bool ok_ = false, enabled_ = true;
  uint32_t last_ = 0;
};
