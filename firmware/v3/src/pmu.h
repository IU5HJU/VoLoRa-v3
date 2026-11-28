// Alimentazione della T-Beam V1.2 (AXP2101), e Vext/reset OLED della Heltec V3: la radio e' sul canale ALDO2 e senza questa sequenza non si accende.
// Sequenza ripresa dalla v2 (VoLoRa v0.1.0-rc.1, src/pmu.cpp), a sua volta dal codice di riferimento LILYGO. Sulla T3 non c'e' PMU: non fa niente.
#pragma once
#include <Arduino.h>

#include "board.h"

#if defined(BOARD_TBEAM_V12)
#include <Wire.h>
#include <XPowersLib.h>

inline XPowersLibInterface*& pmuPtr() { static XPowersLibInterface* p = nullptr; return p; }
// tensione della batteria in mV, -1 se assente o PMU non disponibile
inline int pmuBatteryMv() { XPowersLibInterface* p = pmuPtr(); return (p && p->isBatteryConnect()) ? static_cast<int>(p->getBattVoltage()) : -1; }

// alimentazione del GPS (ALDO3), come la v2 (src/pmu.cpp: setGpsPower)
inline void pmuGpsPower(bool on) {
  XPowersLibInterface* p = pmuPtr();
  if (!p) return;
  if (on) { p->setPowerChannelVoltage(XPOWERS_ALDO3, 3300); p->enablePowerOutput(XPOWERS_ALDO3); }
  else p->disablePowerOutput(XPOWERS_ALDO3);
  Serial.printf("[pmu] GPS ALDO3 %s\n", p->isPowerChannelEnable(XPOWERS_ALDO3) ? "acceso" : "spento");
}

inline bool pmuBegin() {
  Wire.begin(pins::kOledSda, pins::kOledScl);
  XPowersLibInterface* pmu = pmuPtr() = new XPowersAXP2101(Wire, pins::kOledSda, pins::kOledScl);
  if (!pmu->init()) {
    Serial.println("[pmu] AXP2101 non risponde: la radio potrebbe non essere alimentata");
    return false;
  }
  pmu->setProtectedChannel(XPOWERS_DCDC1);     // alimentazione dell'ESP32: mai da spegnere
  pmu->disablePowerOutput(XPOWERS_DCDC2);
  pmu->disablePowerOutput(XPOWERS_DCDC3);
  pmu->disablePowerOutput(XPOWERS_DCDC4);
  pmu->disablePowerOutput(XPOWERS_DCDC5);
  pmu->disablePowerOutput(XPOWERS_ALDO1);
  pmu->disablePowerOutput(XPOWERS_ALDO4);
  pmu->disablePowerOutput(XPOWERS_BLDO1);
  pmu->disablePowerOutput(XPOWERS_BLDO2);
  pmu->disablePowerOutput(XPOWERS_DLDO1);
  pmu->disablePowerOutput(XPOWERS_DLDO2);
  pmu->disablePowerOutput(XPOWERS_CPULDO);
  pmu->setPowerChannelVoltage(XPOWERS_ALDO2, 3300);   // radio LoRa
  pmu->enablePowerOutput(XPOWERS_ALDO2);
  pmu->disablePowerOutput(XPOWERS_ALDO3);             // GPS spento
  delay(100);                                         // la radio ha bisogno di qualche istante prima di begin()
  Serial.printf("[pmu] AXP2101 ok, radio ALDO2 %u mV %s\n", static_cast<unsigned>(pmu->getPowerChannelVoltage(XPOWERS_ALDO2)),
                pmu->isPowerChannelEnable(XPOWERS_ALDO2) ? "acceso" : "SPENTO");
  return true;
}
#elif defined(BOARD_HELTEC_V3)
// Heltec V3: niente PMU. Vext (GPIO36, attivo BASSO) alimenta l'OLED; l'OLED ha il suo reset (GPIO21), da tenere basso per un istante.
inline bool pmuBegin() {
  pinMode(pins::kVext, OUTPUT);
  digitalWrite(pins::kVext, LOW);
  pinMode(pins::kOledRst, OUTPUT);
  digitalWrite(pins::kOledRst, LOW);
  delay(20);
  digitalWrite(pins::kOledRst, HIGH);
  delay(20);
  Serial.println("[avvio] Vext acceso (GPIO36 basso), reset dell'OLED fatto");
  return true;
}
inline int pmuBatteryMv() { return -1; }
inline void pmuGpsPower(bool) {}
#else
inline bool pmuBegin() { return true; }
inline int pmuBatteryMv() { return -1; }
inline void pmuGpsPower(bool) {}
#endif
