// Limiti dei chip radio dai datasheet Semtech e maschera dei gradini che una stazione annuncia nell'HELLO (docs/confronto-datasheet.md).
// Porta di tools/limiti_chip.py (rung_support, rung_mask, common_mask); provata contro il riferimento Python (tests/test_limits.cpp con tests/vettori/limits.txt).
// STUDIO: valori dei datasheet, non misure.
#pragma once
#include <cstdint>

#include "estimate.h"

namespace v3 {

constexpr double kXtalPpm = 10.0;       // quarzo normale: errore di frequenza di ogni scheda (valore di lavoro, da misurare)
constexpr double kTcxoPpm = 2.0;        // con TCXO
constexpr double kDefaultKhz = 433700.0;

// campo di sintonia: SX1278 137-175 e 410-525 MHz; SX1262 150-960 MHz
inline bool inTuning(bool sx1262, double khz) {
  if (sx1262) return khz >= 150000 && khz <= 960000;
  return (khz >= 137000 && khz <= 175000) || (khz >= 410000 && khz <= 525000);
}
// bit rate FSK massimo: l'SX1262 lo scala con la frequenza (300 kb/s a 915 MHz): circa 142 kb/s a 433,7 MHz
inline double fskBrMaxKbps(bool sx1262, double khz) {
  if (!sx1262) return 300.0;
  const double s = 300.0 * khz / 915000.0;
  return s < 300.0 ? s : 300.0;
}
// errore di frequenza TOTALE ammesso fra trasmettitore e ricevitore senza perdita: il piu' stretto fra il 25% della banda e, per SF10-12, 200/100/50 ppm
inline double ppmBudget(double bwKhz, int sf, double khz) {
  double ppm = 0.25 * bwKhz / khz * 1e6;
  const double lim = sf == 10 ? 200.0 : sf == 11 ? 100.0 : sf == 12 ? 50.0 : 1e9;
  return ppm < lim ? ppm : lim;
}
inline bool bwAllowed(double bw) {
  static const double ok[] = {7.8, 10.4, 15.6, 20.8, 31.25, 41.7, 62.5, 125.0, 250.0, 500.0};
  for (double b : ok) if (b == bw) return true;
  return false;
}

// Il chip realizza il gradino a quella frequenza con quarzi da xtalPpm ciascuno?
inline bool rungSupported(int rung, bool sx1262, double khz, double xtalPpm) {
  const Rung& r = kRungs[rung];
  if (!inTuning(sx1262, khz)) return false;
  if (!r.lora) {
    const double br = r.a, fdev = r.b;
    if (!((sx1262 ? 0.6 : 1.2) <= br && br <= fskBrMaxKbps(sx1262, khz))) return false;
    if (!(0.6 <= fdev && fdev <= 200.0) || fdev + br / 2 > 250) return false;
    const double need = br + 2 * fdev + 2 * (2 * xtalPpm * khz / 1e6);          // banda del segnale piu' due volte l'errore di frequenza
    if (need > (sx1262 ? 467.0 : 500.0)) return false;
    if (sx1262 && 2 * fdev / br < 0.5) return false;                             // indice di modulazione minimo
    return true;
  }
  const double bw = r.a;
  const int sf = static_cast<int>(r.b);
  if (!bwAllowed(bw) || sf < (sx1262 ? 5 : 6) || sf > 12) return false;
  return !(2 * xtalPpm > ppmBudget(bw, sf, khz));
}

// Maschera a 16 bit dei gradini che la stazione puo' annunciare (decisioni del 26/11/2026): R0 solo SX1278, R12-R14 solo con TCXO.
inline uint16_t rungMask(bool sx1262, bool tcxo, double khz = kDefaultKhz) {
  uint16_t m = 0;
  for (int i = 0; i < kRungCount; i++) if (rungSupported(i, sx1262, khz, tcxo ? kTcxoPpm : kXtalPpm)) m |= static_cast<uint16_t>(1u << i);
  return m;
}
// Gradini che due stazioni possono usare insieme: AND delle maschere, senza R3 (LoRa 500/SF6) se i chip differiscono (l'SF6 non e' compatibile fra SX1278 e SX1262).
inline uint16_t commonMask(bool sx1262A, uint16_t maskA, bool sx1262B, uint16_t maskB) {
  uint16_t m = maskA & maskB;
  if (sx1262A != sx1262B) m &= static_cast<uint16_t>(~(1u << 3));
  return m;
}

}  // namespace v3
