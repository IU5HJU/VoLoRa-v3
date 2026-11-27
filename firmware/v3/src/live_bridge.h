// Ponte telefono <-> scheda COLLEGATO AL MEZZO (Station): quello che il telefono manda parte davvero sul protocollo radio.
// Il buffer e' il telefono (nessuna microSD sulle schede mobili): la scheda tiene kLiveBlocks blocchi da 1 kB e li chiede a richiesta (E_PULL)
// quando il mittente del protocollo ne ha bisogno per riempire una finestra; i pezzi gia' passati si rileggono dalla cache o si richiedono di nuovo.
// Specifica del collegamento: docs/ble-telefono.md (stesse caratteristiche, stessi comandi ed eventi di ble_bridge.h).
// STUDIO: provato solo sul PC (tests/test_live.cpp), mai su una scheda.
#pragma once
#include <cstdint>
#include <cstring>

#include "ble_bridge.h"
#include "medium.h"

namespace v3 {
namespace ble {

constexpr int kLiveBlocks = 8;            // 8 kB di RAM: una finestra di 16 frame da 15 pezzi sono 3,8 kB (fino a 5 blocchi)
constexpr int kLiveAhead = 3;             // blocchi chiesti in anticipo oltre quello che serve
constexpr double kLiveBudgetS = 600.0;
constexpr uint8_t kDiagStall = 100, kDiagCancelled = 101;     // E_DIAG: oltre ai motivi del protocollo (FailKind 0-7): telefono sparito, annullato
constexpr size_t kRxChunk = 48;           // byte per notifica su data_out (MTU minimo 64 meno 3 meno 5 di intestazione)

struct LiveSink {
  virtual ~LiveSink() {}
  virtual void log(const char* line) { (void)line; }                                          // riga per il registro delle prove (opzionale)
  virtual void evt(const uint8_t* d, size_t n) = 0;                                          // notifica su `evt`
  virtual void rxChunk(uint16_t obj, uint32_t off, const uint8_t* d, size_t n) = 0;          // notifica su `data_out` (il guscio mette obj(2) off(3) davanti)
};

class LiveBridge : public img::ObjectSource {
 public:
  // `rxStore`: dove il mezzo mette gli oggetti che arrivano dalla radio (`rxMax` byte al massimo); la stessa che si e' data alla Station.
  LiveBridge(LiveSink* sink, img::Station* st, const char* call, bool sx1262, uint16_t rungMask, img::Store* rxStore, uint32_t rxMax)
      : sink_(sink), st_(st), sx1262_(sx1262), rungMask_(rungMask), rxStore_(rxStore), rxMax_(rxMax) {
    strncpy(call_, call ? call : "", sizeof(call_) - 1);
    updateGate();
  }

  struct Stats { uint32_t pulls = 0, repulls = 0, blocksIn = 0, dropped = 0, badFrames = 0, maxStallMs = 0, rxObjects = 0; bool crcMismatch = false; };
  const Stats& stats() const { return stats_; }
  bool connected() const { return connected_; }
  bool busy() const { return have_; }
  bool rxBusy() const { return rxPending_; }          // sta ancora passando al telefono un oggetto arrivato dalla radio
  uint32_t held() const { uint32_t h = 0; for (int i = 0; i < kLiveBlocks; i++) if (slot_[i].blk >= 0) h += slot_[i].fill; return h; }

  // per il display
  uint8_t sendKind() const { return kind_; }
  int sendPct() const { const int t = st_->piecesTotal(); return t > 0 ? 100 * st_->piecesAcked() / t : 0; }
  bool hasPosition() const { return havePos_; }
  // Posizione GPS della scheda (T-Beam): se c'e' un fix e' lei che va nell'OFFER ("la posizione GPS assoluta e' meglio", regole-radioamatoriali.md), altrimenti quella del telefono.
  // Blocco di 7 byte: byte 0 = 1, poi latitudine e longitudine a 24 bit (position.h). Senza fix: setGps(nullptr).
  void setGps(const uint8_t* block7) { haveGps_ = block7 != nullptr; if (block7) memcpy(gpsPos_, block7, 7); refreshPos(); }
  const uint8_t* positionBlock() const { return pos_; }
  // "JN53ab" (locatore) o "GPS" (posizione assoluta) in out (almeno 7 byte)
  void positionText(char* out) const { if (!havePos_) { out[0] = 0; return; } if (pos_[0] == 0) { memcpy(out, pos_ + 1, 6); out[6] = 0; } else strcpy(out, "GPS"); }
  void onConnect() { connected_ = true; updateGate(); }
  void onDisconnect() {
    connected_ = false;
    for (int i = 0; i < kLiveBlocks; i++) if (slot_[i].blk >= 0 && !slot_[i].complete) slot_[i].blk = -1;   // un blocco a meta' si butta
    asked_ = 0;
    rxPending_ = false;                  // quello che si stava passando al telefono si perde: il mittente lo ripropone quando il telefono c'e'
    updateGate();
  }

  void onCommand(const uint8_t* b, size_t n) {
    bool ok = n > 0;
    if (ok) {
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
        if (n != 8 || (b[1] != 0 && b[1] != 1) || (b[1] == 0 && !detail::ascii(b + 2, 6))) ok = false;
        else { memcpy(phonePos_, b + 1, 7); havePhone_ = true; refreshPos(); }
      } else if (c == C_BEGIN) {
        ok = begin(b, n);
      } else if (c == C_CANCEL || c == C_RESUME || c == C_RX_ACK) {
        if (n != 3) ok = false;
        else {
          const uint16_t obj = static_cast<uint16_t>(detail::rd(b + 1, 2));
          if (c == C_CANCEL) cancel(obj); else if (c == C_RESUME) resume(obj);      // C_RX_ACK: la copia e' gia' liberata a fine consegna
        }
      } else ok = false;
    }
    if (!ok) { stats_.badFrames++; err(0, ERR_BAD_FRAME); }
  }

  void onData(const uint8_t* b, size_t n) {
    if (n <= static_cast<size_t>(kDataHdr)) { stats_.badFrames++; return; }
    const uint16_t obj = static_cast<uint16_t>(detail::rd(b, 2));
    const uint32_t off = detail::rd(b + 2, 3);
    const size_t pn = n - kDataHdr;
    if (!have_ || obj_ != obj) return;
    const uint32_t k = off / kBlock;
    if (k >= 64 || !(asked_ >> k & 1) || k >= nblocks()) { stats_.dropped++; return; }
    int si = findSlot(k);
    if (si >= 0 && slot_[si].complete) { stats_.dropped++; return; }
    if (si < 0) { stats_.dropped++; return; }                       // lo slot lo ha assegnato la richiesta
    Slot& sl = slot_[si];
    const uint32_t start = k * kBlock, ln = blockLen(k);
    if (off != start + sl.fill || sl.fill + pn > ln) { stats_.dropped++; return; }
    memcpy(sl.data + sl.fill, b + kDataHdr, pn);
    sl.fill = static_cast<uint16_t>(sl.fill + pn);
    if (sl.fill == ln) { sl.complete = true; stats_.blocksIn++; advanceCrc(); }
  }

  // il tempo passa (chiamare spesso)
  void poll(double now) {
    now_ = now;
    pumpRx();
    watchRx();
    if (!have_) return;
    if (st_->sendFinished()) { diag(static_cast<uint8_t>(st_->sendFailure())); finishSend(st_->sendOk() ? DONE_DELIVERED : DONE_FAILED); return; }
    if (stallSince_ > 0) {
      const double d = now - stallSince_;
      if (d * 1000 > stats_.maxStallMs) stats_.maxStallMs = static_cast<uint32_t>(d * 1000);
      if (d > kStallTimeoutS) { diag(kDiagStall); st_->cancelSend(); finishSend(DONE_FAILED); return; }
    }
    progress();
  }

  // ----- ObjectSource: i byte dell'oggetto, dalla cache o dal telefono -----
  bool read(size_t off, size_t n, uint8_t* out) override {
    if (!have_ || n == 0) return false;
    const uint32_t k0 = static_cast<uint32_t>(off / kBlock), k1 = static_cast<uint32_t>((off + n - 1) / kBlock);
    bool all = true;
    for (uint32_t k = k0; k <= k1; k++) if (findComplete(k) < 0) all = false;
    if (!all) {
      if (stallSince_ == 0) stallSince_ = now_ > 0 ? now_ : 1e-9;
      requestFrom(k0, k1);
      return false;
    }
    stallSince_ = 0;
    size_t done = 0;
    for (uint32_t k = k0; k <= k1; k++) {
      const int si = findComplete(k);
      slot_[si].used = ++useTick_;
      const size_t start = static_cast<size_t>(k) * kBlock;
      const size_t from = off + done > start ? off + done - start : 0;
      size_t take = blockLen(k) - from;
      if (take > n - done) take = n - done;
      memcpy(out + done, slot_[si].data + from, take);
      done += take;
    }
    return true;
  }
  uint32_t crcAll() override { return crc_; }
  bool crcPrefix(size_t n, uint32_t* crc) override {
    for (int i = 0; i < nl_; i++) if (endBytes_[i] == n && prefOk_[i]) { *crc = pref_[i]; return true; }
    if (n == size_ && crcNext_ >= nblocks()) { *crc = crcRun_; return true; }
    return false;
  }

 private:
  struct Slot { int16_t blk = -1; uint16_t fill = 0; bool complete = false; uint32_t used = 0; uint8_t data[kBlock]; };

  void refreshPos() {
    if (haveGps_) { memcpy(pos_, gpsPos_, 7); havePos_ = true; }
    else if (havePhone_) { memcpy(pos_, phonePos_, 7); havePos_ = true; }
    else havePos_ = false;
  }
  void notify(const uint8_t* d, size_t n) { if (connected_) sink_->evt(d, n); }
  void err(uint16_t obj, uint8_t code) { uint8_t o[4]; o[0] = E_ERR; detail::wr(o + 1, obj, 2); o[3] = code; notify(o, 4); }
  uint32_t nblocks() const { return (size_ + kBlock - 1) / kBlock; }
  uint32_t blockLen(uint32_t k) const { const uint32_t rest = size_ - k * kBlock; return rest < kBlock ? rest : kBlock; }
  int findSlot(uint32_t k) const { for (int i = 0; i < kLiveBlocks; i++) if (slot_[i].blk == static_cast<int>(k)) return i; return -1; }
  int findComplete(uint32_t k) const { const int i = findSlot(k); return (i >= 0 && slot_[i].complete) ? i : -1; }
  void updateGate() { st_->receiver().setAccepting(connected_ && !have_ && !rxPending_, rxMax_); }

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
  // Riepilogo di fine invio (E_DIAG 0x8A): obj(2) motivo(1) livelli(1) byte(3) gradino(1) % confermata(1) secondi(2). Il motivo e' il FailKind del protocollo
  // (0 = consegnato; 1 hello, 2 negoziazione, 3 offerta, 4 budget, 5 progresso, 6 ricerca, 7 DONE) oppure 100 telefono sparito, 101 annullato. Serve a capire perche' un invio e' fallito.
  void diag(uint8_t why) {
    uint8_t o[12];
    o[0] = E_DIAG; detail::wr(o + 1, obj_, 2); o[3] = why; o[4] = static_cast<uint8_t>(st_->layersDelivered()); detail::wr(o + 5, st_->bytesDelivered(), 3);
    o[8] = static_cast<uint8_t>(st_->link().rung);
    const int t = st_->piecesTotal();
    o[9] = static_cast<uint8_t>(t > 0 ? 100 * st_->piecesAcked() / t : 0);
    const double el = now_ - beganAt_;
    const uint32_t secs = static_cast<uint32_t>(el < 0 ? 0 : el > 65535 ? 65535 : el);
    detail::wr(o + 10, secs, 2);
    notify(o, 12);
    char line[112];
    snprintf(line, sizeof(line), "fine invio obj %u: motivo %u, livelli %u, byte %u, R%u, %u%% confermato, %u s", static_cast<unsigned>(obj_), why, o[4], static_cast<unsigned>(st_->bytesDelivered()), o[8], o[9], static_cast<unsigned>(secs));
    sink_->log(line);
  }
  void finishSend(uint8_t status) {
    const uint16_t obj = obj_;
    have_ = false;
    for (int i = 0; i < kLiveBlocks; i++) { slot_[i].blk = -1; slot_[i].fill = 0; slot_[i].complete = false; }
    asked_ = 0;
    stallSince_ = 0;
    done(obj, status);
    updateGate();
  }

  // ----- richieste di blocchi -----
  bool evictable(int i, uint32_t k0, uint32_t k1) const {
    const Slot& s = slot_[i];
    if (s.blk < 0) return true;
    if (!s.complete) return false;
    if (static_cast<uint32_t>(s.blk) >= crcNext_) return false;     // il CRC corrente passa da qui: non si butta quello che non e' ancora stato contato
    if (static_cast<uint32_t>(s.blk) >= k0 && static_cast<uint32_t>(s.blk) <= k1) return false;
    return true;
  }
  int allocSlot(uint32_t k, uint32_t k0, uint32_t k1) {
    int best = -1;
    for (int i = 0; i < kLiveBlocks; i++) {
      if (!evictable(i, k0, k1)) continue;
      if (slot_[i].blk < 0) { best = i; break; }
      if (best < 0 || slot_[i].used < slot_[best].used) best = i;
    }
    if (best < 0) return -1;
    if (slot_[best].blk >= 0) asked_ &= ~(1ULL << slot_[best].blk);
    slot_[best].blk = static_cast<int16_t>(k); slot_[best].fill = 0; slot_[best].complete = false; slot_[best].used = ++useTick_;
    return best;
  }
  void requestFrom(uint32_t k0, uint32_t k1) {
    if (!connected_) return;
    uint32_t last = k1 + 0;
    if (last < k0 + kLiveAhead) last = k0 + kLiveAhead;
    if (last >= nblocks()) last = nblocks() - 1;
    for (uint32_t k = k0; k <= last; k++) {
      if (findComplete(k) >= 0 || (asked_ >> k & 1)) continue;
      if (allocSlot(k, k0, last) < 0) break;
      asked_ |= 1ULL << k;
      stats_.pulls++;
      if (served_ >> k & 1) stats_.repulls++;
      served_ |= 1ULL << k;
      uint8_t o[8];
      o[0] = E_PULL; detail::wr(o + 1, obj_, 2); detail::wr(o + 3, k * kBlock, 3); detail::wr(o + 6, blockLen(k), 2);
      notify(o, 8);
    }
  }

  // CRC corrente e CRC dei prefissi alle fine dei livelli: si fanno quando i blocchi passano la prima volta in ordine
  void advanceCrc() {
    for (;;) {
      if (crcNext_ >= nblocks()) return;
      const int si = findComplete(crcNext_);
      if (si < 0) return;
      const uint32_t start = crcNext_ * kBlock, ln = blockLen(crcNext_);
      for (int i = 0; i < nl_; i++)
        if (!prefOk_[i] && endBytes_[i] > start && endBytes_[i] <= start + ln) { pref_[i] = img::crc32(slot_[si].data, endBytes_[i] - start, crcRun_); prefOk_[i] = true; }
      crcRun_ = img::crc32(slot_[si].data, ln, crcRun_);
      crcNext_++;
      if (crcNext_ == nblocks() && crcRun_ != crc_) stats_.crcMismatch = true;
    }
  }

  bool begin(const uint8_t* b, size_t n) {
    // stesso formato di Bridge::begin
    if (n < 16) return false;
    const uint16_t obj = static_cast<uint16_t>(detail::rd(b + 1, 2));
    const uint8_t kind = b[3];
    const uint32_t size = detail::rd(b + 4, 3), crc = detail::rd(b + 7, 4);
    const uint8_t nl = b[15];
    if (nl > kMaxLayers) return false;
    size_t p = 16 + 3 * static_cast<size_t>(nl);
    if (p >= n) return false;
    const size_t dl = b[p];
    if (p + 1 + dl >= n) return false;
    if (!detail::ascii(b + p + 1, dl)) return false;
    p += 1 + dl;
    const size_t nm = b[p];
    if (n != p + 1 + nm) return false;
    if (!detail::utf8Valid(b + p + 1, nm)) return false;
    if (call_[0] == 0) { err(obj, ERR_NO_CALL); return true; }
    if (kind != kKindText && kind != kKindFile && kind != kKindImage) { err(obj, ERR_BAD_KIND); return true; }
    if (!havePos_) { err(obj, ERR_NO_POSITION); return true; }
    if (size == 0 || size > kMaxObject || (kind == kKindText && size > kMaxText)) { err(obj, ERR_TOO_BIG); return true; }
    if (have_ || st_->sending() || rxPending_) { err(obj, ERR_BUSY); return true; }
    // sessione
    obj_ = obj; kind_ = kind; size_ = size; crc_ = crc;
    nl_ = nl ? nl : 1;
    const uint32_t nPieces = (size + kPiece - 1) / kPiece;
    uint16_t endPieces[kMaxLayers];
    for (int i = 0; i < nl_; i++) {
      uint32_t e = nl ? detail::rd(b + 16 + 3 * i, 3) : size;
      uint32_t ep = (e + kPiece - 1) / kPiece;
      if (ep > nPieces) ep = nPieces;
      endPieces[i] = static_cast<uint16_t>(ep);
      uint32_t eb = ep * kPiece;
      endBytes_[i] = eb < size ? eb : size;
      prefOk_[i] = false;
    }
    endPieces[nl_ - 1] = static_cast<uint16_t>(nPieces);    // l'ultimo livello e' l'oggetto intero
    endBytes_[nl_ - 1] = size;
    for (int i = 0; i < kLiveBlocks; i++) { slot_[i].blk = -1; slot_[i].fill = 0; slot_[i].complete = false; slot_[i].used = 0; }
    asked_ = 0; served_ = 0; crcNext_ = 0; crcRun_ = 0; stallSince_ = 0; pct_ = 0; lastProgress_ = now_;
    have_ = true;
    beganAt_ = now_;
    { char line[96]; snprintf(line, sizeof(line), "inizio invio obj %u: tipo %u, %u byte, %u livelli", static_cast<unsigned>(obj), kind, static_cast<unsigned>(size), nl_); sink_->log(line); }
    if (!st_->startSend(this, size, endPieces, nl_, kLiveBudgetS, obj, img::kProbeCount, kind, pos_)) { have_ = false; err(obj, ERR_BUSY); return true; }
    updateGate();
    const double eta = estimateSeconds(size, st_->link().rung, sx1262_);
    uint8_t o[9];
    o[0] = E_BEGIN_OK; detail::wr(o + 1, obj, 2); detail::wr(o + 3, static_cast<uint32_t>(eta + 0.5), 3); o[6] = static_cast<uint8_t>(st_->link().rung); detail::wr(o + 7, kBlock, 2);
    notify(o, 9);
    return true;
  }
  void cancel(uint16_t obj) {
    if (!have_ || obj_ != obj) { err(obj, ERR_UNKNOWN_OBJ); return; }
    diag(kDiagCancelled);
    st_->cancelSend();
    finishSend(DONE_CANCELLED);
  }
  void resume(uint16_t obj) {
    int at = -1;
    for (int i = 0; i < lastN_; i++) if (last_[i].obj == obj) at = i;
    if (at >= 0 && (!have_ || obj_ != obj)) { uint8_t o[4]; o[0] = E_DONE; detail::wr(o + 1, obj, 2); o[3] = last_[at].status; notify(o, 4); return; }
    if (!have_ || obj_ != obj) { err(obj, ERR_UNKNOWN_OBJ); return; }
    asked_ = 0;                          // quello che era stato chiesto prima della caduta va richiesto di nuovo
    stallSince_ = stallSince_ > 0 ? now_ : 0;
  }
  void progress() {
    const int tot = st_->piecesTotal();
    if (tot <= 0) return;
    int pct = 100 * st_->piecesAcked() / tot;
    if (pct > 99) pct = 99;
    if (pct - pct_ >= 10 && now_ - lastProgress_ >= 2.0) {
      pct_ = pct; lastProgress_ = now_;
      const double eta = estimateSeconds(size_, st_->link().rung, sx1262_) * (100 - pct) / 100;
      uint8_t o[9];
      o[0] = E_PROGRESS; detail::wr(o + 1, obj_, 2); o[3] = static_cast<uint8_t>(pct); o[4] = static_cast<uint8_t>(st_->link().rung);
      detail::wr(o + 5, static_cast<uint32_t>(eta), 3);
      notify(o, 8);
    }
  }

  // ----- dalla radio al telefono -----
  void watchRx() {
    img::Receiver& rx = st_->receiver();
    if (rx.doneCount() == seenDone_) return;
    seenDone_ = rx.doneCount();
    if (!rx.doneOk() || !connected_ || rxPending_) { updateGate(); return; }
    // CRC dei byte consegnati (il frame E_RX lo porta prima dei dati)
    const uint32_t nb = rx.doneBytes();
    uint32_t crc = 0;
    uint8_t pb[kPiece];
    size_t got = 0;
    for (uint32_t p = 0; got < nb; p++) {
      size_t m = rxStore_->get(static_cast<uint16_t>(p), pb);
      if (m > nb - got) m = nb - got;
      if (m == 0) break;
      crc = img::crc32(pb, m, crc);
      got += m;
    }
    rxObj_++;
    rxSize_ = nb; rxPos_ = 0; rxPending_ = true;
    char from[13];
    size_t fl = rx.peerCallLen() > 12 ? 12 : rx.peerCallLen();
    memcpy(from, rx.peerCall(), fl);
    uint8_t o[32];
    o[0] = E_RX; detail::wr(o + 1, rxObj_, 2); o[3] = rx.objType(); detail::wr(o + 4, nb, 3); detail::wr(o + 7, crc, 4); o[11] = static_cast<uint8_t>(fl);
    memcpy(o + 12, from, fl);
    notify(o, 12 + fl);
    stats_.rxObjects++;
    updateGate();
  }
  void pumpRx() {
    if (!rxPending_ || !connected_) return;
    for (int c = 0; c < 4 && rxPos_ < rxSize_; c++) {
      uint8_t buf[kRxChunk];
      size_t n = 0;
      while (n < kRxChunk && rxPos_ + n < rxSize_) {                        // i pezzi da 16 B dal negozio del mezzo
        const uint32_t pos = rxPos_ + static_cast<uint32_t>(n);
        uint8_t pb[kPiece];
        const size_t m = rxStore_->get(static_cast<uint16_t>(pos / kPiece), pb);
        const size_t from = pos % kPiece;
        if (m <= from) { n = kRxChunk; break; }
        size_t take = m - from;
        if (take > kRxChunk - n) take = kRxChunk - n;
        if (take > rxSize_ - pos) take = rxSize_ - pos;
        memcpy(buf + n, pb + from, take);
        n += take;
      }
      if (n == 0 || n > kRxChunk) break;
      sink_->rxChunk(rxObj_, rxPos_, buf, n);
      rxPos_ += static_cast<uint32_t>(n);
    }
    if (rxPos_ >= rxSize_) { rxPending_ = false; updateGate(); }
  }

  LiveSink* sink_;
  img::Station* st_;
  bool sx1262_;
  uint16_t rungMask_;
  img::Store* rxStore_;
  uint32_t rxMax_;
  char call_[13] = {0};
  uint8_t pos_[7] = {0};
  bool havePos_ = false, havePhone_ = false, haveGps_ = false, connected_ = true, have_ = false;
  uint8_t phonePos_[7] = {0}, gpsPos_[7] = {0};
  double now_ = 0, stallSince_ = 0, lastProgress_ = 0, beganAt_ = 0;
  Stats stats_;
  // oggetto in uscita
  uint16_t obj_ = 0;
  uint8_t kind_ = 0;
  uint32_t size_ = 0, crc_ = 0;
  int nl_ = 1, pct_ = 0;
  uint32_t endBytes_[kMaxLayers] = {0}, pref_[kMaxLayers] = {0};
  bool prefOk_[kMaxLayers] = {false};
  uint32_t crcRun_ = 0, crcNext_ = 0, useTick_ = 0;
  uint64_t asked_ = 0, served_ = 0;
  Slot slot_[kLiveBlocks];
  struct Last { uint16_t obj; uint8_t status; } last_[4];
  int lastN_ = 0;
  // oggetto in ingresso
  int seenDone_ = 0;
  bool rxPending_ = false;
  uint16_t rxObj_ = 0;
  uint32_t rxSize_ = 0, rxPos_ = 0;
};

}  // namespace ble
}  // namespace v3
