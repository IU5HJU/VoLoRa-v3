// Driver radio per la scheda (RadioLib): implementa v3::img::Radio per il mezzo (medium.h). SX1278 sulla T3, SX1262 sul T-Beam. STUDIO: mai eseguito su una scheda.
// Ogni gradino (docs/protocollo-immagini.md, punto 3) e' un modo LoRa (banda, SF, CR 4/5) o FSK (bit rate, deviazione, filtro di ricezione); cambiare gradino riconfigura la radio e la
// rimette in ascolto. Non supportato: R3 (LoRa 500/SF6) sull'SX1278, che vuole l'intestazione implicita (lunghezza fissa): il firmware non lo annuncia.
#pragma once
#include <Arduino.h>
#include <RadioLib.h>

#include "board.h"
#include "boost.h"
#include "medium.h"

#if defined(RADIO_SX1262)
#define VL3_CHIP "SX1262"
constexpr bool kBoardSx1262 = true;
static SX1262 vl3Radio = new Module(pins::kRadioCs, pins::kRadioDio1, pins::kRadioRst, pins::kRadioBusy);
#else
#define VL3_CHIP "SX1278"
constexpr bool kBoardSx1262 = false;
static SX1278 vl3Radio = new Module(pins::kRadioCs, pins::kRadioDio0, pins::kRadioRst, pins::kRadioDio1);
#endif

namespace v3 {
namespace img {

constexpr float kFreqMhz = 433.700f;     // canale di incontro (docs/band-plan.md): liberamente configurabile nel campo del chip
constexpr int kPowerDbm = boost::kNormalDbm;   // +17 dBm: massimo in continuo dell'SX1278 (docs/confronto-datasheet.md); con BOOST +20 dBm (boost.h)
constexpr uint8_t kSyncWord = 0x5D;      // diverso da quello della v2

static volatile bool vl3Irq = false;
static void IRAM_ATTR vl3OnIrq() { vl3Irq = true; }

class BoardRadio : public Radio {
 public:
  bool begin() { return setRungImpl(kRendezvous); }
  void setRung(int r) override { rung_ = r; ok_ = setRungImpl(r); }
  bool transmit(const uint8_t* f, size_t n) override {
    if (!ok_) return false;
    const int st = vl3Radio.startTransmit(f, n);
    if (st != RADIOLIB_ERR_NONE) { Serial.printf("[radio] startTransmit errore %d\n", st); return false; }
    txBusy_ = true;
    if (boost_.txStarted(millis(), static_cast<uint32_t>(frameAirtimeS(rung_, static_cast<int>(n)) * 1e6)))
      Serial.printf("ATTENZIONE BOOST: ciclo di lavoro %.1f%% su %d s, oltre %.0f%% (rischio calore e danno alla radio). BOOST OFF per tornare a +%d dBm\n", boost_.duty(millis()), boost::DutyGuard::kBuckets, boost::kDutyMaxPct, boost::kNormalDbm);
    return true;
  }
  // ----- BOOST (+20 dBm, estrema, docs/boost.md): sempre spento all'avvio, non si salva, non si spegne da solo -----
  const boost::State& boostState() const { return boost_; }
  // Un comando seriale "BOOST ..." o "IOF ...". Ritorna false se la riga non e' uno dei due.
  bool boostCommand(const char* line) {
    const boost::Cmd c = boost::parse(line), ci = boost::parseIof(line);
    if (c == boost::Cmd::Invalid && ci == boost::Cmd::Invalid) {
      if (!strncasecmp(line, "BOOST", 5)) { Serial.println("ERR BOOST ON RISCHIO | BOOST OFF | BOOST STATUS"); return true; }
      if (!strncasecmp(line, "IOF", 3)) { Serial.println("ERR IOF ON RISCHIO | IOF OFF | IOF STATUS (solo SX1262)"); return true; }
      return false;
    }
    if (c == boost::Cmd::NeedsAck) { Serial.println(boost::kWarning); Serial.println("ERR BOOST non attivato: scrivi BOOST ON RISCHIO"); return true; }
    if (c == boost::Cmd::On) { boost_.enable(); applyPower(); Serial.println(boost::kWarning); Serial.printf("BOOST ATTIVO (RISCHIO): +%d dBm\n", boost_.power()); return true; }
    if (ci == boost::Cmd::NeedsAck) {
      Serial.println(boost::kIofWarning);
      Serial.println(kBoardSx1262 ? "ERR IOF MODE non attivato: scrivi IOF ON RISCHIO" : "ERR IOF MODE esiste solo sull'SX1262: questa scheda ha l'SX1278 (massimo +20 dBm con BOOST)");
      return true;
    }
    if (ci == boost::Cmd::On) {
      if (!boost_.enableIof()) { Serial.println("ERR IOF MODE esiste solo sull'SX1262: questa scheda ha l'SX1278 (massimo +20 dBm con BOOST)"); return true; }
      applyPower(); Serial.println(boost::kIofWarning); Serial.printf("IOF MODE ATTIVO (RISCHIO): +%d dBm\n", boost_.power()); return true;
    }
    if (c == boost::Cmd::Off || ci == boost::Cmd::Off) { boost_.disable(); applyPower(); Serial.printf("potenza normale: +%d dBm\n", boost_.power()); return true; }
    Serial.printf("%s, potenza %d dBm, ciclo di lavoro %.2f%% su %d s\n", boost_.iofOn() ? "IOF MODE ATTIVO (RISCHIO)" : boost_.boostOn() ? "BOOST ATTIVO (RISCHIO)" : "potenza normale", boost_.power(), boost_.duty(millis()), boost::DutyGuard::kBuckets);
    return true;
  }
  double random() override { return esp_random() / 4294967296.0; }
  int rung() const { return rung_; }
  // da chiamare spesso nel loop: gestisce l'interrupt della radio (fine trasmissione o pacchetto ricevuto)
  void service(Station& st, double now) {
    if (!vl3Irq) return;
    vl3Irq = false;
    if (txBusy_) {
      txBusy_ = false;
      vl3Radio.finishTransmit();
      vl3Radio.startReceive();
      st.onTxDone(now);
      return;
    }
    const size_t n = vl3Radio.getPacketLength();
    uint8_t buf[256];
    if (n == 0 || n > sizeof(buf)) { vl3Radio.startReceive(); return; }
    const int s = vl3Radio.readData(buf, n);
    const double rssi = vl3Radio.getRSSI();
#if defined(RADIO_SX1262)
    const double snr = kRungs[rung_].lora ? vl3Radio.getSNR() : rssi - noiseFloorDbm(rung_);
#else
    const double snr = kRungs[rung_].lora ? vl3Radio.getSNR() : rssi - noiseFloorDbm(rung_);
#endif
    vl3Radio.startReceive();
    if (s == RADIOLIB_ERR_NONE) st.onRx(buf, n, rssi, snr, now);
    else rxErrors_++;
  }
  uint32_t rxErrors() const { return rxErrors_; }

 private:
  // potenza e limite di corrente (a +20 dBm servono circa 120 mA: il limite di base della radio e' piu' basso)
  void limitCurrent() { if (boost_.on()) vl3Radio.setCurrentLimit(boost::kOcpMa); }
  void applyPower() {
    if (!ok_) return;
    const int st = vl3Radio.setOutputPower(boost_.power());
    if (st != RADIOLIB_ERR_NONE) Serial.printf("[radio] potenza %d dBm errore %d\n", boost_.power(), st);
    limitCurrent();
  }
  // il filtro di ricezione FSK: il primo valore permesso dal chip che contiene la banda del segnale piu' l'errore di due quarzi da 10 ppm
  static float fskRxBw(bool sx1262, double br, double dev) {
    static const float ssb[] = {2.6f, 3.1f, 3.9f, 5.2f, 6.3f, 7.8f, 10.4f, 12.5f, 15.6f, 20.8f, 25.0f, 31.3f, 41.7f, 50.0f, 62.5f, 83.3f, 100.0f, 125.0f, 166.7f, 200.0f, 250.0f};      // SX1278: banda laterale singola
    static const float dsb[] = {4.8f, 5.8f, 7.3f, 9.7f, 11.7f, 14.6f, 19.5f, 23.4f, 29.3f, 39.0f, 46.9f, 58.6f, 78.2f, 93.8f, 117.3f, 156.2f, 187.2f, 234.3f, 312.0f, 373.6f, 467.0f};    // SX1262: doppia banda
    const double need = br + 2 * dev + 2 * (2 * 10e-6 * kFreqMhz * 1000.0);
    const float* t = sx1262 ? dsb : ssb;
    const double want = sx1262 ? need : need / 2;
    for (int i = 0; i < 21; i++) if (t[i] >= want) return t[i];
    return t[20];
  }
  bool setRungImpl(int rung) {
    const Rung& r = kRungs[rung];
    int st;
    if (r.lora) {
#if defined(RADIO_SX1262)
      st = vl3Radio.begin(kFreqMhz, static_cast<float>(r.a), static_cast<uint8_t>(r.b), 5, kSyncWord, boost_.power(), 8, 1.6f);
      if (st == RADIOLIB_ERR_NONE) st = vl3Radio.setCRC(true);
#else
      if (r.b == 6) { Serial.println("[radio] R3 (SF6) non supportato sull'SX1278: serve l'intestazione implicita"); return false; }
      st = vl3Radio.begin(kFreqMhz, static_cast<float>(r.a), static_cast<uint8_t>(r.b), 5, kSyncWord, boost_.power(), 8);
      if (st == RADIOLIB_ERR_NONE) st = vl3Radio.setCRC(true);
#endif
    } else {
#if defined(RADIO_SX1262)
      st = vl3Radio.beginFSK(kFreqMhz, static_cast<float>(r.a), static_cast<float>(r.b), fskRxBw(true, r.a, r.b), boost_.power(), 16, 1.6f);
      if (st == RADIOLIB_ERR_NONE) st = vl3Radio.variablePacketLengthMode(255);
      if (st == RADIOLIB_ERR_NONE) st = vl3Radio.setCRC(2);
#else
      st = vl3Radio.beginFSK(kFreqMhz, static_cast<float>(r.a), static_cast<float>(r.b), fskRxBw(false, r.a, r.b), boost_.power(), 16, false);
      if (st == RADIOLIB_ERR_NONE) st = vl3Radio.variablePacketLengthMode(64);
      if (st == RADIOLIB_ERR_NONE) st = vl3Radio.setCRC(true);
#endif
    }
    if (st != RADIOLIB_ERR_NONE) { Serial.printf("[radio] configurazione R%d errore %d\n", rung, st); return false; }
    limitCurrent();
    vl3Radio.setPacketSentAction(vl3OnIrq);
    vl3Radio.setPacketReceivedAction(vl3OnIrq);
    txBusy_ = false;
    vl3Irq = false;
    return vl3Radio.startReceive() == RADIOLIB_ERR_NONE;
  }
  int rung_ = kRendezvous;
  bool ok_ = false, txBusy_ = false;
  uint32_t rxErrors_ = 0;
  boost::State boost_{kBoardSx1262};
};

}  // namespace img
}  // namespace v3
