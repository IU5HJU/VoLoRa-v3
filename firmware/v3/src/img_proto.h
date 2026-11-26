// Protocollo immagini V3 (docs/protocollo-immagini.md): collegamento, ricevitore e mittente, senza canale, senza orologio e senza memoria dinamica.
// Porta di tools/img_proto.py; provata contro le tracce che il simulatore Python registra (tests/test_protocol.cpp, tools/gen_tracce_protocollo.py).
// Il mittente e' un PROCESSO come in Python: a ogni ripresa riceve (ora, gradino, in ricerca, risposta) e restituisce l'azione che chiede al mezzo (radio e orologio del firmware, o il
// simulatore). Le procedure sono scritte come coroutine a macro (switch/__LINE__) per avere la stessa struttura dei generatori Python: la traduzione resta meccanica e verificabile.
// STUDIO: mai eseguito su una scheda.
#pragma once
#include <cmath>
#include <cstdint>
#include <cstring>

#include "estimate.h"
#include "frames.h"
#include "limits.h"

namespace v3 {
namespace img {

// ------------------------------------------------------------------------------------------------------------------------------------ costanti
constexpr double kGuardS = 0.15, kMarginUpDb = 6.0, kLossDown = 0.20, kLossUp = 0.02, kProbeOk = 0.9, kGiveUpS = 900.0;
constexpr int kWindowFrames = 16, kUpWindows = 3, kProbeCount = 8, kStatusRetries = 3, kProbeBytes = 32;
constexpr int kMaxWindow = 64, kMaxPieces = 4096, kMaxCalendar = 8;
constexpr uint8_t kScanOrder[kMaxCalendar] = {10, 11, 10, 12, 10, 13, 10, 14};

inline uint32_t crc32(const uint8_t* d, size_t n, uint32_t crc = 0) {
  crc = ~crc;
  for (size_t i = 0; i < n; i++) {
    crc ^= d[i];
    for (int k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
  }
  return ~crc;
}
inline int s8round(double v) { const long r = std::lrint(v); return r < -128 ? -128 : r > 127 ? 127 : static_cast<int>(r); }   // come int(round(v)) di Python (pari ai .5)

inline double scanDwellS(int rung) { const double a = 3.0 * (frameAirtimeS(rung, 25) + 2 * kGuardS); return a > 120.0 ? a : 120.0; }
inline double fallbackS(int rung) { const double a = 12.0 * frameAirtimeS(rung, kDataHeader + 2 * kPiece); return a > 30.0 ? a : 30.0; }
inline int scanRung(double elapsed, const uint8_t* order, int n) {
  double cycle = 0;
  for (int i = 0; i < n; i++) cycle += scanDwellS(order[i]);
  double e = std::fmod(elapsed, cycle);
  for (int i = 0; i < n; i++) {
    const double d = scanDwellS(order[i]);
    if (e < d) return order[i];
    e -= d;
  }
  return order[n - 1];
}
// calendario della ricerca ristretto ai gradini annunciati da entrambe le stazioni (se nessuno: solo R10)
inline int scanOrderFor(bool chipA, uint16_t maskA, bool chipB, uint16_t maskB, uint8_t* out) {
  const uint16_t m = commonMask(chipA, maskA, chipB, maskB);
  int n = 0;
  for (int i = 0; i < kMaxCalendar; i++) if (m >> kScanOrder[i] & 1) out[n++] = kScanOrder[i];
  if (n == 0) out[n++] = kRendezvous;
  return n;
}

// ------------------------------------------------------------------------------------------------------------------------------------ il collegamento
struct LinkEvent { bool fallback; double silence; int a, b; };   // fallback: silenzio e gradino; altrimenti cambio di gradino a -> b
class Link {
 public:
  int rung = kRendezvous;
  double lastHeard = 0.0, holdUntil = 0.0, lostSince = 0.0;
  bool hadLink = false, hold = false, lost = false;
  // ritorna il numero di eventi (al massimo 2). `order` e' il calendario della ricerca.
  int tick(double t, const uint8_t* order, int orderN, bool calendar, LinkEvent* ev) {
    int n = 0;
    if (!lost && hadLink && t - lastHeard > fallbackS(rung)) {
      lost = true;
      lostSince = lastHeard + fallbackS(rung);
      ev[n++] = LinkEvent{true, t - lastHeard, rung, 0};
    }
    if (lost && !hold && t >= holdUntil) {
      const int nw = calendar ? scanRung(t - lostSince, order, orderN) : kRendezvous;
      if (nw != rung) ev[n++] = LinkEvent{false, 0, rung, nw};
      rung = nw;
    }
    return n;
  }
  bool setRung(int r, LinkEvent* ev) { const bool ch = rung != r; if (ch) *ev = LinkEvent{false, 0, rung, r}; rung = r; return ch; }
  void onTx(double t) { lastHeard = t; }
  void onHeard(double t, int type, bool reply) {      // type < 0: frame non decodificabile
    lastHeard = t;
    hadLink = true;
    if (type == HELLO) { if (reply) hold = true; }
    else { lost = false; hold = false; }
  }
};

// ------------------------------------------------------------------------------------------------------------------------------------ il ricevitore
struct Store {            // dove vanno i pezzi ricevuti (nel firmware: RAM, telefono o microSD)
  virtual ~Store() {}
  virtual void reset(uint16_t nPieces) = 0;
  virtual void put(uint16_t piece, const uint8_t* d, size_t n) = 0;
  virtual size_t get(uint16_t piece, uint8_t* out) = 0;     // ritorna i byte del pezzo
};
struct Reply { const uint8_t* frame = nullptr; size_t len = 0; bool hasHold = false; double holdUntil = 0; int rungAfter = -1; };

class Receiver {
 public:
  Receiver(const uint8_t* call, size_t callLen, bool sx1262, bool tcxo, int window, bool incontroHello, Store* store)
      : sx1262_(sx1262), tcxo_(tcxo), window_(window), hello_(incontroHello), store_(store) { callLen_ = callLen > kMaxCall ? kMaxCall : callLen; memcpy(call_, call, callLen_); }
  uint16_t mask() const { return rungMask(sx1262_, tcxo_); }
  int scanOrder(uint8_t* out) const {
    if (!haveCaps_) { out[0] = kRendezvous; return 1; }
    return scanOrderFor(sx1262_, mask(), peerSx1262_, peerMask_, out);
  }
  bool windowHeard() const { return windowHeard_ > 0; }
  bool probesHeard() const { return probeHeard_ > 0; }
  int k() const { return k_; }
  bool hasDone() const { return hasDone_; }
  bool doneOk() const { return doneOk_; }

  Reply onFrame(const Msg& f, double rssi, double snr, double t, int rung, bool lost) {
    Reply r;
    sess_ = f.sess;
    switch (f.type) {
      case HELLO:
        if (!f.reply) {
          haveCaps_ = true; peerSx1262_ = f.chip != 0; peerMask_ = f.rungMask;
          { const int a = piecesPerFrame(rung, sx1262_), b = piecesPerFrame(rung, peerSx1262_); k_ = a < b ? a : b; }
          if (lost) { const double h = 12.0 * frameAirtimeS(rung, kProbeBytes); r.hasHold = true; r.holdUntil = t + (h > 60.0 ? h : 60.0); }
          int rs = 0, sn = 0;
          if (hello_) { rs = s8round(rssi); sn = s8round(snr); }
          r.len = encHello(buf_, sizeof(buf_), sess_, call_, callLen_, sx1262_, mask(), static_cast<uint8_t>(maxFrame(kRendezvous, sx1262_)), 100, true, hello_ ? &rs : nullptr, hello_ ? &sn : nullptr, nullptr, nullptr, 0);
          r.frame = buf_;
          return r;
        }
        return r;
      case PROBE:
        if (f.idx == 0) { sumR_ = sumS_ = 0; nSamples_ = 0; probeHeard_ = 0; }
        addSample(rssi, snr);
        probeHeard_++; probeCount_ = f.count; probeRung_ = f.rung;
        return r;
      case MODE_SET:
        k_ = f.k;
        r.len = encModeAck(buf_, sizeof(buf_), sess_, f.rung); r.frame = buf_; r.rungAfter = f.rung;
        return r;
      case OFFER:
        nPieces_ = f.nPieces > kMaxPieces ? kMaxPieces : f.nPieces; haveOffer_ = true; nl_ = f.nl;
        for (int i = 0; i < f.nl; i++) layerEnds_[i] = f.layerEnds[i];
        memset(have_, 0, sizeof(have_));
        store_->reset(nPieces_);
        r.len = encAccept(buf_, sizeof(buf_), sess_, f.nl, static_cast<uint8_t>(window_), 1); r.frame = buf_;
        return r;
      case DATA: {
        windowHeard_++;
        if (f.widx > winMax_) winMax_ = f.widx;
        if (f.flags & F_LAST_WINDOW) winLast_ = f.widx;
        addSample(rssi, snr);
        const size_t np = (f.payloadLen + kPiece - 1) / kPiece;
        for (size_t i = 0; i < np; i++) {
          const size_t idx = f.offset + i;
          if (idx < static_cast<size_t>(nPieces_)) {
            const size_t o = i * kPiece, n = f.payloadLen - o < kPiece ? f.payloadLen - o : kPiece;
            store_->put(static_cast<uint16_t>(idx), f.payload + o, n);
            have_[idx >> 3] |= static_cast<uint8_t>(1u << (idx & 7));
          }
        }
        return r;
      }
      case DONE: {
        int nOk = 0;
        while (nOk < nPieces_ && hasPiece(nOk)) nOk++;
        // i primi nbytes byte dei pezzi consecutivi: lunghezza e CRC
        uint32_t crc = 0;
        size_t have = 0;
        uint8_t pb[kPiece];
        for (int i = 0; i < nOk && have < f.nbytes; i++) {
          size_t n = store_->get(static_cast<uint16_t>(i), pb);
          if (n > f.nbytes - have) n = f.nbytes - have;
          crc = crc32Update(crc, pb, n);
          have += n;
        }
        hasDone_ = true; doneOk_ = have == f.nbytes && crc == f.crc;
        r.len = encStatus(buf_, sizeof(buf_), sess_, static_cast<uint16_t>(nOk), 0, 0, 0, 0, f.layers, 1); r.frame = buf_;
        return r;
      }
      default: return r;
    }
  }

  // quanti frame sono partiti nella finestra, dagli indici dei frame sentiti: dal frame di ultima finestra se si e' sentito, altrimenti dal piu' alto indice sentito
  int sentBlocks() const { return (winLast_ >= 0 ? winLast_ : winMax_) + 1; }
  // STATUS alla fine di una finestra: base = primo pezzo mancante, un bit per blocco di k pezzi; la perdita e' misurata sui frame della finestra.
  size_t status(uint8_t* out, size_t cap) {
    const int sentBlocks = this->sentBlocks(), k = k_;
    int base = 0;
    while (base < nPieces_ && hasPiece(base)) base++;
    uint64_t bm = 0;
    for (int i = 0; i < 64; i++) {
      const int lo = base + i * k;
      if (lo >= nPieces_) break;
      bool all = true;
      for (int p = lo; p < lo + k && p < nPieces_; p++) if (!hasPiece(p)) { all = false; break; }
      if (all) bm |= 1ULL << (63 - i);
    }
    const double rs = nSamples_ ? static_cast<double>(sumR_ / nSamples_) : -128.0, sn = nSamples_ ? static_cast<double>(sumS_ / nSamples_) : -128.0;
    const double loss = sentBlocks ? 100.0 * (1 - static_cast<double>(windowHeard_ < sentBlocks ? windowHeard_ : sentBlocks) / sentBlocks) : 0.0;
    int ld = 0;
    if (haveOffer_) for (int i = 0; i < nl_; i++) if (base >= layerEnds_[i]) ld++;
    sumR_ = sumS_ = 0; nSamples_ = 0; windowHeard_ = 0; winMax_ = winLast_ = -1;
    return encStatus(out, cap, sess_, static_cast<uint16_t>(base), bm, s8round(rs), s8round(sn), static_cast<int>(loss), static_cast<uint8_t>(ld), 0);
  }
  // il PROBE-REPORT a timer, dopo la raffica: 0 se non ha sentito nessun PROBE
  size_t probeReport(uint8_t* out, size_t cap) {
    if (probeHeard_ == 0) return 0;
    const double rs = static_cast<double>(sumR_ / nSamples_), sn = static_cast<double>(sumS_ / nSamples_);
    const size_t n = encProbeReport(out, cap, sess_, static_cast<uint8_t>(probeRung_), static_cast<uint8_t>(probeCount_), static_cast<uint8_t>(probeHeard_), s8round(rs), s8round(sn));
    sumR_ = sumS_ = 0; nSamples_ = 0; probeHeard_ = 0;
    return n;
  }

 private:
  static uint32_t crc32Update(uint32_t crc, const uint8_t* d, size_t n) { return crc32(d, n, crc); }
  bool hasPiece(int i) const { return (have_[i >> 3] >> (i & 7)) & 1; }
  void addSample(double r, double s) { sumR_ += r; sumS_ += s; nSamples_++; }
  bool sx1262_, tcxo_;
  int window_;
  bool hello_;
  Store* store_;
  uint8_t call_[kMaxCall + 1];
  size_t callLen_ = 0;
  uint16_t sess_ = 0;
  bool haveCaps_ = false, peerSx1262_ = false;
  uint16_t peerMask_ = 0;
  bool haveOffer_ = false;
  int nPieces_ = 0, nl_ = 0;
  uint16_t layerEnds_[kMaxLayers];
  uint8_t have_[kMaxPieces / 8];
  long double sumR_ = 0, sumS_ = 0;
  int nSamples_ = 0, windowHeard_ = 0, probeHeard_ = 0, probeCount_ = 0, probeRung_ = 0;
  bool hasDone_ = false, doneOk_ = false;
  int k_ = 1, winMax_ = -1, winLast_ = -1;
  uint8_t buf_[64];
};

// ------------------------------------------------------------------------------------------------------------------------------------ il mittente
struct Action {
  enum Kind { None, Exchange, Probe, ModeSet, Burst, Status, Wait, Rand, SetRung, HoldClear, Legacy } kind = None;
  const uint8_t* frame = nullptr;   // Exchange, ModeSet: il frame
  size_t len = 0;
  uint8_t expect = 0;               // Exchange: tipo atteso
  int tries = 0;                    // Exchange
  int count = 0;                    // Probe, Burst: numero di frame (si leggono con Sender::frameAt)
  int target = 0;                   // ModeSet, SetRung
  double seconds = 0;               // Wait
};
struct Answer {
  enum Kind { None, FrameIn, Rnd, Bool } kind = None;
  Msg msg;                          // FrameIn: il frame decodificato
  double rnd = 0;
  bool b = false;
};
enum FailKind { FAIL_NONE, FAIL_HELLO, FAIL_NEGOZIAZIONE, FAIL_OFFER, FAIL_BUDGET, FAIL_PROGRESSO, FAIL_RICERCA, FAIL_DONE };

#define VL_CO_BEGIN switch (pc) { case 0:
#define VL_CO_YIELD(a) do { pc = __LINE__; return (a); case __LINE__:; } while (0)
#define VL_CO_FINISH do { done = true; pc = 0; return Action(); } while (0)
#define VL_CO_FAIL(k) do { s.fail_ = (k); done = true; pc = 0; return Action(); } while (0)
#define VL_CO_END } done = true; pc = 0; return Action()
#define VL_CO_AWAIT(sub, ...) do { sub.start(__VA_ARGS__); for (;;) { tmp = sub.step(s); if (sub.done) break; VL_CO_YIELD(tmp); } if (s.fail_ != FAIL_NONE) VL_CO_FINISH; } while (0)

class Sender {
 public:
  Sender(uint16_t sess, const uint8_t* call, size_t callLen, bool sx1262, bool tcxo, const uint8_t* obj, size_t objLen, const uint16_t* layerEnds, int nl, double budget, int window, int probesR10)
      : sess_(sess), sx1262_(sx1262), tcxo_(tcxo), obj_(obj), objLen_(objLen), nl_(nl), budget_(budget), window_(window), probesR10_(probesR10) {
    callLen_ = callLen > kMaxCall ? kMaxCall : callLen; memcpy(call_, call, callLen_);
    for (int i = 0; i < nl && i < kMaxLayers; i++) layerEnds_[i] = layerEnds[i];
    nPieces_ = static_cast<int>((objLen + kPiece - 1) / kPiece);
  }
  // Una ripresa: il mezzo passa ora, gradino, "in ricerca" e la risposta all'azione precedente (la prima volta: Answer vuota). Ritorna la prossima azione.
  Action resume(const Answer& a, double t, int rung, bool lost) {
    ans_ = a; t_ = t; rung_ = rung; lost_ = lost;
    if (fin_) return Action();
    Action act = top_.step(*this);
    if (top_.done) fin_ = true;
    return act;
  }
  bool finished() const { return fin_; }
  FailKind failure() const { return fail_; }
  bool ok() const { return fin_ && fail_ == FAIL_NONE; }
  // calendario della ricerca (solo R10 finche' non si conosce l'altra stazione)
  int scanOrderOrRendezvous(uint8_t* out) const { if (!peerKnown_) { out[0] = kRendezvous; return 1; } return scanOrder(out); }
  int layersDelivered() const { return resLayers_; }
  uint32_t bytesDelivered() const { return resBytes_; }
  double tHello() const { return tHello_; }
  double tTransfer0() const { return tTransfer0_; }
  // i frame di un'azione Probe o Burst
  bool frameAt(const Action& a, int i, uint8_t* out, size_t cap, size_t* len) const {
    if (a.kind == Action::Probe) { *len = encProbe(out, cap, sess_, static_cast<uint8_t>(probeRung_), static_cast<uint8_t>(i), static_cast<uint8_t>(a.count), kProbeBytes - 7); return *len != 0; }
    if (a.kind != Action::Burst || i >= a.count) return false;
    const BurstItem& b = burst_[i];
    if (b.abort) { *len = encAbort(out, cap, sess_, 1); return true; }
    const size_t from = static_cast<size_t>(b.start) * kPiece, to = (static_cast<size_t>(b.start) + b.pieces) * kPiece;
    const size_t end = to < objLen_ ? to : objLen_;
    *len = encData(out, cap, sess_, static_cast<uint16_t>(b.start), obj_ + from, end > from ? end - from : 0, b.flags, b.widx);
    return *len != 0;
  }

 private:
  struct BurstItem { bool abort; int start; int pieces; uint8_t flags; uint8_t widx; };

  // ----- comodi -----
  uint16_t mask() const { return rungMask(sx1262_, tcxo_); }
  int kFor(int rung) const { const int a = piecesPerFrame(rung, sx1262_), b = piecesPerFrame(rung, peerSx1262_); return a < b ? a : b; }
  int allowed(int* out) const {
    const uint16_t m = commonMask(sx1262_, mask(), peerSx1262_, caps_.rungMask);
    int n = 0;
    for (int r = 0; r < kRungCount; r++) if (m >> r & 1) out[n++] = r;
    return n;
  }
  int scanOrder(uint8_t* out) const { return scanOrderFor(sx1262_, mask(), peerSx1262_, caps_.rungMask, out); }
  Action exchange(const uint8_t* fr, size_t n, uint8_t expect, int tries) { Action a; a.kind = Action::Exchange; a.frame = fr; a.len = n; a.expect = expect; a.tries = tries; return a; }
  Action mkHello() { const size_t n = helloFrame(); return exchange(tx_, n, HELLO, 1); }
  Action mkProbe() { Action a; a.kind = Action::Probe; a.count = rung_ <= kRendezvous ? probesR10_ : 4; probeRung_ = rung_; return a; }
  Action mkModeSet(int target, int k, int rep) {
    txLen_ = encModeSet(tx_, sizeof(tx_), sess_, static_cast<uint8_t>(target), static_cast<uint8_t>(k), static_cast<uint8_t>(rep));
    Action a; a.kind = Action::ModeSet; a.frame = tx_; a.len = txLen_; a.target = target; return a;
  }
  Action mkSetRung(int r) { Action a; a.kind = Action::SetRung; a.target = r; return a; }
  Action mkBurst(int n) { Action a; a.kind = Action::Burst; a.count = n; return a; }
  Action mkStatus() { Action a; a.kind = Action::Status; return a; }
  Action mkOffer(uint32_t crc) {
    txLen_ = encOffer(tx_, sizeof(tx_), sess_, call_, callLen_, 0, static_cast<uint32_t>(objLen_), kPiece, static_cast<uint16_t>(nPieces_), 0, 0, layerEnds_, static_cast<size_t>(nl_), crc, nullptr, nullptr, 0);
    return exchange(tx_, txLen_, ACCEPT, 2);
  }
  Action mkDone(int li, uint32_t* nbytes) {
    const size_t endp = static_cast<size_t>(layerEnds_[li - 1]) * kPiece;
    *nbytes = static_cast<uint32_t>(endp < objLen_ ? endp : objLen_);
    txLen_ = encDone(tx_, sizeof(tx_), sess_, call_, callLen_, static_cast<uint8_t>(li), *nbytes, crc32(obj_, *nbytes));
    return exchange(tx_, txLen_, STATUS, 4);
  }
  Action wait(double s) { Action a; a.kind = Action::Wait; a.seconds = s; return a; }
  Action simple(Action::Kind k) { Action a; a.kind = k; return a; }
  size_t helloFrame() { return txLen_ = encHello(tx_, sizeof(tx_), sess_, call_, callLen_, sx1262_, mask(), static_cast<uint8_t>(maxFrame(10, sx1262_)), 100, false, nullptr, nullptr, nullptr, nullptr, 0); }
  double giveUp() const { const double a = 4.0 * window_ * frameAirtimeS(rung_, kDataHeader + 2 * kPiece); return a > kGiveUpS ? a : kGiveUpS; }
  int predictedBest(double prx, const int* al, int n, double margin) const {
    const double ms[2] = {margin, 3.0};
    for (int j = 0; j < 2; j++) for (int i = 0; i < n; i++) if (prx - sensitivityDbm(al[i]) >= ms[j]) return al[i];
    return al[n - 1];
  }
  bool acked(int p) const { return (acked_[p >> 3] >> (p & 7)) & 1; }
  void setAcked(int p) { acked_[p >> 3] |= static_cast<uint8_t>(1u << (p & 7)); }

  // ----- le procedure (coroutine) -----
  struct Hello { int pc = 0; bool done = false; double wait, t0; Action tmp;
    void start() { pc = 0; done = false; }
    Action step(Sender& s) {
      VL_CO_BEGIN
      wait = 5.0; t0 = s.t_;
      for (;;) {
        VL_CO_YIELD(s.mkHello());
        if (s.ans_.kind == Answer::FrameIn) {
          s.caps_ = s.ans_.msg; s.peerSx1262_ = s.ans_.msg.chip != 0; s.peerKnown_ = true;
          if (s.ans_.msg.hasMeasure) { s.hasHelloMetrics_ = true; s.helloRssi_ = s.ans_.msg.rssi; s.helloSnr_ = s.ans_.msg.snr; }
          s.kNow_ = s.kFor(kRendezvous); s.tHello_ = s.t_ - t0;
          VL_CO_FINISH;
        }
        VL_CO_YIELD(s.simple(Action::Rand));
        VL_CO_YIELD(s.wait(wait * (0.8 + 0.4 * s.ans_.rnd)));
        wait = wait * 2 < 60.0 ? wait * 2 : 60.0;
        if (s.t_ - t0 > 600.0) VL_CO_FAIL(FAIL_HELLO);
      }
      VL_CO_END;
    } };
  struct ProbeP { int pc = 0; bool done = false; bool ok; int rec, exp, rssi, snr; Action tmp;
    void start() { pc = 0; done = false; }
    Action step(Sender& s) {
      VL_CO_BEGIN
      VL_CO_YIELD(s.mkProbe());
      ok = s.ans_.kind == Answer::FrameIn;
      if (ok) { rec = s.ans_.msg.received; exp = s.ans_.msg.expected; rssi = s.ans_.msg.rssi; snr = s.ans_.msg.snr; }
      VL_CO_END;
    } };
  struct SwitchP { int pc = 0; bool done = false; bool ok; int target, k, rep; Action tmp;
    void start(int tg) { pc = 0; done = false; target = tg; }
    Action step(Sender& s) {
      VL_CO_BEGIN
      k = s.kFor(target);
      for (rep = 0; rep < 3; rep++) {
        VL_CO_YIELD(s.mkModeSet(target, k, rep));
        if (s.ans_.kind == Answer::FrameIn) {
          VL_CO_YIELD(s.mkSetRung(target));
          s.kNow_ = k;
          VL_CO_YIELD(s.wait(kGuardS));
          ok = true;
          VL_CO_FINISH;
        }
        VL_CO_YIELD(s.wait(frameAirtimeS(s.rung_, 8) + 2 * kGuardS));
      }
      ok = false;
      VL_CO_END;
    } };
  struct Resync { int pc = 0; bool done = false; double t0; Action tmp;
    void start() { pc = 0; done = false; }
    Action step(Sender& s) {
      VL_CO_BEGIN
      t0 = s.t_;
      VL_CO_YIELD(s.simple(Action::HoldClear));
      while (!s.lost_) { VL_CO_YIELD(s.wait(1.0)); }          // il mittente entra in ricerca con lo stesso timer del ricevitore
      for (;;) {
        VL_CO_YIELD(s.mkHello());
        if (s.ans_.kind == Answer::FrameIn) { s.kNow_ = s.kFor(s.rung_); s.justReconnected_ = true; VL_CO_FINISH; }
        VL_CO_YIELD(s.simple(Action::Rand));
        VL_CO_YIELD(s.wait(frameAirtimeS(s.rung_, 25) * (1.0 + s.ans_.rnd)));
        {
          uint8_t order[kMaxCalendar];
          const int n = s.scanOrder(order);
          double sum = 0;
          for (int i = 0; i < n; i++) sum += scanDwellS(order[i]);
          const double lim = 3.0 * sum > kGiveUpS ? 3.0 * sum : kGiveUpS;
          if (s.t_ - t0 > lim) VL_CO_FAIL(FAIL_RICERCA);
        }
      }
      VL_CO_END;
    } };
  struct Negotiate { int pc = 0; bool done = false; int al[kRungCount], nAl, fails, attempt, target, slower; bool m_ok; int rec, exp, rssi, snr; Action tmp;
    ProbeP probe; SwitchP sw; Resync resync;
    void start() { pc = 0; done = false; }
    Action step(Sender& s) {
      VL_CO_BEGIN
      nAl = s.allowed(al);
      if (s.justReconnected_) { s.justReconnected_ = false; VL_CO_FINISH; }
      fails = 0;
      for (attempt = 0; attempt < 8; attempt++) {
        if (s.hasHelloMetrics_) { m_ok = true; rec = 1; exp = 1; rssi = s.helloRssi_; snr = s.helloSnr_; s.hasHelloMetrics_ = false; }
        else { VL_CO_AWAIT(probe, ); m_ok = probe.ok; rec = probe.rec; exp = probe.exp; rssi = probe.rssi; snr = probe.snr; }
        if (!m_ok) {
          fails++;
          if (fails >= 2) { VL_CO_AWAIT(resync, ); fails = 0; }
          else { VL_CO_YIELD(s.wait(5.0)); }
          continue;
        }
        s.hasRssiEst_ = true; s.rssiEst_ = rssi;
        target = s.predictedBest(rssi, al, nAl, kMarginUpDb);
        if (target == s.rung_) VL_CO_FINISH;
        if (target > s.rung_ && rec >= kProbeOk * exp) VL_CO_FINISH;
        VL_CO_AWAIT(sw, target);
        if (!sw.ok) { VL_CO_AWAIT(resync, ); continue; }
        for (;;) {
          VL_CO_AWAIT(probe, );
          if (probe.ok && probe.rec >= kProbeOk * probe.exp) VL_CO_FINISH;
          slower = -1;
          for (int i = 0; i < nAl; i++) if (al[i] > s.rung_) { slower = al[i]; break; }
          if (slower < 0) VL_CO_FINISH;
          VL_CO_AWAIT(sw, slower);
          if (!sw.ok) { VL_CO_AWAIT(resync, ); break; }
        }
      }
      VL_CO_FAIL(FAIL_NEGOZIAZIONE);
      VL_CO_END;
    } };
  struct StepDown { int pc = 0; bool done = false; bool ok; int al[kRungCount], n, slower; Action tmp; SwitchP sw;
    void start() { pc = 0; done = false; }
    Action step(Sender& s) {
      VL_CO_BEGIN
      n = s.allowed(al); slower = -1;
      for (int i = 0; i < n; i++) if (al[i] > s.rung_) { slower = al[i]; break; }
      if (slower < 0) { ok = true; VL_CO_FINISH; }
      VL_CO_AWAIT(sw, slower);
      ok = sw.ok;
      VL_CO_END;
    } };
  struct Transfer { int pc = 0; bool done = false; Action tmp;
    int attempt, al[kRungCount], nAl, ridBest, base, tl, end, k, goodWindows, upBlock, frontier, nRuns, lastStart, lastPieces, retxCount, newStart, newCount, li, st_attempt, faster, cand, oldRung;
    double lastProgress, est0, loss;
    bool haveAcc, stOk;
    Msg st;
    uint32_t crcObj, nbytes;
    Negotiate neg; Resync resync; StepDown down; SwitchP sw; ProbeP probe;
    void start() { pc = 0; done = false; }
    static int layerTarget(Sender& s, int ackedPrefix) {
      const double elapsed = s.t_ - s.tTransfer0_;
      int best = 0;
      for (int i = 0; i < s.nl_; i++) {
        const int rem = s.layerEnds_[i] > ackedPrefix ? s.layerEnds_[i] - ackedPrefix : 0;
        const double est = rem ? estimateSeconds(static_cast<uint32_t>(rem) * kPiece, s.rung_, s.sx1262_) : 0.0;
        if (elapsed + est <= s.budget_) best = i;
      }
      return best;
    }
    // costruisce la finestra: prima i pezzi non confermati gia' inviati, poi i nuovi, in frame di al massimo k pezzi consecutivi; al massimo `window` frame
    void buildWindow(Sender& s) {
      const int lim = frontier < end ? frontier : end;
      retxCount = 0;
      for (int p = base; p < lim; p++) if (!s.acked(p)) retxCount++;
      newStart = frontier > base ? frontier : base;
      const int room = s.window_ * k - retxCount;
      newCount = newStart < end ? (end - newStart < (room > 0 ? room : 0) ? end - newStart : (room > 0 ? room : 0)) : 0;
      nRuns = 0;
      int runStart = -1, runLen = 0;
      auto push = [&](int p) -> bool {                      // false = finestra piena
        if (runLen > 0 && p == runStart + runLen && runLen < k) { runLen++; return true; }
        if (runLen > 0) { Sender::BurstItem& b = s.burst_[nRuns++]; b = Sender::BurstItem{false, runStart, runLen, 0, 0}; }
        if (nRuns >= s.window_) { runLen = 0; return false; }
        runStart = p; runLen = 1;
        return true;
      };
      bool full = false;
      for (int p = base; p < lim && !full; p++) if (!s.acked(p)) full = !push(p);
      for (int j = 0; j < newCount && !full; j++) full = !push(newStart + j);
      if (!full && runLen > 0) { Sender::BurstItem& b = s.burst_[nRuns++]; b = Sender::BurstItem{false, runStart, runLen, 0, 0}; }
      for (int i = 0; i < nRuns; i++) {                     // flag e fronte
        Sender::BurstItem& b = s.burst_[i];
        uint8_t fl = 0;
        if (i == nRuns - 1) fl |= F_LAST_WINDOW;
        if (b.start >= base && b.start < lim && !s.acked(b.start)) fl |= F_RETX;
        const int endp = b.start + b.pieces;
        for (int e = 0; e < s.nl_; e++) if (s.layerEnds_[e] == endp) fl |= F_LAYER_END;
        if (endp == s.nPieces_) fl |= F_LAST_OBJECT;
        b.flags = fl;
        b.widx = static_cast<uint8_t>(i);
        if (endp > frontier) frontier = endp;
      }
    }
    Action step(Sender& s) {
      VL_CO_BEGIN
      crcObj = crc32(s.obj_, s.objLen_);
      for (attempt = 0; attempt < 4; attempt++) {
        VL_CO_YIELD(s.mkOffer(crcObj));
        haveAcc = s.ans_.kind == Answer::FrameIn;
        if (haveAcc) break;
        VL_CO_AWAIT(resync, );
        VL_CO_AWAIT(neg, );
      }
      if (!haveAcc) VL_CO_FAIL(FAIL_OFFER);
      s.tTransfer0_ = s.t_;
      nAl = s.allowed(al);
      ridBest = s.hasRssiEst_ ? (s.rung_ < s.predictedBest(s.rssiEst_, al, nAl, 3.0) ? s.rung_ : s.predictedBest(s.rssiEst_, al, nAl, 3.0)) : s.rung_;
      est0 = estimateSeconds(static_cast<uint32_t>(s.layerEnds_[0]) * kPiece, ridBest, s.sx1262_);
      if (est0 > s.budget_) {
        s.burst_[0] = Sender::BurstItem{true, 0, 0, 0, 0};
        VL_CO_YIELD(s.mkBurst(1));
        VL_CO_FAIL(FAIL_BUDGET);
      }
      memset(s.acked_, 0, sizeof(s.acked_));
      frontier = 0; goodWindows = 0; upBlock = 0; lastProgress = s.t_;
      for (;;) {
        base = 0;
        while (base < s.nPieces_ && s.acked(base)) base++;
        tl = layerTarget(s, base);
        end = s.layerEnds_[tl];
        if (base >= end) break;
        k = s.kNow_;
        buildWindow(s);
        VL_CO_YIELD(s.mkBurst(nRuns));
        stOk = false;
        for (st_attempt = 0; st_attempt < kStatusRetries; st_attempt++) {
          VL_CO_YIELD(s.mkStatus());
          if (s.ans_.kind == Answer::FrameIn) { st = s.ans_.msg; stOk = true; break; }
          VL_CO_YIELD(s.wait(frameAirtimeS(s.rung_, 20) + kGuardS));
          lastStart = s.burst_[nRuns - 1].start; lastPieces = s.burst_[nRuns - 1].pieces;
          s.burst_[0] = Sender::BurstItem{false, lastStart, lastPieces, static_cast<uint8_t>(F_LAST_WINDOW | F_RETX), static_cast<uint8_t>(nRuns - 1)};
          VL_CO_YIELD(s.mkBurst(1));
        }
        if (!stOk) {
          VL_CO_AWAIT(down, );
          if (!down.ok) {
            VL_CO_AWAIT(resync, );
            VL_CO_AWAIT(neg, );
          }
          goodWindows = 0;
          if (s.t_ - lastProgress > s.giveUp()) VL_CO_FAIL(FAIL_PROGRESSO);
          continue;
        }
        s.hasRssiEst_ = true; s.rssiEst_ = st.rssi;
        {
          const int lim = st.base < s.nPieces_ ? st.base : s.nPieces_;
          for (int p = 0; p < lim; p++) if (!s.acked(p)) { s.setAcked(p); lastProgress = s.t_; }
          for (int i = 0; i < 64; i++) {
            if (st.bitmap >> (63 - i) & 1) {
              const int lo = st.base + i * k;
              for (int p = lo; p < lo + k && p < s.nPieces_; p++) if (!s.acked(p)) { s.setAcked(p); lastProgress = s.t_; }
            }
          }
        }
        loss = st.lossPct / 100.0;
        {
          if (loss > kLossDown) {
            goodWindows = 0;
            VL_CO_AWAIT(down, );
            if (!down.ok) {
            VL_CO_AWAIT(resync, );
            VL_CO_AWAIT(neg, );
          }
          } else if (loss < kLossUp) {
            goodWindows++;
            if (goodWindows >= kUpWindows && upBlock <= 0) {
              goodWindows = 0;
              nAl = s.allowed(al);
              faster = -1;
              for (int i = 0; i < nAl; i++) if (al[i] < s.rung_) faster = al[i];
              if (faster >= 0) {
                cand = faster;
                if (st.rssi - sensitivityDbm(cand) >= kMarginUpDb) {
                  oldRung = s.rung_;
                  VL_CO_AWAIT(sw, cand);
                  if (sw.ok) {
                    VL_CO_AWAIT(probe, );
                    if (!probe.ok || probe.rec < kProbeOk * probe.exp) {
                      VL_CO_AWAIT(sw, oldRung);
                      if (!sw.ok) {
            VL_CO_AWAIT(resync, );
            VL_CO_AWAIT(neg, );
          }
                      upBlock = 5;
                    }
                  } else {
                    VL_CO_AWAIT(resync, );
                    VL_CO_AWAIT(neg, );
                    upBlock = 5;
                  }
                }
              }
            }
            upBlock--;
          } else { goodWindows = 0; upBlock--; }
        }
        if (s.t_ - lastProgress > s.giveUp()) VL_CO_FAIL(FAIL_PROGRESSO);
      }
      li = 0;
      for (int e = 0; e < s.nl_; e++) if (base >= s.layerEnds_[e]) li++;
      VL_CO_YIELD(s.mkDone(li, &nbytes));
      if (s.ans_.kind != Answer::FrameIn) VL_CO_FAIL(FAIL_DONE);       // il mittente non sa se il ricevitore ha sentito il DONE: lo dichiara non confermato
      s.resLayers_ = li; s.resBytes_ = nbytes;
      VL_CO_END;
    } };
  struct Top { int pc = 0; bool done = false; Action tmp; Hello hello; Negotiate neg; Transfer xfer;
    Action step(Sender& s) {
      VL_CO_BEGIN
      VL_CO_AWAIT(hello, );
      VL_CO_AWAIT(neg, );
      VL_CO_AWAIT(xfer, );
      VL_CO_END;
    } };

  // ----- stato -----
  uint16_t sess_;
  bool sx1262_, tcxo_;
  uint8_t call_[kMaxCall + 1];
  size_t callLen_ = 0;
  const uint8_t* obj_;
  size_t objLen_;
  uint16_t layerEnds_[kMaxLayers];
  int nl_, nPieces_;
  double budget_;
  int window_, probesR10_;
  // dal mezzo a ogni ripresa
  double t_ = 0;
  int rung_ = kRendezvous;
  bool lost_ = false;
  Answer ans_;
  // quello che il mittente impara
  Msg caps_;
  bool peerKnown_ = false, peerSx1262_ = false, hasHelloMetrics_ = false, hasRssiEst_ = false, justReconnected_ = false;
  int helloRssi_ = 0, helloSnr_ = 0, rssiEst_ = 0, kNow_ = 0, probeRung_ = 0;
  double tHello_ = 0, tTransfer0_ = 0;
  int resLayers_ = 0;
  uint32_t resBytes_ = 0;
  FailKind fail_ = FAIL_NONE;
  bool fin_ = false;
  // buffer
  uint8_t tx_[256];
  size_t txLen_ = 0;
  uint8_t acked_[kMaxPieces / 8];
  BurstItem burst_[kMaxWindow + 1];
  Top top_;
};

}  // namespace img
}  // namespace v3
