// Alimentazione della T-Beam V1.2 (AXP2101): la radio e' sul canale ALDO2 e senza questa sequenza non si accende.
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
#else
inline bool pmuBegin() { return true; }
inline int pmuBatteryMv() { return -1; }
#endif
