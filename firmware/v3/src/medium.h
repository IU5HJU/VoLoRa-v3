// Il MEZZO della scheda: collega il protocollo immagini (img_proto.h) alla radio e ai timer, in tempo reale.
//   Radio    l'interfaccia che la scheda (radio_board.h, RadioLib) e il simulatore sul PC (tests/test_medium.cpp) implementano.
//   Station  una stazione: collegamento + ricevitore (che risponde da solo) + mittente (le cui azioni diventano trasmissioni e attese). Si pilota con tre eventi:
//            onRx (un frame sentito), onTxDone (trasmissione finita), poll (il tempo passa).
// Mezzo duplex: una stazione trasmette oppure ascolta. Nessuna memoria dinamica. Provato sul PC con due stazioni e un canale con perdite (tests/test_medium.cpp); mai su una scheda.
//
// Cosa fa il ricevitore da solo (nel simulatore Python lo faceva il mezzo a richiesta del mittente):
//   * risponde ai frame di richiesta (HELLO, MODE-SET, OFFER, DONE) dopo un tempo di commutazione (kGuardS);
//   * manda lo STATUS appena sente il frame con il flag di ultima finestra, oppure dopo un silenzio (un frame lungo piu' la commutazione) se ha sentito qualche DATA;
//   * manda il PROBE-REPORT appena sente l'ultimo PROBE della raffica, oppure dopo un silenzio se ne ha sentito qualcuno;
//   * dopo il MODE-ACK passa al nuovo gradino, sia che il mittente lo senta o no.
// Cosa aspetta il mittente: dopo ogni frame che chiede una risposta, la risposta fino a un tempo limite (due commutazioni piu' il tempo in aria della risposta, piu' il silenzio
// del ricevitore dove serve); scaduto, ritenta o riporta "nessuna risposta" al protocollo, che decide.
#pragma once
#include <cstring>
#include <new>

#include "img_proto.h"

namespace v3 {
namespace img {

struct Radio {
  virtual ~Radio() {}
  virtual void setRung(int rung) = 0;                              // configura il modem sul gradino e si mette in ascolto
  virtual bool transmit(const uint8_t* frame, size_t n) = 0;      // inizia a trasmettere (non bloccante); a fine trasmissione chiamare Station::onTxDone
  virtual double random() = 0;                                     // un numero casuale in [0, 1)
};

constexpr double kPendingRetryS = 0.02;

class Station {
 public:
  // `unsupported`: gradini che la radio non sa fare (per esempio R3 sull'SX1278): non si annunciano, quindi non si usano
  Station(const uint8_t* call, size_t callLen, bool sx1262, bool tcxo, Radio* radio, Store* store, int window = kWindowFrames, bool helloWithMeasure = true, uint16_t unsupported = 0, double khz = kDefaultKhz)
      : radio_(radio), sx1262_(sx1262), tcxo_(tcxo), window_(window), unsupported_(unsupported), khz_(khz), rx_(call, callLen, sx1262, tcxo, window, helloWithMeasure, store, unsupported, khz) {
    callLen_ = callLen > static_cast<size_t>(kMaxCall) ? static_cast<size_t>(kMaxCall) : callLen;
    memcpy(call_, call, callLen_);
    radio_->setRung(link_.rung);
  }
  ~Station() { if (snd_) snd_->~Sender(); }
  Station(const Station&) = delete;
  Station& operator=(const Station&) = delete;

  // ----- comandi -----
  // Manda un oggetto (il buffer deve restare valido fino alla fine). false se un invio e' gia' in corso o l'oggetto e' troppo grande.
  bool startSend(const uint8_t* obj, size_t len, const uint16_t* layerEnds, int nl, double budgetS, uint16_t sess, int probesR10 = kProbeCount) {
    new (&mem_) MemSource(obj, len);
    return startSend(&mem_, len, layerEnds, nl, budgetS, sess, probesR10);
  }
  // Variante con sorgente esterna (per esempio il telefono): `src` deve restare valida fino alla fine dell'invio.
  bool startSend(ObjectSource* obj, size_t len, const uint16_t* layerEnds, int nl, double budgetS, uint16_t sess, int probesR10 = kProbeCount, uint8_t objType = 0, const uint8_t* pos7 = nullptr) {
    if ((snd_ && !snd_->finished()) || len == 0 || len > 65536 || nl < 1 || nl > kMaxLayers) return false;
    if (snd_) snd_->~Sender();
    snd_ = new (sndMem_) Sender(sess, call_, callLen_, sx1262_, tcxo_, obj, len, layerEnds, nl, budgetS, window_, probesR10, unsupported_, objType, khz_);
    if (pos7) snd_->setPosition(pos7);
    ex_ = Exec();
    ex_.st = Exec::Resume;
    ans_ = Answer();
    return true;
  }
  // Annulla l'invio in corso (il mezzo lascia perdere: nessun ABORT in aria, il ricevente chiude per silenzio)
  void cancelSend() { if (snd_ && !snd_->finished()) { snd_->~Sender(); snd_ = nullptr; ex_ = Exec(); ans_ = Answer(); } }
  int piecesAcked() const { return snd_ ? snd_->piecesAcked() : 0; }
  int piecesTotal() const { return snd_ ? snd_->nPieces() : 0; }
  bool sending() const { return snd_ && !snd_->finished(); }
  bool sendFinished() const { return snd_ && snd_->finished(); }
  bool sendOk() const { return snd_ && snd_->ok(); }
  FailKind sendFailure() const { return snd_ ? snd_->failure() : FAIL_NONE; }
  int layersDelivered() const { return snd_ ? snd_->layersDelivered() : 0; }
  uint32_t bytesDelivered() const { return snd_ ? snd_->bytesDelivered() : 0; }
  // ultimo frame sentito (per il display)
  double lastRssi() const { return lastRssi_; }
  double lastSnr() const { return lastSnr_; }
  double lastRxAt() const { return lastRxAt_; }
  uint32_t rxFrames() const { return rxFrames_; }
  const Receiver& receiver() const { return rx_; }
  Receiver& receiver() { return rx_; }
  const Link& link() const { return link_; }

  // ----- eventi -----
  void onRx(const uint8_t* f, size_t n, double rssi, double snr, double now) {
    lastRssi_ = rssi; lastSnr_ = snr; lastRxAt_ = now; rxFrames_++;
    Msg m;
    if (!decode(f, n, &m)) { link_.onHeard(now, -1, false); return; }
    link_.onHeard(now, m.type, m.type == HELLO && m.reply);
    // frame per il mittente: solo se li sta aspettando
    if (ex_.st == Exec::WaitReply && m.type == ex_.expect && isForSender(m)) {
      ans_.kind = Answer::FrameIn;
      ans_.msg = m;
      ex_.st = Exec::Resume;
      return;
    }
    if (isForSender(m)) return;
    // frame per il ricevitore
    const Reply r = rx_.onFrame(m, rssi, snr, now, link_.rung, link_.lost);
    if (r.hasHold) link_.holdUntil = r.holdUntil;
    if (r.frame) scheduleFrame(r.frame, r.len, now + kGuardS, r.rungAfter);
    if (m.type == DATA) {
      if (m.flags & F_LAST_WINDOW) scheduleReport(Rep::Status, now + kGuardS);
      else dataIdleAt_ = now + idleData();
    } else if (m.type == PROBE) {
      if (m.idx + 1 >= m.count) scheduleReport(Rep::Probe, now + kGuardS);
      else probeIdleAt_ = now + idleProbe();
    }
  }
  void onTxDone(double now) {
    txBusy_ = false;
    link_.onTx(now);
    if (txKind_ == Tx::Reply) {
      if (reply_.rungAfter >= 0) setRung(reply_.rungAfter);      // il ricevitore passa al nuovo gradino dopo il MODE-ACK, sia che il mittente lo senta o no
      reply_.rungAfter = -1;
    } else if (txKind_ == Tx::Sender) {
      if (ex_.act.kind == Action::Exchange || ex_.act.kind == Action::ModeSet) {
        ex_.st = Exec::WaitReply;
        ex_.deadline = now + replyWait();
      } else if (ex_.sent >= ex_.act.count) {                    // raffica finita
        if (ex_.act.kind == Action::Probe) { ex_.st = Exec::WaitReply; ex_.expect = PROBE_REPORT; ex_.deadline = now + idleProbe() + replyWait(); }
        else { ans_ = Answer(); ex_.st = Exec::Resume; }
      }
    }
    txKind_ = Tx::None;
  }
  // il tempo passa (chiamare spesso: almeno ogni `nextWake`)
  void poll(double now) {
    linkTick(now);
    if (txBusy_) return;
    idleTimers(now);
    if (reply_.pending && now >= reply_.at) { sendReply(now); return; }
    if (snd_ && !snd_->finished()) driveSender(now);
  }
  // entro quando serve il prossimo poll
  double nextWake(double now) const {
    double w = now + 0.1;
    if (txBusy_) return w;                     // sta trasmettendo: ci sveglia la fine della trasmissione
    auto min = [&](double t) { if (t > 0 && t < w) w = t; };
    if (reply_.pending) min(reply_.at);
    if (ex_.st == Exec::WaitReply || ex_.st == Exec::Timer) min(ex_.deadline);
    if (ex_.st == Exec::Sending) min(ex_.notBefore);
    min(dataIdleAt_); min(probeIdleAt_);
    return w < now ? now : w;
  }

 private:
  struct Exec {
    enum St { Idle, Resume, Sending, WaitReply, Timer } st = Idle;
    Action act;
    int sent = 0, triesLeft = 0;
    uint8_t expect = 0;
    double deadline = 0, notBefore = 0;
  };
  struct Rep { enum Kind { None, Frame, Status, Probe }; };
  struct Pending { bool pending = false; Rep::Kind kind = Rep::None; double at = 0; uint8_t buf[64]; size_t len = 0; int rungAfter = -1; };
  enum class Tx { None, Reply, Sender };

  static bool isForSender(const Msg& m) { return m.type == PROBE_REPORT || m.type == MODE_ACK || m.type == ACCEPT || m.type == STATUS || (m.type == HELLO && m.reply); }
  double replyWait() const { return 2 * kGuardS + frameAirtimeS(link_.rung, 48); }
  double idleData() const { return frameAirtimeS(link_.rung, maxFrame(link_.rung, sx1262_)) + 2 * kGuardS; }
  double idleProbe() const { return frameAirtimeS(link_.rung, kProbeBytes) + 2 * kGuardS; }
  void setRung(int r) { link_.rung = r; radio_->setRung(r); }

  void linkTick(double now) {
    uint8_t order[kMaxCalendar];
    int n;
    if (snd_ && !snd_->finished()) n = snd_->scanOrderOrRendezvous(order); else n = rx_.scanOrder(order);
    LinkEvent ev[4];
    const int before = link_.rung;
    link_.tick(now, order, n, true, ev);
    if (link_.rung != before) radio_->setRung(link_.rung);
  }
  void scheduleFrame(const uint8_t* f, size_t n, double at, int rungAfter) {
    reply_.pending = true; reply_.kind = Rep::Frame; reply_.at = at; reply_.len = n > sizeof(reply_.buf) ? sizeof(reply_.buf) : n; reply_.rungAfter = rungAfter;
    memcpy(reply_.buf, f, reply_.len);
  }
  void scheduleReport(Rep::Kind k, double at) {
    if (reply_.pending && reply_.kind == Rep::Frame) return;     // una risposta a una richiesta ha la precedenza
    reply_.pending = true; reply_.kind = k; reply_.at = at; reply_.rungAfter = -1;
    if (k == Rep::Status) dataIdleAt_ = -1; else probeIdleAt_ = -1;
  }
  void idleTimers(double now) {
    if (dataIdleAt_ > 0 && now >= dataIdleAt_) { dataIdleAt_ = -1; if (rx_.windowHeard()) scheduleReport(Rep::Status, now); }
    if (probeIdleAt_ > 0 && now >= probeIdleAt_) { probeIdleAt_ = -1; if (rx_.probesHeard()) scheduleReport(Rep::Probe, now); }
  }
  void sendReply(double now) {
    (void)now;
    size_t n = reply_.len;
    if (reply_.kind == Rep::Status) n = rx_.status(reply_.buf, sizeof(reply_.buf));
    else if (reply_.kind == Rep::Probe) n = rx_.probeReport(reply_.buf, sizeof(reply_.buf));
    reply_.pending = false;
    if (n == 0) return;
    startTx(reply_.buf, n, Tx::Reply);
  }
  void startTx(const uint8_t* f, size_t n, Tx kind) {
    txKind_ = kind;
    txBusy_ = true;
    if (!radio_->transmit(f, n)) { txBusy_ = false; txKind_ = Tx::None; }   // la radio non ha accettato: il protocollo se ne accorge dai tempi
  }

  // ----- il mittente -----
  void begin(const Action& a, double now) {
    ex_.act = a;
    switch (a.kind) {
      case Action::None: ex_.st = Exec::Idle; break;
      case Action::Exchange: ex_.st = Exec::Sending; ex_.triesLeft = a.tries; ex_.expect = a.expect; ex_.notBefore = now; break;
      case Action::ModeSet: ex_.st = Exec::Sending; ex_.triesLeft = 1; ex_.expect = MODE_ACK; ex_.notBefore = now; break;
      case Action::Probe: case Action::Burst: ex_.st = Exec::Sending; ex_.sent = 0; ex_.notBefore = now; break;
      case Action::Status: ex_.st = Exec::WaitReply; ex_.expect = STATUS; ex_.deadline = now + idleData() + replyWait(); break;
      case Action::Wait: ex_.st = Exec::Timer; ex_.deadline = now + a.seconds; break;
      case Action::Rand: ans_ = Answer(); ans_.kind = Answer::Rnd; ans_.rnd = radio_->random(); ex_.st = Exec::Resume; break;
      case Action::SetRung: setRung(a.target); ans_ = Answer(); ex_.st = Exec::Resume; break;
      case Action::HoldClear: link_.hold = false; ans_ = Answer(); ex_.st = Exec::Resume; break;
      case Action::Legacy: default: ans_ = Answer(); ex_.st = Exec::Resume; break;       // la vecchia ricerca a R10 non esiste nel firmware
    }
  }
  void driveSender(double now) {
    for (int guard = 0; guard < 16; guard++) {
      switch (ex_.st) {
        case Exec::Resume: {
          const Action a = snd_->resume(ans_, now, link_.rung, link_.lost);
          ans_ = Answer();
          begin(a, now);
          if (snd_->finished()) { ex_.st = Exec::Idle; return; }
          continue;
        }
        case Exec::Sending: {
          if (now < ex_.notBefore) return;
          uint8_t buf[260];
          size_t n = 0;
          if (ex_.act.kind == Action::Exchange || ex_.act.kind == Action::ModeSet) { memcpy(buf, ex_.act.frame, ex_.act.len); n = ex_.act.len; }
          else {
            const FrameRes fr = snd_->frameAt(ex_.act, ex_.sent, buf, sizeof(buf), &n);
            if (fr == FR_PENDING) { ex_.notBefore = now + kPendingRetryS; return; }      // i byte non sono ancora arrivati dal telefono
            if (fr == FR_ERR) { ans_ = Answer(); ex_.st = Exec::Resume; continue; }
          }
          if (ex_.act.kind == Action::Probe || ex_.act.kind == Action::Burst) ex_.sent++;
          startTx(buf, n, Tx::Sender);
          return;
        }
        case Exec::WaitReply:
          if (now < ex_.deadline) return;
          if ((ex_.act.kind == Action::Exchange || ex_.act.kind == Action::ModeSet) && --ex_.triesLeft > 0) {
            ex_.st = Exec::Sending; ex_.notBefore = now + kGuardS;      // un altro tentativo dopo una commutazione
            return;
          }
          ans_ = Answer();                                                 // nessuna risposta
          ex_.st = Exec::Resume;
          continue;
        case Exec::Timer:
          if (now < ex_.deadline) return;
          ans_ = Answer();
          ex_.st = Exec::Resume;
          continue;
        default: return;
      }
    }
  }

  Radio* radio_;
  bool sx1262_, tcxo_;
  int window_;
  uint16_t unsupported_;
  double khz_;
  uint8_t call_[kMaxCall + 1];
  size_t callLen_ = 0;
  Link link_;
  Receiver rx_;
  alignas(Sender) unsigned char sndMem_[sizeof(Sender)];
  Sender* snd_ = nullptr;
  MemSource mem_{nullptr, 0};
  Exec ex_;
  Answer ans_;
  Pending reply_;
  bool txBusy_ = false;
  double lastRssi_ = 0, lastSnr_ = 0, lastRxAt_ = -1e9;
  uint32_t rxFrames_ = 0;
  Tx txKind_ = Tx::None;
  double dataIdleAt_ = -1, probeIdleAt_ = -1;
};

}  // namespace img
}  // namespace v3
