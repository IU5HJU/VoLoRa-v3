// Firmware V3, scheda MOBILE COMPLETA: telefono (Bluetooth LE) -> ponte -> mezzo -> radio vera, e radio -> ponte -> telefono. STUDIO: mai eseguito su una scheda.
// Spec: docs/ble-telefono.md. Nucleo: src/live_bridge.h (ponte collegato al mezzo), src/medium.h (stazione), src/radio_board.h (driver RadioLib).
// Il buffer e' il telefono: la scheda tiene 8 blocchi da 1 kB e li chiede a richiesta (E_PULL); nessuna microSD. Gli oggetti dalla radio si accettano solo col telefono collegato.
// Seriale a 115200 baud: CALL <nominativo> | STATO. Il codice di accoppiamento BLE si stampa all'avvio.
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Preferences.h>
#include <SPI.h>
#include <esp_timer.h>

#include "freq.h"
#include "live_bridge.h"
#include "pmu.h"
#include "radio_board.h"

using namespace v3;
using namespace v3::img;

constexpr bool kTcxo = false;                 // il TCXO non si legge ancora dalla scheda: senza, R12-R14 non si annunciano (docs/confronto-datasheet.md)
constexpr size_t kRxMax = 32768;              // oggetti dalla radio: fino a 32 kB (RAM della scheda)

static const char* kService = "c49a1433-9f1b-4af8-9826-951953e47edb";
static const char* kCmd = "c49a1434-9f1b-4af8-9826-951953e47edb";
static const char* kDataIn = "c49a1435-9f1b-4af8-9826-951953e47edb";
static const char* kEvt = "c49a1436-9f1b-4af8-9826-951953e47edb";
static const char* kDataOut = "c49a1437-9f1b-4af8-9826-951953e47edb";

// ---------------------------------------------------------------- coda fra i callback del BLE (altro task) e il ciclo principale
struct Frame { uint8_t kind; uint8_t len; uint8_t d[250]; };      // kind: 0 comando, 1 dati, 2 collegato, 3 scollegato
constexpr int kQueue = 32;
static Frame queue[kQueue];
static volatile int qHead = 0, qTail = 0;
static volatile uint32_t qDropped = 0;
static portMUX_TYPE qMux = portMUX_INITIALIZER_UNLOCKED;

static void push(uint8_t kind, const uint8_t* d, size_t n) {
  if (n > sizeof(queue[0].d)) { qDropped++; return; }
  portENTER_CRITICAL(&qMux);
  const int next = (qHead + 1) % kQueue;
  if (next == qTail) { qDropped++; portEXIT_CRITICAL(&qMux); return; }
  queue[qHead].kind = kind;
  queue[qHead].len = static_cast<uint8_t>(n);
  if (n) memcpy(queue[qHead].d, d, n);
  qHead = next;
  portEXIT_CRITICAL(&qMux);
}
static bool pop(Frame* out) {
  bool ok = false;
  portENTER_CRITICAL(&qMux);
  if (qTail != qHead) { *out = queue[qTail]; qTail = (qTail + 1) % kQueue; ok = true; }
  portEXIT_CRITICAL(&qMux);
  return ok;
}

// ---------------------------------------------------------------- BLE
static NimBLECharacteristic* chEvt = nullptr;
static NimBLECharacteristic* chDataOut = nullptr;
static bool bleConnected = false;
static uint32_t passkey = 0;

class ServerCb : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer*, ble_gap_conn_desc*) override { push(2, nullptr, 0); }
  void onDisconnect(NimBLEServer*) override { push(3, nullptr, 0); NimBLEDevice::startAdvertising(); }
  uint32_t onPassKeyRequest() override { return passkey; }
  void onAuthenticationComplete(ble_gap_conn_desc* desc) override { Serial.printf("[ble] accoppiamento %s\n", desc->sec_state.encrypted ? "completato (cifrato)" : "NON cifrato"); }
};
class CmdCb : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c) override { const std::string v = c->getValue(); push(0, reinterpret_cast<const uint8_t*>(v.data()), v.size()); }
};
class DataCb : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c) override { const std::string v = c->getValue(); push(1, reinterpret_cast<const uint8_t*>(v.data()), v.size()); }
};

struct PhoneSink : ble::LiveSink {
  void evt(const uint8_t* d, size_t n) override {
    if (!bleConnected || !chEvt) return;
    chEvt->setValue(d, n);
    chEvt->notify();
  }
  void rxChunk(uint16_t obj, uint32_t off, const uint8_t* d, size_t n) override {
    // dalla radio al telefono: obj(2) offset(3) byte, a pezzi piccoli (MTU minimo 64)
    if (!bleConnected || !chDataOut || n > 100) return;
    uint8_t f[105];
    f[0] = obj >> 8; f[1] = obj & 255; f[2] = (off >> 16) & 255; f[3] = (off >> 8) & 255; f[4] = off & 255;
    memcpy(f + 5, d, n);
    chDataOut->setValue(f, 5 + n);
    chDataOut->notify();
    delay(3);
  }
};
static PhoneSink phone;

// ---------------------------------------------------------------- RAM per gli oggetti che arrivano dalla radio
static uint8_t rxBuf[kRxMax];
static uint8_t rxLen[kRxMax / kPiece];
static uint16_t rxPieces = 0;
struct RamStore : Store {
  void reset(uint16_t n) override { rxPieces = n > kRxMax / kPiece ? kRxMax / kPiece : n; memset(rxLen, 0, sizeof(rxLen)); }
  void put(uint16_t i, const uint8_t* d, size_t n) override { if (i < rxPieces && n <= kPiece) { memcpy(rxBuf + static_cast<size_t>(i) * kPiece, d, n); rxLen[i] = static_cast<uint8_t>(n); } }
  size_t get(uint16_t i, uint8_t* out) override { if (i >= rxPieces) return 0; memcpy(out, rxBuf + static_cast<size_t>(i) * kPiece, rxLen[i]); return rxLen[i]; }
};
static RamStore store;

static BoardRadio radio;
static Station* station = nullptr;
static ble::LiveBridge* bridge = nullptr;
static Preferences prefs;
static char call[13] = "";

// Nome Bluetooth: "VoLoRa-V3 <NOMINATIVO>", cosi' si riconoscono piu' schede (senza nominativo: "VoLoRa-V3"). Cambia con CALL: la scheda si riavvia per annunciarlo.
static String bleName() { return call[0] ? String("VoLoRa-V3 ") + call : String("VoLoRa-V3"); }

static double nowS() { return esp_timer_get_time() / 1e6; }

static void rebuild() {
  if (!call[0]) return;
  delete bridge;
  delete station;
  station = new Station(reinterpret_cast<const uint8_t*>(call), strlen(call), kBoardSx1262, kTcxo, &radio, &store, kWindowFrames, true,
                        kBoardSx1262 ? 0 : static_cast<uint16_t>(1u << 3), radio.frequencyKhz());     // R3 (LoRa 500/SF6) sull'SX1278 vuole l'intestazione implicita: il driver non lo fa
  bridge = new ble::LiveBridge(&phone, station, call, kBoardSx1262, rungMask(kBoardSx1262, kTcxo, radio.frequencyKhz()) & ~(kBoardSx1262 ? 0u : (1u << 3)), &store, kRxMax);
  if (bleConnected) bridge->onConnect(); else bridge->onDisconnect();
}

static void handleSerial() {
  static char line[40];
  static int n = 0;
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r' || c == '\n') {
      line[n] = 0;
      n = 0;
      if (!strncasecmp(line, "CALL ", 5)) {
        char c2[13];
        int k = 0;
        for (const char* p = line + 5; *p && k < 8; p++) if (*p != ' ') c2[k++] = static_cast<char>(toupper(*p));
        c2[k] = 0;
        if (station && station->sending()) { Serial.println("ERR invio in corso"); continue; }
        const bool changed = strcmp(call, c2) != 0;
        prefs.putString("call", c2);
        strncpy(call, c2, sizeof(call) - 1);
        rebuild();
        Serial.printf("OK nominativo %s\n", call);
        if (changed) { Serial.printf("riavvio per annunciare il nome Bluetooth \"%s\"...\n", bleName().c_str()); Serial.flush(); delay(300); ESP.restart(); }
      } else if (const FreqParse fp = parseFreq(line, kBoardSx1262); fp.cmd != FreqCmd::NotFreq) {
        if (fp.cmd == FreqCmd::Show) Serial.printf("frequenza %.3f MHz (campo del chip %s)\n", radio.frequencyKhz() / 1000.0, kBoardSx1262 ? "150-960 MHz" : "137-175 e 410-525 MHz");
        else if (fp.cmd == FreqCmd::Invalid) Serial.printf("ERR FREQ %s\n", fp.why);
        else if (station && station->sending()) Serial.println("ERR invio in corso");
        else if (!radio.setFrequencyKhz(fp.khz)) Serial.println("ERR la radio non accetta questa frequenza");
        else { prefs.putUInt("khz", static_cast<uint32_t>(fp.khz + 0.5)); rebuild(); Serial.printf("OK frequenza %.3f MHz (salvata): impostala uguale sull'altra scheda\n", fp.khz / 1000.0); }
      } else if (radio.boostCommand(line)) {
        // gestito dal driver radio (BOOST ON RISCHIO | OFF | STATUS)
      } else if (!strncasecmp(line, "STATO", 5)) {
        if (!station) { Serial.println("nessun nominativo (CALL xxx)"); continue; }
        const ble::LiveBridge::Stats& s = bridge->stats();
        Serial.printf("%s BLE %s, %.3f MHz, gradino R%d%s, invio %s, in RAM %u byte, richieste %u (ripetute %u), scartati %u, oggetti ricevuti %u, errori radio %u, coda persa %u\n", call, bleConnected ? "collegato" : "scollegato",
                      radio.frequencyKhz() / 1000.0, station->link().rung, station->link().lost ? " (in ricerca)" : "", station->sending() ? "in corso" : "fermo", static_cast<unsigned>(bridge->held()), s.pulls, s.repulls, s.dropped, s.rxObjects,
                      static_cast<unsigned>(radio.rxErrors()), static_cast<unsigned>(qDropped));
      } else if (line[0]) Serial.println("comandi: CALL <nominativo> | FREQ <MHz> | STATO | BOOST|IOF ON RISCHIO|OFF|STATUS");
    } else if (n < static_cast<int>(sizeof(line)) - 1) line[n++] = c;
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("\nVoLoRa V3 mobile con radio vera (STUDIO) %s, %.3f MHz, %d dBm\n", VL3_CHIP, radio.frequencyKhz() / 1000.0, kPowerDbm);
  pmuBegin();
  SPI.begin(pins::kRadioSclk, pins::kRadioMiso, pins::kRadioMosi, pins::kRadioCs);
  Serial.println(radio.begin() ? "radio pronta a R10" : "ERRORE: la radio non parte");
  prefs.begin("vl3", false);
  { const uint32_t k = prefs.getUInt("khz", 0); if (k && !radio.setFrequencyKhz(k)) Serial.printf("frequenza salvata %u kHz non valida: resta %.3f MHz\n", static_cast<unsigned>(k), radio.frequencyKhz() / 1000.0); }
  const String saved = prefs.getString("call", "");
  strncpy(call, saved.c_str(), sizeof(call) - 1);
  rebuild();
  Serial.printf("nominativo: %s\n", call[0] ? call : "(non impostato: scrivi CALL IU5HJU)");

  passkey = 100000 + (esp_random() % 900000);           // codice a 6 cifre per l'accoppiamento (sulla seriale; lo schermo OLED dopo)
  NimBLEDevice::init(bleName().c_str());
  Serial.printf("nome Bluetooth: %s\n", bleName().c_str());
  NimBLEDevice::setMTU(185);
  NimBLEDevice::setSecurityAuth(true, true, true);       // bonding, MITM, connessioni sicure LE: niente "Just Works"
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY);
  NimBLEDevice::setSecurityPasskey(passkey);
  NimBLEServer* server = NimBLEDevice::createServer();
  static ServerCb serverCb;
  server->setCallbacks(&serverCb);
  NimBLEService* svc = server->createService(kService);
  static CmdCb cmdCb;
  static DataCb dataCb;
  NimBLECharacteristic* cmd = svc->createCharacteristic(kCmd, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_ENC | NIMBLE_PROPERTY::WRITE_AUTHEN);
  cmd->setCallbacks(&cmdCb);
  NimBLECharacteristic* dataIn = svc->createCharacteristic(kDataIn, NIMBLE_PROPERTY::WRITE_NR | NIMBLE_PROPERTY::WRITE_ENC | NIMBLE_PROPERTY::WRITE_AUTHEN);
  dataIn->setCallbacks(&dataCb);
  chEvt = svc->createCharacteristic(kEvt, NIMBLE_PROPERTY::NOTIFY);
  chDataOut = svc->createCharacteristic(kDataOut, NIMBLE_PROPERTY::NOTIFY);
  svc->start();
  NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
  adv->addServiceUUID(kService);
  adv->setScanResponse(true);
  adv->start();
  Serial.printf("BLE acceso. Codice di accoppiamento: %06u\n", static_cast<unsigned>(passkey));
}

void loop() {
  Frame f;
  while (pop(&f)) {
    if (f.kind == 2) { bleConnected = true; if (bridge) bridge->onConnect(); Serial.println("[ble] telefono collegato"); }
    else if (f.kind == 3) { bleConnected = false; if (bridge) bridge->onDisconnect(); Serial.println("[ble] telefono scollegato"); }
    else if (bridge) { if (f.kind == 0) bridge->onCommand(f.d, f.len); else bridge->onData(f.d, f.len); }
  }
  handleSerial();
  if (!station) { delay(5); return; }
  const double now = nowS();
  radio.service(*station, now);
  station->poll(now);
  bridge->poll(now);
  delay(1);
}
