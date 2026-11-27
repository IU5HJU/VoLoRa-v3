// Ponte telefono <-> scheda (specifica docs/ble-telefono.md): NUCLEO del firmware mobile, senza dipendenze dalla scheda e senza memoria dinamica.
// Porta in C++ di tools/ble_bridge.py (BleBridge); provata contro il riferimento Python con vettori identici byte per byte (tests/test_conformance.cpp).
// Il BUFFER e' il telefono: la scheda tiene al massimo CACHE_BLOCKS blocchi da 1 kB e li chiede a richiesta (E_PULL). Niente microSD sulle schede mobili.
// STUDIO: non e' stato mai eseguito su una scheda.
#pragma once
#include <cmath>
#include <cstdint>
#include <cstring>

#include "estimate.h"

namespace v3 {
namespace ble {

constexpr uint8_t kVersion = 1;
constexpr uint8_t kKindText = 0, kKindFile = 1, kKindImage = 2;
// comandi (telefono -> scheda)
constexpr uint8_t C_HELLO = 0x01, C_POSITION = 0x02, C_BEGIN = 0x10, C_CANCEL = 0x12, C_RESUME = 0x13, C_RX_ACK = 0x14;
// eventi (scheda -> telefono)
constexpr uint8_t E_INFO = 0x80, E_BEGIN_OK = 0x81, E_ERR = 0x82, E_PROGRESS = 0x85, E_DONE = 0x86, E_RX = 0x87, E_PULL = 0x89, E_DIAG = 0x8A;   // E_DIAG: solo ponte collegato alla radio (live_bridge.h), riepilogo di fine invio
constexpr uint8_t ERR_BUSY = 1, ERR_TOO_BIG = 2, ERR_NO_POSITION = 4, ERR_BAD_FRAME = 5, ERR_BAD_KIND = 7, ERR_UNKNOWN_OBJ = 8, ERR_NO_CALL = 9;
constexpr uint8_t DONE_DELIVERED = 0, DONE_FAILED = 1, DONE_CANCELLED = 2;
constexpr uint32_t kBlock = 1024;
constexpr int kCacheBlocks = 3;
constexpr uint32_t kMaxText = 1024, kMaxObject = 65536;
constexpr double kStallTimeoutS = 60.0;
constexpr int kRetxDelay = 4;
constexpr int kDataHdr = 5;
constexpr int kMaxLayers = 8;
constexpr int kMaxSeq = 192;
constexpr int kMaxNameBytes = 40;

// Dove escono le notifiche e dove va l'oggetto. Nel firmware vero: notifiche BLE e radio.
struct Sink {
  virtual ~Sink() {}
  virtual void evt(const uint8_t* d, size_t n) = 0;                                              // notifica sulla caratteristica `evt`
  virtual void radioBlock(uint16_t obj, uint16_t blk, const uint8_t* d, size_t n, bool again) { (void)obj; (void)blk; (void)d; (void)n; (void)again; }   // un blocco parte in radio
  virtual void rxObject(uint16_t obj, const uint8_t* d, size_t n) { (void)obj; (void)d; (void)n; }                                              // oggetto dalla radio da passare al telefono
};

typedef double (*EstimateFn)(uint32_t size, int rung, bool sx1262, void* ctx);

struct Stats {
  uint32_t badFrames = 0, dropped = 0, maxHeld = 0, pulls = 0, repulls = 0, blocksSent = 0;
  double stalledS = 0.0;
};

namespace detail {
inline bool utf8Valid(const uint8_t* s, size_t n) {
  size_t i = 0;
  while (i < n) {
    const uint8_t c = s[i];
    size_t len;
    uint32_t cp;
    if (c < 0x80) { i++; continue; }
    if ((c & 0xE0) == 0xC0) { len = 2; cp = c & 0x1F; }
    else if ((c & 0xF0) == 0xE0) { len = 3; cp = c & 0x0F; }
    else if ((c & 0xF8) == 0xF0) { len = 4; cp = c & 0x07; }
    else return false;
    if (i + len > n) return false;
    for (size_t k = 1; k < len; k++) {
      if ((s[i + k] & 0xC0) != 0x80) return false;
      cp = (cp << 6) | (s[i + k] & 0x3F);
    }
    if ((len == 2 && cp < 0x80) || (len == 3 && cp < 0x800) || (len == 4 && cp < 0x10000) || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) return false;
    i += len;
  }
  return true;
}
inline bool ascii(const uint8_t* s, size_t n) {
  for (size_t i = 0; i < n; i++) if (s[i] >= 0x80) return false;
  return true;
}
inline uint32_t rd(const uint8_t* b, int n) { uint32_t v = 0; for (int i = 0; i < n; i++) v = (v << 8) | b[i]; return v; }
inline void wr(uint8_t* b, uint32_t v, int n) { for (int i = n - 1; i >= 0; i--) { b[i] = v & 255; v >>= 8; } }
inline int popcount64(uint64_t x) { int c = 0; while (x) { c += x & 1; x >>= 1; } return c; }
}  // namespace detail

class Bridge {
 public:
  Bridge(Sink* sink, const char* call, bool sx1262, int rung, uint16_t rungMask) : sink_(sink), sx1262_(sx1262), rung_(rung), rungMask_(rungMask) {
    setCall(call);
    est_ = defaultEstimate;
  }
  void setCall(const char* c) { strncpy(call_, c ? c : "", sizeof(call_) - 1); call_[sizeof(call_) - 1] = 0; }
  void setPosition(const uint8_t raw[7]) { memcpy(pos_, raw, 7); havePos_ = true; }
  void setRadioOk(bool ok) { radioOk_ = ok; }
  void setEstimate(EstimateFn f, void* ctx) { est_ = f; ctx_ = ctx; }
  void setRetxPlan(uint64_t mask) { retxPlan_ = mask; }     // blocchi da ritrasmettere una volta (prova della ritrasmissione selettiva)
  const Stats& stats() const { return st_; }
  bool connected() const { return connected_; }
  bool busy() const { return have_; }
  uint32_t held() const {
    if (!have_) return 0;
    uint32_t h = 0;
    for (int i = 0; i < kCacheBlocks; i++) if (s_.slot[i].blk >= 0) h += s_.slot[i].fill;
    return h;
  }

  void onDisconnect() {
    connected_ = false;
    if (have_) {
      for (int i = 0; i < kCacheBlocks; i++) if (s_.slot[i].blk >= 0 && !s_.slot[i].complete) s_.slot[i].blk = -1;   // un blocco a meta' si butta
      s_.asked = 0;
    }
  }
  void onConnect() { connected_ = true; }

  void onCommand(const uint8_t* b, size_t n) {
    bool ok = true;
    if (n == 0) ok = false;
    else {
      const uint8_t c = b[0];
      if (c == C_HELLO) {
        uint8_t o[32];
        const size_t cl = strlen(call_);
        o[0] = E_INFO; o[1] = kVersion; o[2] = sx1262_ ? 1 : 0;
        detail::wr(o + 3, rungMask_, 2); detail::wr(o + 5, kBlock, 3); detail::wr(o + 8, kMaxObject, 3);
        o[11] = havePos_ ? 1 : 0; o[12] = static_cast<uint8_t>(cl);
        memcpy(o + 13, call_, cl);
        notify(o, 13 + cl);
      } else if (c == C_POSITION) {
        if (n != 8 || (b[1] != 0 && b[1] != 1) || (b[1] == 0 && !detail::ascii(b + 2, 6))) ok = false;     // tipo 0 locatore (6 caratteri ASCII), tipo 1 GPS
        else setPosition(b + 1);
      } else if (c == C_BEGIN) {
        ok = begin(b, n);
      } else if (c == C_CANCEL || c == C_RESUME || c == C_RX_ACK) {
        if (n != 3) ok = false;
        else {
          const uint16_t obj = static_cast<uint16_t>(detail::rd(b + 1, 2));
          if (c == C_CANCEL) cancel(obj); else if (c == C_RESUME) resume(obj); else rxAck(obj);
        }
      } else ok = false;
    }
    if (!ok) { st_.badFrames++; err(0, ERR_BAD_FRAME); }
  }

  void onData(const uint8_t* b, size_t n) {
    if (n <= static_cast<size_t>(kDataHdr)) { st_.badFrames++; return; }
    const uint16_t obj = static_cast<uint16_t>(detail::rd(b, 2));
    const uint32_t off = detail::rd(b + 2, 3);
    const uint8_t* pl = b + kDataHdr;
    const size_t pn = n - kDataHdr;
    if (!have_ || s_.obj != obj) return;
    const uint32_t k = off / kBlock;
    if (k >= 64 || !(s_.asked >> k & 1) || findComplete(k) >= 0 || k >= nblocks()) { st_.dropped++; return; }
    const uint32_t start = k * kBlock;
    const uint32_t ln = blockLen(k);
    int si = findSlot(k);
    if (si < 0) si = allocSlot(k);
    if (si < 0) { st_.dropped++; return; }
    Slot& sl = s_.slot[si];
    if (off != start + sl.fill || sl.fill + pn > ln) { st_.dropped++; return; }
    memcpy(sl.data + sl.fill, pl, pn);
    sl.fill = static_cast<uint16_t>(sl.fill + pn);
    if (sl.fill == ln) { sl.complete = true; s_.served |= 1ULL << k; }
    const uint32_t h = held();
    if (h > st_.maxHeld) st_.maxHeld = h;
  }

  // Avanza il tempo e la radio (modello a tempo: nel firmware vero la fine di ogni blocco la dice la radio).
  void tick(double dt) {
    t_ += dt;
    if (!have_) return;
    const uint32_t n = nblocks();
    if (s_.idx >= s_.seqLen) return;
    const uint8_t cur = s_.seq[s_.idx];
    const int ci = findComplete(cur);
    if (ci < 0) {
      s_.stall += dt;
      st_.stalledS += dt;
      if (s_.stall > kStallTimeoutS) {
        const uint16_t obj = s_.obj;
        have_ = false;
        done(obj, DONE_FAILED);
      }
      return;
    }
    s_.stall = 0.0;
    const uint32_t ln = blockLen(cur);
    const double bt = s_.dur * ln / s_.size;
    s_.inBlock += dt;
    if (s_.inBlock < bt) return;
    s_.inBlock = 0.0;
    const bool again = (s_.sent >> cur & 1) != 0;
    sink_->radioBlock(s_.obj, cur, s_.slot[ci].data, ln, again);
    s_.sent |= 1ULL << cur;
    st_.blocksSent++;
    s_.idx++;
    if (s_.retxLeft >> cur & 1) {              // la mappa del ricevitore dira' che manca: lo si rimanda dopo qualche blocco
      s_.retxLeft &= ~(1ULL << cur);
      insertRetx(cur);
    }
    if (s_.idx >= s_.seqLen) {
      const uint16_t obj = s_.obj;
      have_ = false;
      done(obj, radioOk_ ? DONE_DELIVERED : DONE_FAILED);
      return;
    }
    const int doneBlocks = detail::popcount64(s_.sent);
    int pct = static_cast<int>(100 * static_cast<double>(doneBlocks) / n);
    if (pct > 99) pct = 99;
    if (pct - s_.pct >= 10 && t_ - s_.lastProgress >= 2.0) {
      s_.pct = pct; s_.lastProgress = t_;
      uint8_t o[9];
      o[0] = E_PROGRESS; detail::wr(o + 1, s_.obj, 2); o[3] = static_cast<uint8_t>(pct); o[4] = static_cast<uint8_t>(rung_);
      detail::wr(o + 5, static_cast<uint32_t>(s_.dur * (100 - pct) / 100), 3);
      notify(o, 8);
    }
    prefetch();
  }

  // Oggetto arrivato dalla radio: accettato solo con il telefono collegato (la scheda non ha dove tenerlo). false = rifiutato.
  bool radioReceived(uint16_t obj, uint8_t kind, const uint8_t* d, size_t n, const char* from, uint32_t crc) {
    if (!connected_) return false;
    uint8_t o[32];
    const size_t fl = strlen(from) > 12 ? 12 : strlen(from);
    o[0] = E_RX; detail::wr(o + 1, obj, 2); o[3] = kind; detail::wr(o + 4, static_cast<uint32_t>(n), 3); detail::wr(o + 7, crc, 4); o[11] = static_cast<uint8_t>(fl);
    memcpy(o + 12, from, fl);
    notify(o, 12 + fl);
    if (rxN_ < 4) rx_[rxN_++] = obj;
    sink_->rxObject(obj, d, n);
    return true;
  }
  uint8_t layerCount() const { return have_ ? s_.nl : 0; }

 private:
  struct Slot { int16_t blk = -1; uint16_t fill = 0; bool complete = false; uint8_t data[kBlock]; };
  struct Session {
    uint16_t obj; uint8_t kind; uint32_t size, crc; uint16_t w, h; uint8_t nl; uint32_t layerEnds[kMaxLayers]; char dest[13]; uint8_t name[kMaxNameBytes + 1]; uint8_t nameLen;
    Slot slot[kCacheBlocks];
    uint64_t asked = 0, served = 0, sent = 0, retxLeft = 0;
    uint8_t seq[kMaxSeq]; int seqLen = 0, idx = 0;
    double inBlock = 0, dur = 0, lastProgress = 0, stall = 0;
    int pct = 0;
  };

  static double defaultEstimate(uint32_t size, int rung, bool sx1262, void*) { return estimateSeconds(size, rung, sx1262); }
  void notify(const uint8_t* d, size_t n) { if (connected_) sink_->evt(d, n); }
  void err(uint16_t obj, uint8_t code) { uint8_t o[4]; o[0] = E_ERR; detail::wr(o + 1, obj, 2); o[3] = code; notify(o, 4); }
  void done(uint16_t obj, uint8_t status) {
    int at = -1;
    for (int i = 0; i < lastN_; i++) if (last_[i].obj == obj) at = i;
    if (at >= 0) last_[at].status = status;
    else {
      if (lastN_ == 4) { for (int i = 1; i < 4; i++) last_[i - 1] = last_[i]; lastN_ = 3; }
      last_[lastN_].obj = obj; last_[lastN_].status = status; lastN_++;
    }
    uint8_t o[4]; o[0] = E_DONE; detail::wr(o + 1, obj, 2); o[3] = status; notify(o, 4);
  }
  uint32_t nblocks() const { return (s_.size + kBlock - 1) / kBlock; }
  uint32_t blockLen(uint32_t k) const { const uint32_t rest = s_.size - k * kBlock; return rest < kBlock ? rest : kBlock; }
  int findSlot(uint32_t k) const { for (int i = 0; i < kCacheBlocks; i++) if (s_.slot[i].blk == static_cast<int>(k)) return i; return -1; }
  int findComplete(uint32_t k) const { const int i = findSlot(k); return (i >= 0 && s_.slot[i].complete) ? i : -1; }
  int allocSlot(uint32_t k) { for (int i = 0; i < kCacheBlocks; i++) if (s_.slot[i].blk < 0) { s_.slot[i].blk = static_cast<int16_t>(k); s_.slot[i].fill = 0; s_.slot[i].complete = false; return i; } return -1; }
  void insertRetx(uint8_t blk) {
    if (s_.seqLen >= kMaxSeq) return;
    int pos = s_.idx + kRetxDelay;
    if (pos > s_.seqLen) pos = s_.seqLen;
    for (int i = s_.seqLen; i > pos; i--) s_.seq[i] = s_.seq[i - 1];
    s_.seq[pos] = blk;
    s_.seqLen++;
  }

  bool begin(const uint8_t* b, size_t n) {
    // obj(2) kind(1) size(3) crc(4) w(2) h(2) nl(1) ends(3*nl) destLen(1) dest nameLen(1) name: lunghezza esatta, dest ASCII, nome UTF-8 valido
    if (n < 16) return false;
    Session ns;
    ns.obj = static_cast<uint16_t>(detail::rd(b + 1, 2)); ns.kind = b[3]; ns.size = detail::rd(b + 4, 3); ns.crc = detail::rd(b + 7, 4);
    ns.w = static_cast<uint16_t>(detail::rd(b + 11, 2)); ns.h = static_cast<uint16_t>(detail::rd(b + 13, 2)); ns.nl = b[15];
    size_t p = 16 + 3 * static_cast<size_t>(ns.nl);
    if (p >= n) return false;
    for (int i = 0; i < ns.nl && i < kMaxLayers; i++) ns.layerEnds[i] = detail::rd(b + 16 + 3 * i, 3);
    const size_t dl = b[p];
    if (p + 1 + dl >= n) return false;
    if (!detail::ascii(b + p + 1, dl)) return false;
    p += 1 + dl;
    const size_t nm = b[p];
    if (n != p + 1 + nm) return false;
    if (!detail::utf8Valid(b + p + 1, nm)) return false;
    const size_t dk = dl > 12 ? 12 : dl;                         // il telefono ne manda al massimo 12; di piu' si tronca
    memcpy(ns.dest, b + 16 + 3 * static_cast<size_t>(ns.nl) + 1, dk); ns.dest[dk] = 0;
    ns.nameLen = static_cast<uint8_t>(nm > kMaxNameBytes ? kMaxNameBytes : nm); memcpy(ns.name, b + p + 1, ns.nameLen);
    // controlli di merito (come BleBridge._begin)
    if (call_[0] == 0) { err(ns.obj, ERR_NO_CALL); return true; }
    if (ns.kind != kKindText && ns.kind != kKindFile && ns.kind != kKindImage) { err(ns.obj, ERR_BAD_KIND); return true; }
    if (!havePos_) { err(ns.obj, ERR_NO_POSITION); return true; }
    if (ns.size == 0 || ns.size > kMaxObject || (ns.kind == kKindText && ns.size > kMaxText)) { err(ns.obj, ERR_TOO_BIG); return true; }
    if (have_) { err(ns.obj, ERR_BUSY); return true; }
    ns.dur = est_(ns.size, rung_, sx1262_, ctx_);
    const uint32_t nb = (ns.size + kBlock - 1) / kBlock;
    ns.seqLen = static_cast<int>(nb);
    for (uint32_t i = 0; i < nb; i++) ns.seq[i] = static_cast<uint8_t>(i);
    ns.retxLeft = nb >= 64 ? retxPlan_ : (retxPlan_ & ((1ULL << nb) - 1));
    ns.lastProgress = t_;
    s_ = ns;
    have_ = true;
    uint8_t o[9];
    o[0] = E_BEGIN_OK; detail::wr(o + 1, s_.obj, 2); detail::wr(o + 3, static_cast<uint32_t>(s_.dur + 0.5), 3); o[6] = static_cast<uint8_t>(rung_); detail::wr(o + 7, kBlock, 2);
    notify(o, 9);
    prefetch();
    return true;
  }

  void lookahead(uint8_t* out, int* n) const {
    *n = 0;
    for (int i = s_.idx; i < s_.seqLen && i < s_.idx + kCacheBlocks; i++) {
      bool dup = false;
      for (int j = 0; j < *n; j++) if (out[j] == s_.seq[i]) dup = true;
      if (!dup) out[(*n)++] = s_.seq[i];
    }
  }
  void prefetch() {
    if (!have_) return;
    uint8_t want[kCacheBlocks]; int wn;
    lookahead(want, &wn);
    for (int i = 0; i < kCacheBlocks; i++) {                  // si butta quello che non serve piu' (completo o a meta')
      if (s_.slot[i].blk < 0) continue;
      bool keep = false;
      for (int j = 0; j < wn; j++) if (want[j] == s_.slot[i].blk) keep = true;
      if (!keep) { s_.asked &= ~(1ULL << s_.slot[i].blk); s_.slot[i].blk = -1; s_.slot[i].fill = 0; s_.slot[i].complete = false; }
    }
    if (!connected_) return;
    for (int j = 0; j < wn; j++) {
      const uint32_t k = want[j];
      if (findComplete(k) < 0 && !(s_.asked >> k & 1)) {
        s_.asked |= 1ULL << k;
        st_.pulls++;
        if (s_.served >> k & 1) st_.repulls++;
        uint8_t o[8];
        o[0] = E_PULL; detail::wr(o + 1, s_.obj, 2); detail::wr(o + 3, k * kBlock, 3); detail::wr(o + 6, blockLen(k), 2);
        notify(o, 8);
      }
    }
  }
  void cancel(uint16_t obj) {
    if (!have_ || s_.obj != obj) { err(obj, ERR_UNKNOWN_OBJ); return; }
    have_ = false;
    done(obj, DONE_CANCELLED);
  }
  void resume(uint16_t obj) {
    int at = -1;
    for (int i = 0; i < lastN_; i++) if (last_[i].obj == obj) at = i;
    if (at >= 0 && (!have_ || s_.obj != obj)) { uint8_t o[4]; o[0] = E_DONE; detail::wr(o + 1, obj, 2); o[3] = last_[at].status; notify(o, 4); return; }
    if (!have_ || s_.obj != obj) { err(obj, ERR_UNKNOWN_OBJ); return; }
    s_.asked = 0;
    s_.stall = 0.0;
    prefetch();
  }
  void rxAck(uint16_t obj) {
    for (int i = 0; i < rxN_; i++) if (rx_[i] == obj) { for (int j = i + 1; j < rxN_; j++) rx_[j - 1] = rx_[j]; rxN_--; return; }
  }

  Sink* sink_;
  bool sx1262_;
  int rung_;
  uint16_t rungMask_;
  char call_[13] = {0};
  uint8_t pos_[7] = {0};
  bool havePos_ = false, radioOk_ = true, connected_ = true, have_ = false;
  uint64_t retxPlan_ = 0;
  Session s_;
  Stats st_;
  double t_ = 0.0;
  EstimateFn est_;
  void* ctx_ = nullptr;
  struct Last { uint16_t obj; uint8_t status; } last_[4];
  int lastN_ = 0;
  uint16_t rx_[4];
  int rxN_ = 0;
};

}  // namespace ble
}  // namespace v3
