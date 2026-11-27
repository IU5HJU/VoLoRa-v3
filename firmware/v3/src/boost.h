// Modalita' BOOST (+20 dBm) per il firmware V3: ESTREMA, con rischio (docs/boost.md). Nucleo senza dipendenze dalla scheda, provato sul PC (tests/test_boost.cpp).
// Rischio TECNICO, non normativo: vale docs/regole-radioamatoriali.md. Di base si trasmette a +17 dBm (massimo in continuo dell'SX1278); il BOOST e' sempre spento all'avvio e non si salva.
// Si attiva solo con "BOOST ON RISCHIO". Il nodo NON spegne il BOOST da solo (decisione del 26/11/2026: solo avviso).
// Stessa logica e stessi testi di firmware/misura/src/misura_core.h; sull'SX1278 il ciclo di lavoro e' controllato (1% su 100 s, Table 35 del datasheet), sull'SX1262 +20 dBm e' sotto il suo massimo (+22 dBm) e resta l'avviso su calore e corrente.
#pragma once
#include <cctype>
#include <cstdint>
#include <cstring>
#include <strings.h>

namespace v3 {
namespace boost {

constexpr int kNormalDbm = 17;                    // massimo in continuo dell'SX1278 (PA_BOOST); e' anche la potenza di partenza
constexpr int kMinDbmSx1278 = 2, kMinDbmSx1262 = -9;   // minimo del chip con l'uscita PA_BOOST (SX1278) o HP (SX1262): sotto non si scende
constexpr int kBoostDbm = 20;
constexpr int kIofDbm = 22;                       // IOF MODE: solo SX1262, il suo massimo
constexpr uint32_t kWindowMs = 100000UL;          // finestra su cui si misura il ciclo di lavoro
constexpr float kDutyMaxPct = 1.0f;               // ciclo massimo a +20 dBm sull'SX1278
constexpr uint32_t kWarnEveryMs = 5000;
constexpr float kOcpMa = 140.0f;                  // limite di corrente da dare alla radio a +20 dBm (circa 120 mA in trasmissione)
constexpr const char* kWarning =
    "ATTENZIONE BOOST +20 dBm: modalita' ESTREMA, con RISCHIO per la radio e per la scheda. "
    "SX1278: massimo 1% di ciclo di lavoro (in continuo +17 dBm) e antenna adattata (VSWR max 3:1): mai senza antenna. "
    "Calore e corrente (circa 120 mA), batteria; ricevitori vicini saturati; armoniche e spurie piu' forti. "
    "Per attivare: BOOST ON RISCHIO";

// IOF MODE (solo SX1262): +22 dBm, il massimo del chip, un gradino sopra il BOOST. Dedicato a IZ5IOF Andrea (vedi docs/boost.md).
constexpr const char* kIofWarning =
    "IOF MODE: dedicato a IZ5IOF Andrea, che spreme tutto dalle sue apparecchiature per il collegamento impossibile. "
    "ATTENZIONE IOF MODE +22 dBm: il MASSIMO dell'SX1262, un gradino sopra il BOOST, con RISCHIO per la radio e per la scheda. "
    "Corrente al limite (circa 120-140 mA), calore, batteria sotto sforzo; ricevitori vicini saturati; armoniche e spurie piu' forti. "
    "Antenna adattata obbligatoria: mai senza antenna. Chi spreme tutto spesso guasta qualcosa: i danni sono a carico tuo. "
    "Per attivare: IOF ON RISCHIO";

enum class Cmd { Invalid, On, Off, Status, NeedsAck };
enum class Level { Normal, Boost, Iof };

// "BOOST ON RISCHIO" | "BOOST OFF" | "BOOST STATUS" (maiuscole o minuscole, spazi qualunque). "BOOST ON" da solo non attiva: serve la parola RISCHIO.
inline Cmd parseWord(const char* line, const char* word) {
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
  if (n < 2 || std::strcmp(tok[0], word)) return Cmd::Invalid;
  if (!std::strcmp(tok[1], "OFF") && n == 2) return Cmd::Off;
  if (!std::strcmp(tok[1], "STATUS") && n == 2) return Cmd::Status;
  if (!std::strcmp(tok[1], "ON")) return (n == 3 && !std::strcmp(tok[2], "RISCHIO")) ? Cmd::On : Cmd::NeedsAck;
  return Cmd::Invalid;
}

inline Cmd parse(const char* line) { return parseWord(line, "BOOST"); }

// "POWER" (mostra) | "POWER 5" | "POWER -3": potenza normale in dBm interi. Set con *dbm; Invalid se non e' un numero; NeedsAck = non e' un comando POWER (usato come "no").
enum class PowerCmd { NotPower, Invalid, Set, Show };
inline PowerCmd parsePower(const char* line, int* dbm) {
  const char* p = line;
  while (*p == ' ' || *p == '\t') p++;
  if (strncasecmp(p, "POWER", 5) != 0) return PowerCmd::NotPower;
  p += 5;
  if (*p && *p != ' ' && *p != '\t') return PowerCmd::NotPower;
  while (*p == ' ' || *p == '\t') p++;
  if (!*p) return PowerCmd::Show;
  bool neg = false;
  if (*p == '-' || *p == '+') { neg = *p == '-'; p++; }
  if (*p < '0' || *p > '9') return PowerCmd::Invalid;
  int v = 0;
  for (; *p >= '0' && *p <= '9'; p++) { v = v * 10 + (*p - '0'); if (v > 1000) return PowerCmd::Invalid; }
  while (*p == ' ' || *p == '\t') p++;
  if (*p) return PowerCmd::Invalid;
  *dbm = neg ? -v : v;
  return PowerCmd::Set;
}
inline Cmd parseIof(const char* line) { return parseWord(line, "IOF"); }

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

// Giro della potenza normale per la voce "Potenza" del menu: 17 -> 10 -> 5 -> 2 -> (T-Beam SX1262: -3 -> -9) -> 17. Si ferma al minimo del chip.
inline int nextBasePower(int current, int minDbm) {
  static const int steps[] = {17, 10, 5, 2, -3, -9};
  const size_t n = sizeof(steps) / sizeof(steps[0]);
  size_t i = 0;
  while (i < n && steps[i] != current) i++;
  for (size_t j = (i < n ? i + 1 : 1); j < n; j++) if (steps[j] >= minDbm) return steps[j];
  return steps[0];
}

// Stato della potenza estrema di una scheda: normale (+17), BOOST (+20) oppure IOF MODE (+22, solo SX1262). Uno solo alla volta. La radio chiede power() a ogni configurazione e dice quando trasmette.
class State {
 public:
  explicit State(bool sx1262) : sx1262_(sx1262) {}
  Level level() const { return level_; }
  bool on() const { return level_ != Level::Normal; }          // un livello estremo e' attivo
  bool boostOn() const { return level_ == Level::Boost; }
  bool iofOn() const { return level_ == Level::Iof; }
  int power() const { return level_ == Level::Iof ? kIofDbm : level_ == Level::Boost ? kBoostDbm : base_; }
  // Potenza normale (senza BOOST ne' IOF): da `minDbm()` a +17 dBm. Serve per le prove con attenuatori: l'ingresso del ricevitore non deve saturare.
  int base() const { return base_; }
  int minDbm() const { return sx1262_ ? kMinDbmSx1262 : kMinDbmSx1278; }
  bool setBase(int dbm) { if (dbm < minDbm() || dbm > kNormalDbm) return false; base_ = dbm; return true; }
  void enable() { setLevel(Level::Boost); }
  // IOF MODE: false (e niente cambia) se il chip non e' un SX1262
  bool enableIof() { if (!sx1262_) return false; setLevel(Level::Iof); return true; }
  void disable() { level_ = Level::Normal; }
  float duty(uint32_t nowMs) { return guard_.dutyPct(nowMs); }
  // una trasmissione parte: in un livello estremo conta nel ciclo di lavoro. Ritorna true se bisogna stampare l'avviso (SX1278 in BOOST, sopra l'1%, al massimo ogni 5 s). Non spegne niente.
  bool txStarted(uint32_t nowMs, uint32_t airUs) {
    if (!on()) return false;
    guard_.addTx(nowMs, airUs);
    if (sx1262_) return false;
    if (guard_.dutyPct(nowMs) <= kDutyMaxPct) return false;
    if (warned_ && nowMs - lastWarn_ < kWarnEveryMs) return false;
    warned_ = true; lastWarn_ = nowMs;
    return true;
  }

 private:
  void setLevel(Level l) { if (l != level_) { guard_ = DutyGuard(); lastWarn_ = 0; warned_ = false; } level_ = l; }
  bool sx1262_, warned_ = false;
  int base_ = kNormalDbm;
  Level level_ = Level::Normal;
  uint32_t lastWarn_ = 0;
  DutyGuard guard_;
};

}  // namespace boost
}  // namespace v3
