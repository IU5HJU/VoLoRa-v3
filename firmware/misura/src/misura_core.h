// Logica del firmware di misura, senza dipendenze dalla scheda: gira anche sul PC (tests/test_core.cpp).
// Contiene: lettura dei comandi, tempo in aria LoRa, formato del pacchetto di prova, statistiche di ricezione.
#pragma once
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace misura {

// ---------- Parametri ----------
struct Params {
  bool fsk = false;
  float freqMhz = 433.475f;
  // LoRa
  float bwKhz = 250.0f;
  int sf = 7;
  int cr = 5;  // denominatore: 5 = 4/5 ... 8 = 4/8
  // FSK
  float kbps = 100.0f;
  float devKhz = 50.0f;
  float rxBwKhz = 234.3f;
  int shape = 0;  // 0 nessuno, 3 = 0,3, 5 = 0,5, 10 = 1,0
  // Comuni
  int powerDbm = 2;
  bool boost = false;  // modalita' BOOST attiva (+20 dBm): estrema, con rischio (vedi BoostGuard)
  int payload = 64;   // byte del pacchetto di prova
  int preamble = 8;   // simboli LoRa o byte FSK
};

constexpr int kMinPayload = 26;  // intestazione 18 + CRC32 4 + almeno 4 di riempimento
constexpr int kMaxPayload = 255;

// ---------- Tempo in aria LoRa (formula Semtech), in microsecondi ----------
inline uint32_t loraToaUs(int sf, float bwKhz, int cr, int payloadBytes, int preambleSyms, bool crcOn = true,
                          bool explicitHeader = true) {
  const double ts = std::pow(2.0, sf) / (bwKhz * 1000.0);  // secondi per simbolo
  const int de = ts > 0.016 ? 1 : 0;                      // ottimizzazione per basse velocita'
  const int h = explicitHeader ? 0 : 1;
  const double num = 8.0 * payloadBytes - 4.0 * sf + 28.0 + (crcOn ? 16.0 : 0.0) - 20.0 * h;
  double symbols = std::ceil(num / (4.0 * (sf - 2 * de))) * cr;
  if (symbols < 0) symbols = 0;
  symbols += 8.0;
  const double preFix = sf < 7 ? 6.25 : 4.25;  // SF5 e SF6: 2 simboli in piu' nel preambolo
  return static_cast<uint32_t>(((preambleSyms + preFix) * ts + symbols * ts) * 1e6 + 0.5);
}

// Tempo in aria FSK stimato (preambolo + sincronismo da 2 byte + lunghezza fissa + CRC da 2 byte), in microsecondi.
inline uint32_t fskToaUs(float kbps, int payloadBytes, int preambleBytes) {
  const double bits = 8.0 * (preambleBytes + 2 + payloadBytes + 2);
  return static_cast<uint32_t>(bits / (kbps * 1000.0) * 1e6 + 0.5);
}

// ---------- Comandi ----------
constexpr int kMaxTok = 8;
struct Tokens {
  char tok[kMaxTok][24];
  int n = 0;
};

inline void upper(char* s) {
  for (; *s; ++s)
    if (*s >= 'a' && *s <= 'z') *s = static_cast<char>(*s - 'a' + 'A');
}

// Divide una riga in parole (separate da spazi); la prima e le parole chiave vanno in maiuscolo, i numeri restano come sono.
inline Tokens tokenize(const char* line) {
  Tokens t;
  const char* p = line;
  while (*p && t.n < kMaxTok) {
    while (*p == ' ' || *p == '\t') ++p;
    if (!*p) break;
    int k = 0;
    while (*p && *p != ' ' && *p != '\t' && k < 23) t.tok[t.n][k++] = *p++;
    t.tok[t.n][k] = 0;
    while (*p && *p != ' ' && *p != '\t') ++p;  // parola troppo lunga: si scarta il resto
    t.n++;
  }
  for (int i = 0; i < t.n; i++) {
    const char c = t.tok[i][0];
    if (!((c >= '0' && c <= '9') || c == '-' || c == '.')) upper(t.tok[i]);
  }
  return t;
}

inline bool parseFloat(const char* s, float* out) {
  char* end = nullptr;
  const double v = std::strtod(s, &end);
  if (end == s || *end != 0 || std::isnan(v) || std::isinf(v)) return false;
  *out = static_cast<float>(v);
  return true;
}
inline bool parseInt(const char* s, int* out) {
  char* end = nullptr;
  const long v = std::strtol(s, &end, 10);
  if (end == s || *end != 0) return false;
  *out = static_cast<int>(v);
  return true;
}

// Frequenza ammessa: 430-440 MHz (decisione del progetto, docs/architettura.md).
inline bool freqOk(float mhz) { return mhz >= 430.0f && mhz <= 440.0f; }

// Valida un modo LoRa (limiti di docs/radio-limiti.md; l'SF5 esiste solo sull'SX1262: lo dice la radio all'avvio del modo).
inline bool loraValid(float bw, int sf, int cr) {
  const float ok[] = {7.8f, 10.4f, 15.6f, 20.8f, 31.25f, 41.7f, 62.5f, 125.0f, 250.0f, 500.0f};
  bool bwOk = false;
  for (float b : ok)
    if (std::fabs(bw - b) < 0.001f) bwOk = true;
  return bwOk && sf >= 5 && sf <= 12 && cr >= 5 && cr <= 8;
}

inline bool fskValid(float kbps, float dev, float rxbw) {
  return kbps >= 0.5f && kbps <= 300.0f && dev >= 0.6f && dev <= 200.0f && dev + kbps / 2.0f <= 250.0f && rxbw > 0.0f && rxbw <= 467.0f;
}

// ---------- Modalita' BOOST (+20 dBm), estrema ----------
// Vale per ogni profilo (LoRa, FSK). Rischio TECNICO, non normativo (docs/confronto-datasheet.md, docs/boost.md):
//  - SX1278: +20 dBm solo con ciclo di lavoro massimo 1% e VSWR 3:1 al connettore d'antenna (datasheet SX1276/77/78/79, Table 35); in continuo il limite e' +17 dBm;
//  - corrente in trasmissione 120 mA (SX1278) o 118 mA (SX1262 a +22 dBm): calore, alimentazione, batteria;
//  - ricevitori vicini saturati; armoniche e spurie piu' forti; MAI trasmettere senza antenna o con antenna non adatta.
constexpr int kBoostDbm = 20;
constexpr int kContinuousDbm = 17;       // SX1278: massimo in continuo (PA_BOOST)
constexpr uint32_t kBoostWindowMs = 100000UL;   // finestra su cui si misura il ciclo di lavoro
constexpr float kBoostDutyMaxPct = 1.0f;        // ciclo massimo a +20 dBm sull'SX1278
constexpr const char* kBoostWarning =
    "ATTENZIONE BOOST +20 dBm: modalita' ESTREMA, con RISCHIO per la radio e per la scheda. "
    "SX1278: massimo 1% di ciclo di lavoro (in continuo +17 dBm) e antenna adattata (VSWR max 3:1): mai senza antenna. "
    "Calore e corrente (circa 120 mA), batteria; ricevitori vicini saturati; armoniche e spurie piu' forti. "
    "Per attivare: BOOST ON RISCHIO";

// Ciclo di lavoro in trasmissione su una finestra scorrevole, a secchi da 1 s (nessuna memoria dinamica).
struct BoostGuard {
  static constexpr int kBuckets = 100;      // 100 secchi da 1 s = finestra di 100 s
  uint32_t usInBucket[kBuckets] = {0};
  uint32_t curSecond = 0;
  bool started = false;
  void advance(uint32_t nowMs) {
    const uint32_t sec = nowMs / 1000;
    if (!started) {
      started = true;
      curSecond = sec;
      return;
    }
    // azzera i secchi saltati
    uint32_t steps = sec - curSecond;
    if (steps > kBuckets) steps = kBuckets;
    for (uint32_t i = 1; i <= steps; i++) usInBucket[(curSecond + i) % kBuckets] = 0;
    curSecond = sec;
  }
  void addTx(uint32_t nowMs, uint32_t airUs) {
    advance(nowMs);
    usInBucket[curSecond % kBuckets] += airUs;
  }
  float dutyPct(uint32_t nowMs) {
    advance(nowMs);
    uint64_t sum = 0;
    for (int i = 0; i < kBuckets; i++) sum += usInBucket[i];
    return static_cast<float>(sum) / (static_cast<double>(kBuckets) * 1e6) * 100.0f;
  }
  bool overLimit(uint32_t nowMs) { return dutyPct(nowMs) > kBoostDutyMaxPct; }
};

// Potenza da applicare alla radio: con BOOST +20 dBm in ogni profilo, altrimenti quella scelta (mai oltre +17 dBm di default sull'SX1278 se non e' BOOST).
inline int effectivePowerDbm(const Params& p) { return p.boost ? kBoostDbm : p.powerDbm; }

// "BOOST ON RISCHIO" attiva, "BOOST OFF" spegne; senza la parola RISCHIO non si attiva (il comando deve dire che si e' capito).
enum class BoostCmd { Invalid, On, OffCmd, Status, NeedsAck };
inline BoostCmd parseBoost(const Tokens& t) {
  if (t.n < 2 || std::strcmp(t.tok[0], "BOOST")) return BoostCmd::Invalid;
  if (!std::strcmp(t.tok[1], "OFF") && t.n == 2) return BoostCmd::OffCmd;
  if (!std::strcmp(t.tok[1], "STATUS") && t.n == 2) return BoostCmd::Status;
  if (!std::strcmp(t.tok[1], "ON")) return (t.n == 3 && !std::strcmp(t.tok[2], "RISCHIO")) ? BoostCmd::On : BoostCmd::NeedsAck;
  return BoostCmd::Invalid;
}

// ---------- Pacchetto di prova ----------
// byte 0-3: "V3M1" | 4-7: numero di sequenza | 8-9: lunghezza totale | 10-17: nominativo (riempito con 0)
// 18..len-5: riempimento pseudocasuale deterministico (dal numero di sequenza) | len-4..len-1: CRC32 di tutto cio' che precede
constexpr int kHeader = 18;
constexpr uint8_t kMagic[4] = {'V', '3', 'M', '1'};

inline uint32_t crc32(const uint8_t* d, size_t n) {
  uint32_t c = 0xFFFFFFFFu;
  for (size_t i = 0; i < n; i++) {
    c ^= d[i];
    for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
  }
  return ~c;
}

inline uint32_t xorshift(uint32_t& s) {
  s ^= s << 13;
  s ^= s >> 17;
  s ^= s << 5;
  return s;
}

inline void fillPattern(uint8_t* d, size_t n, uint32_t seq) {
  uint32_t s = seq * 2654435761u + 0x9E3779B9u;
  if (s == 0) s = 1;
  for (size_t i = 0; i < n; i++) d[i] = static_cast<uint8_t>(xorshift(s) >> 11);
}

inline void put32(uint8_t* p, uint32_t v) {
  p[0] = static_cast<uint8_t>(v);
  p[1] = static_cast<uint8_t>(v >> 8);
  p[2] = static_cast<uint8_t>(v >> 16);
  p[3] = static_cast<uint8_t>(v >> 24);
}
inline uint32_t get32(const uint8_t* p) {
  return static_cast<uint32_t>(p[0]) | static_cast<uint32_t>(p[1]) << 8 | static_cast<uint32_t>(p[2]) << 16 | static_cast<uint32_t>(p[3]) << 24;
}

inline bool buildPacket(uint8_t* out, int len, uint32_t seq, const char* call) {
  if (len < kMinPayload || len > kMaxPayload) return false;
  std::memcpy(out, kMagic, 4);
  put32(out + 4, seq);
  out[8] = static_cast<uint8_t>(len & 0xFF);
  out[9] = static_cast<uint8_t>(len >> 8);
  std::memset(out + 10, 0, 8);
  for (int i = 0; i < 8 && call[i]; i++) out[10 + i] = static_cast<uint8_t>(call[i]);
  fillPattern(out + kHeader, static_cast<size_t>(len - kHeader - 4), seq);
  put32(out + len - 4, crc32(out, static_cast<size_t>(len - 4)));
  return true;
}

enum class PacketStatus { Ok, TooShort, BadMagic, BadLength, BadCrc };

struct Parsed {
  PacketStatus status = PacketStatus::TooShort;
  uint32_t seq = 0;
  int bitErrors = -1;  // bit diversi dal riempimento atteso (solo se intestazione riconoscibile), -1 = non misurabile
};

inline int popcount8(uint8_t v) {
  int c = 0;
  while (v) {
    c += v & 1;
    v >>= 1;
  }
  return c;
}

inline Parsed parsePacket(const uint8_t* d, int len) {
  Parsed r;
  if (len < kMinPayload) return r;
  if (std::memcmp(d, kMagic, 4) != 0) {
    r.status = PacketStatus::BadMagic;
    return r;
  }
  r.seq = get32(d + 4);
  const int declared = d[8] | (d[9] << 8);
  if (declared != len) {
    r.status = PacketStatus::BadLength;
    return r;
  }
  const bool crcOk = crc32(d, static_cast<size_t>(len - 4)) == get32(d + len - 4);
  uint8_t expect[kMaxPayload];
  fillPattern(expect, static_cast<size_t>(len - kHeader - 4), r.seq);
  int errs = 0;
  for (int i = 0; i < len - kHeader - 4; i++) errs += popcount8(static_cast<uint8_t>(d[kHeader + i] ^ expect[i]));
  r.bitErrors = errs;
  r.status = crcOk ? PacketStatus::Ok : PacketStatus::BadCrc;
  return r;
}

// ---------- Statistiche di ricezione ----------
struct Stats {
  uint32_t rxOk = 0;        // pacchetti con CRC32 giusto
  uint32_t rxBad = 0;       // pacchetti ricevuti ma rovinati (CRC radio o CRC32 sbagliato, lunghezza, intestazione)
  uint32_t dup = 0;
  uint32_t bitErrors = 0;
  bool haveSeq = false;
  uint32_t firstSeq = 0, maxSeq = 0;
  uint32_t seen = 0;        // numeri di sequenza distinti visti correttamente
  double sumRssi = 0, sumSnr = 0, sumFei = 0;
  uint32_t nRssi = 0, nSnr = 0, nFei = 0;
  uint32_t lastSeq = 0;

  void add(const Parsed& p, bool radioCrcError, float rssi, float snr, float feiHz) {
    const bool good = p.status == PacketStatus::Ok && !radioCrcError;
    if (good) {
      rxOk++;
      if (!haveSeq) {
        haveSeq = true;
        firstSeq = maxSeq = p.seq;
        seen = 1;
      } else if (p.seq == lastSeq) {
        dup++;
      } else if (p.seq > maxSeq) {
        maxSeq = p.seq;
        seen++;
      } else if (p.seq >= firstSeq) {
        seen++;  // arrivato in ritardo (fuori ordine)
      } else {
        dup++;
      }
      lastSeq = p.seq;
    } else {
      rxBad++;
      if (p.bitErrors > 0) bitErrors += static_cast<uint32_t>(p.bitErrors);
    }
    if (!std::isnan(rssi)) { sumRssi += rssi; nRssi++; }
    if (!std::isnan(snr)) { sumSnr += snr; nSnr++; }
    if (!std::isnan(feiHz)) { sumFei += feiHz; nFei++; }
  }

  // Pacchetti persi tra il primo e l'ultimo visto (non si conosce quanti ne sono partiti oltre l'ultimo: lo dice chi trasmette).
  uint32_t lost() const { return haveSeq ? (maxSeq - firstSeq + 1) - (seen > (maxSeq - firstSeq + 1) ? (maxSeq - firstSeq + 1) : seen) : 0; }
  double meanRssi() const { return nRssi ? sumRssi / nRssi : NAN; }
  double meanSnr() const { return nSnr ? sumSnr / nSnr : NAN; }
  double meanFei() const { return nFei ? sumFei / nFei : NAN; }
};

inline int formatSummary(char* out, size_t cap, const Stats& s) {
  return std::snprintf(out, cap, "RXSUM ok=%u bad=%u lost=%u dup=%u bit_err=%u first=%u last=%u rssi=%.1f snr=%.1f fei_hz=%.0f", s.rxOk, s.rxBad,
                       s.lost(), s.dup, s.bitErrors, s.haveSeq ? s.firstSeq : 0u, s.haveSeq ? s.maxSeq : 0u, s.meanRssi(), s.meanSnr(),
                       s.meanFei());
}

}  // namespace misura
