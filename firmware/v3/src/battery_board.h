// Tensione della batteria da mostrare sul display (come la v2, src/battery.cpp), lettura NON bloccante.
//  - T-Beam V1.2: dal chip AXP2101 (-1 se la batteria non c'e'), ogni 2 s.
//  - T3 V1.6.1: ADC su GPIO35 con partitore 100k/100k, calibrazione del chip, media di 16 letture (una ogni 50 ms) e media lenta (2,5 s) perche' con l'USB e senza batteria
//    si legge la linea del caricatore, che oscilla. STUDIO: mai provato su una scheda.
#pragma once
#include <Arduino.h>

#include "battery_info.h"
#include "board.h"
#include "pmu.h"

class BatteryReader {
 public:
  void begin() {
#if !defined(BOARD_TBEAM_V12)
    pinMode(pins::kBatteryAdc, INPUT);
    analogSetPinAttenuation(pins::kBatteryAdc, ADC_11db);       // fino a circa 3,1 V sul pin = 6,2 V di batteria
    for (int i = 0; i < 16; i++) { filter_.add(static_cast<float>(analogReadMilliVolts(pins::kBatteryAdc))); delay(3); }
    volts_ = smoother_.update(filter_.average() * 2.0f / 1000.0f);
#endif
  }
  void update(uint32_t nowMs) {
#if defined(BOARD_TBEAM_V12)
    if (nowMs - lastMs_ < 2000 && lastMs_ != 0) return;
    lastMs_ = nowMs ? nowMs : 1;
    const int mv = pmuBatteryMv();
    volts_ = mv < 0 ? -1.0f : static_cast<float>(mv) / 1000.0f;
#else
    if (nowMs - lastMs_ < 50) return;
    lastMs_ = nowMs;
    filter_.add(static_cast<float>(analogReadMilliVolts(pins::kBatteryAdc)));
    volts_ = smoother_.update(filter_.average() * 2.0f / 1000.0f);
#endif
  }
  float volts() const { return volts_; }

 private:
  float volts_ = -1.0f;
  uint32_t lastMs_ = 0;
  v3::AverageFilter filter_;
  v3::BatterySmoother smoother_;
};
