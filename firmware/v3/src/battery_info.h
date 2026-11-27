// Indicazione della batteria sul display: testo, soglia di batteria scarica e medie delle letture. Porta di lib/voicecore/battery_info.{h,cpp} della v2
// (stesso formato "(Batt=4.12V)" del firmware LoRa APRS iGate di Guzman). Nucleo senza dipendenze dalla scheda, provato sul PC (tests/test_display.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdio>

namespace v3 {

constexpr float kLowBatteryVolts = 3.40f;          // sotto questa tensione la batteria e' scarica (il testo va in negativo)

inline size_t formatBatteryText(char* out, size_t cap, float volts) {
  if (!out || cap == 0) return 0;
  const int n = volts < 0.0f ? std::snprintf(out, cap, "(Batt=--)") : std::snprintf(out, cap, "(Batt=%.2fV)", static_cast<double>(volts));
  if (n < 0) { out[0] = 0; return 0; }
  return static_cast<size_t>(n) < cap ? static_cast<size_t>(n) : cap - 1;
}
inline bool isLowBattery(float volts) { return volts >= 0.0f && volts < kLowBatteryVolts; }

// Media lenta per la T3: con l'USB e senza batteria l'ADC legge la linea del caricatore, che oscilla (4,14-4,42 V). alpha per lettura (una ogni 50 ms): 0,02 = circa 2,5 s.
class BatterySmoother {
 public:
  explicit BatterySmoother(float alpha = 0.02f) : alpha_(alpha) {}
  float update(float volts) { if (!init_) { value_ = volts; init_ = true; } else value_ += (volts - value_) * alpha_; return value_; }
  float value() const { return value_; }
 private:
  float alpha_, value_ = 0.0f;
  bool init_ = false;
};
// Media mobile delle ultime 16 letture dell'ADC, senza bloccare il ciclo principale.
class AverageFilter {
 public:
  static constexpr size_t kWindow = 16;
  void add(float v) { buf_[next_] = v; next_ = (next_ + 1) % kWindow; if (count_ < kWindow) count_++; }
  float average() const { if (!count_) return 0.0f; float s = 0; for (size_t i = 0; i < count_; i++) s += buf_[i]; return s / static_cast<float>(count_); }
 private:
  float buf_[kWindow] = {0};
  size_t count_ = 0, next_ = 0;
};

}  // namespace v3
