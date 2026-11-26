// Modalita' BOOST (+20 dBm) per il firmware V3: ESTREMA, con rischio (docs/boost.md). Nucleo senza dipendenze dalla scheda, provato sul PC (tests/test_boost.cpp).
// Rischio TECNICO, non normativo: vale docs/regole-radioamatoriali.md. Di base si trasmette a +17 dBm (massimo in continuo dell'SX1278); il BOOST e' sempre spento all'avvio e non si salva.
// Si attiva solo con "BOOST ON RISCHIO". Il nodo NON spegne il BOOST da solo (decisione del 26/11/2026: solo avviso).
// Stessa logica e stessi testi di firmware/misura/src/misura_core.h; sull'SX1278 il ciclo di lavoro e' controllato (1% su 100 s, Table 35 del datasheet), sull'SX1262 +20 dBm e' sotto il suo massimo (+22 dBm) e resta l'avviso su calore e corrente.
#pragma once
#include <cctype>
#include <cstdint>
#include <cstring>

namespace v3 {
namespace boost {

constexpr int kNormalDbm = 17;                    // massimo in continuo dell'SX1278 (PA_BOOST)
constexpr int kBoostDbm = 20;
constexpr uint32_t kWindowMs = 100000UL;          // finestra su cui si misura il ciclo di lavoro
constexpr float kDutyMaxPct = 1.0f;               // ciclo massimo a +20 dBm sull'SX1278
constexpr uint32_t kWarnEveryMs = 5000;
constexpr float kOcpMa = 140.0f;                  // limite di corrente da dare alla radio a +20 dBm (circa 120 mA in trasmissione)
constexpr const char* kWarning =
    "ATTENZIONE BOOST +20 dBm: modalita' ESTREMA, con RISCHIO per la radio e per la scheda. "
    "SX1278: massimo 1% di ciclo di lavoro (in continuo +17 dBm) e antenna adattata (VSWR max 3:1): mai senza antenna. "
    "Calore e corrente (circa 120 mA), batteria; ricevitori vicini saturati; armoniche e spurie piu' forti. "
    "Per attivare: BOOST ON RISCHIO";

enum class Cmd { Invalid, On, Off, Status, NeedsAck };

// "BOOST ON RISCHIO" | "BOOST OFF" | "BOOST STATUS" (maiuscole o minuscole, spazi qualunque). "BOOST ON" da solo non attiva: serve la parola RISCHIO.
inline Cmd parse(const char* line) {
  char tok[4][12];
  int n = 0;
  const char* p = line;
  while (*p) {
    while (*p == ' ' || *p == '\t') p++;
    if (!*p) break;
    if (n == 4) return Cmd::Invalid;
    int k = 0;
    while (*p && *p != ' ' && *p != '\t') { if (k < 11) tok[n][k++] = static_cast<char>(std::toupper(static_cast<unsigned char>(*p))); p++; }
    tok[n][k] = 0;
    n++;
  }
  if (n < 2 || std::strcmp(tok[0], "BOOST")) return Cmd::Invalid;
  if (!std::strcmp(tok[1], "OFF") && n == 2) return Cmd::Off;
  if (!std::strcmp(tok[1], "STATUS") && n == 2) return Cmd::Status;
  if (!std::strcmp(tok[1], "ON")) return (n == 3 && !std::strcmp(tok[2], "RISCHIO")) ? Cmd::On : Cmd::NeedsAck;
  return Cmd::Invalid;
}

// Ciclo di lavoro in trasmissione su una finestra scorrevole, a secchi da 1 s (nessuna memoria dinamica).
struct DutyGuard {
  static constexpr int kBuckets = 100;
  uint32_t usInBucket[kBuckets] = {0};
  uint32_t curSecond = 0;
  bool started = false;
  void advance(uint32_t nowMs) {
    const uint32_t sec = nowMs / 1000;
    if (!started) { started = true; curSecond = sec; return; }
    uint32_t steps = sec - curSecond;
    if (steps > kBuckets) steps = kBuckets;
    for (uint32_t i = 1; i <= steps; i++) usInBucket[(curSecond + i) % kBuckets] = 0;
    curSecond = sec;
  }
  void addTx(uint32_t nowMs, uint32_t airUs) { advance(nowMs); usInBucket[curSecond % kBuckets] += airUs; }
  float dutyPct(uint32_t nowMs) {
    advance(nowMs);
    uint64_t sum = 0;
    for (int i = 0; i < kBuckets; i++) sum += usInBucket[i];
    return static_cast<float>(static_cast<double>(sum) / (static_cast<double>(kBuckets) * 1e6) * 100.0);
  }
};

// Stato del BOOST di una scheda. La radio chiede power() a ogni configurazione e dice quando trasmette (txStarted).
class State {
 public:
  explicit State(bool sx1262) : sx1262_(sx1262) {}
  bool on() const { return on_; }
  int power() const { return on_ ? kBoostDbm : kNormalDbm; }
  void enable() { on_ = true; guard_ = DutyGuard(); lastWarn_ = 0; warned_ = false; }
  void disable() { on_ = false; }
  float duty(uint32_t nowMs) { return guard_.dutyPct(nowMs); }
  // una trasmissione parte: in BOOST sull'SX1278 conta nel ciclo di lavoro. Ritorna true se bisogna stampare l'avviso (sopra l'1%, al massimo ogni 5 s). Non spegne niente.
  bool txStarted(uint32_t nowMs, uint32_t airUs) {
    if (!on_) return false;
    guard_.addTx(nowMs, airUs);
    if (sx1262_) return false;
    if (guard_.dutyPct(nowMs) <= kDutyMaxPct) return false;
    if (warned_ && nowMs - lastWarn_ < kWarnEveryMs) return false;
    warned_ = true; lastWarn_ = nowMs;
    return true;
  }

 private:
  bool sx1262_, on_ = false, warned_ = false;
  uint32_t lastWarn_ = 0;
  DutyGuard guard_;
};

}  // namespace boost
}  // namespace v3
