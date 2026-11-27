// GPS della T-Beam V1.2 (u-blox, 9600 baud, frasi NMEA una al secondo): porta di src/gps.{h,cpp} della v2. L'interprete NMEA e' in nmea.h (provato sul PC);
// qui ci sono la seriale e l'alimentazione (ALDO3 del PMU). Sulla T3 non c'e' il GPS e tutto e' neutro. Spento di base come nella v2: si accende con `GPS ON`.
// STUDIO: mai provato su una scheda.
#pragma once
#include <Arduino.h>

#include "board.h"
#include "nmea.h"
#include "pmu.h"

class GpsBoard {
 public:
  // Accende il GPS (solo se la scheda lo ha) e apre la seriale. Con enabled=false lo spegne.
  void begin(bool enabled) {
#if defined(BOARD_TBEAM_V12)
    if (!enabled) { if (active_) { pmuGpsPower(false); Serial1.end(); } active_ = false; return; }
    if (active_) return;
    pmuGpsPower(true);
    Serial1.setRxBufferSize(2048);                              // come la v2: durante un invio il loop non legge e il GPS manda circa 500 byte al secondo
    Serial1.begin(9600, SERIAL_8N1, pins::kGpsRx, pins::kGpsTx);  // il TX va indicato (il predefinito della UART1 e' la memoria flash)
    active_ = true;
    lastLogMs_ = millis();
    Serial.printf("[gps] acceso: seriale a 9600 baud su GPIO%d, in attesa dei satelliti\n", pins::kGpsRx);
#else
    (void)enabled;
#endif
  }
  // Da chiamare spesso: legge i caratteri e scrive lo stato sulla seriale ogni 10 s (come la v2)
  void loop(uint32_t nowMs) {
#if defined(BOARD_TBEAM_V12)
    if (!active_) return;
    while (Serial1.available() > 0) {
      const char c = static_cast<char>(Serial1.read());
      charsRead_++;
      if (parser_.feed(c) && parser_.fix().valid) { lastFixMs_ = nowMs; everFixed_ = true; }
    }
    const bool fix = hasFix(nowMs);
    if (fix != lastHadFix_) {
      lastHadFix_ = fix;
      if (fix) Serial.printf("[gps] FIX: %.5f, %.5f, %u satelliti\n", parser_.fix().latE7 / 1e7, parser_.fix().lonE7 / 1e7, static_cast<unsigned>(parser_.fix().sats));
      else Serial.println("[gps] fix perso: si usa la posizione del telefono");
      lastLogMs_ = nowMs;
    }
    if (nowMs - lastLogMs_ >= 10000) {
      lastLogMs_ = nowMs;
      if (fix) Serial.printf("[gps] fix %.5f, %.5f, %u satelliti\n", parser_.fix().latE7 / 1e7, parser_.fix().lonE7 / 1e7, static_cast<unsigned>(parser_.fix().sats));
      else if (charsRead_ == 0) Serial.println("[gps] nessun dato dalla seriale: controlla l'alimentazione del GPS (ALDO3) e il cavo");
      else Serial.printf("[gps] nessun fix (satelliti %u, frasi lette %u, errori %u): serve il cielo aperto, il primo fix puo' richiedere alcuni minuti\n",
                         static_cast<unsigned>(parser_.fix().sats), static_cast<unsigned>(parser_.sentences()), static_cast<unsigned>(parser_.checksumErrors()));
    }
#else
    (void)nowMs;
#endif
  }
  bool present() const {
#if defined(BOARD_TBEAM_V12)
    return true;
#else
    return false;
#endif
  }
  bool active() const { return active_; }
  bool hasFix(uint32_t nowMs) const { return active_ && everFixed_ && parser_.fix().valid && static_cast<int32_t>(nowMs - lastFixMs_) <= static_cast<int32_t>(v3::kGpsMaxAgeMs); }
  uint8_t satellites() const { return parser_.fix().sats; }
  int32_t latE7() const { return parser_.fix().latE7; }
  int32_t lonE7() const { return parser_.fix().lonE7; }

 private:
  bool active_ = false, everFixed_ = false, lastHadFix_ = false;
  v3::NmeaParser parser_;
  uint32_t lastFixMs_ = 0, lastLogMs_ = 0, charsRead_ = 0;
};
