// Firmware V3, scheda MOBILE: ponte Bluetooth LE fra il telefono e il protocollo radio. STUDIO.
// Spec: docs/ble-telefono.md. Il nucleo (src/ble_bridge.h) e' provato sul PC contro il riferimento Python; questo guscio lo collega al BLE (NimBLE).
// LA RADIO NON C'E': i blocchi "partono" secondo il modello a tempo del nucleo (si vedono sulla seriale). Il telefono vede consegna, avanzamento e tempi come con la radio vera.
// Mai eseguito su una scheda. Nessuna microSD (il buffer e' il telefono).
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Preferences.h>

#include "ble_bridge.h"
#include "img_proto.h"
#include "limits.h"

#if defined(RADIO_SX1262)
constexpr bool kSx1262 = true;
#else
constexpr bool kSx1262 = false;
#endif
constexpr bool kTcxo = false;               // il TCXO non si legge ancora dalla scheda: senza, R12-R14 non si annunciano (docs/confronto-datasheet.md)
constexpr int kRung = 5;                    // gradino del modello a tempo (R5 = LoRa 250 kHz / SF7)

// UUID del servizio (docs/ble-telefono.md)
static const char* kService = "c49a1433-9f1b-4af8-9826-951953e47edb";
static const char* kCmd = "c49a1434-9f1b-4af8-9826-951953e47edb";
static const char* kDataIn = "c49a1435-9f1b-4af8-9826-951953e47edb";
static const char* kEvt = "c49a1436-9f1b-4af8-9826-951953e47edb";
static const char* kDataOut = "c49a1437-9f1b-4af8-9826-951953e47edb";

// ---------------------------------------------------------------- coda fra i callback del BLE (altro task) e il ponte (loop)
struct Frame { uint8_t kind; uint8_t len; uint8_t d[250]; };      // kind: 0 comando, 1 dati, 2 collegato, 3 scollegato
constexpr int kQueue = 24;
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

// ---------------------------------------------------------------- il ponte e dove escono le notifiche
struct BleSink : v3::ble::Sink {
  void evt(const uint8_t* d, size_t n) override {
    if (!bleConnected || !chEvt) return;
    chEvt->setValue(d, n);
    chEvt->notify();
    Serial.printf("[evt] %02x len %u\n", d[0], static_cast<unsigned>(n));
  }
  void radioBlock(uint16_t obj, uint16_t blk, const uint8_t*, size_t n, bool again) override {
    Serial.printf("[radio simulata] oggetto %u blocco %u (%u byte)%s\n", obj, blk, static_cast<unsigned>(n), again ? " RITRASMESSO" : "");
  }
  void rxObject(uint16_t obj, const uint8_t* d, size_t n) override {
    // Un oggetto dalla radio al telefono: a pezzi da 100 byte con offset (obj 2, offset 3, byte). Solo con il telefono collegato.
    if (!bleConnected || !chDataOut) return;
    for (size_t off = 0; off < n; off += 100) {
      uint8_t f[105];
      const size_t k = (n - off) < 100 ? (n - off) : 100;
      f[0] = obj >> 8; f[1] = obj & 255; f[2] = (off >> 16) & 255; f[3] = (off >> 8) & 255; f[4] = off & 255;
      memcpy(f + 5, d + off, k);
      chDataOut->setValue(f, 5 + k);
      chDataOut->notify();
      delay(8);
    }
  }
};
static BleSink sink;
static v3::ble::Bridge* bridge = nullptr;
static Preferences prefs;
static char call[13] = "";

static void applyCall(const char* c) {
  strncpy(call, c, sizeof(call) - 1);
  call[sizeof(call) - 1] = 0;
  if (bridge) bridge->setCall(call);
}

static void handleSerial() {
  static char line[40];
  static int n = 0;
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r' || c == '\n') {
      line[n] = 0;
      n = 0;
      if (!strncmp(line, "CALL ", 5) || !strncmp(line, "call ", 5)) {
        char c2[13];
        int k = 0;
        for (const char* p = line + 5; *p && k < 12; p++) if (*p != ' ') c2[k++] = static_cast<char>(toupper(*p));
        c2[k] = 0;
        prefs.putString("call", c2);
        applyCall(c2);
        Serial.printf("OK nominativo %s\n", call);
      } else if (!strncmp(line, "STATO", 5) || !strncmp(line, "stato", 5)) {
        const v3::ble::Stats& s = bridge->stats();
        Serial.printf("nominativo %s, BLE %s, oggetto in corso %s, RAM %u byte, richieste %u (ripetute %u), blocchi %u, scartati %u, coda persa %u\n", call[0] ? call : "(manca: CALL xxx)",
                      bleConnected ? "collegato" : "scollegato", bridge->busy() ? "si" : "no", static_cast<unsigned>(bridge->held()), s.pulls, s.repulls, s.blocksSent, s.dropped, static_cast<unsigned>(qDropped));
      } else if (line[0]) Serial.println("comandi: CALL <nominativo> | STATO");
    } else if (n < static_cast<int>(sizeof(line)) - 1) line[n++] = c;
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("\nVoLoRa V3 mobile (STUDIO: radio simulata) %s\n", kSx1262 ? "SX1262" : "SX1278");
  prefs.begin("vl3", false);
  const String saved = prefs.getString("call", "");
  strncpy(call, saved.c_str(), sizeof(call) - 1);
  const uint16_t rungMask = v3::rungMask(kSx1262, kTcxo);       // SX1278: R0-R11 (0x0FFF); SX1262: R1-R11 (0x0FFE); con TCXO anche R12-R14
  bridge = new v3::ble::Bridge(&sink, call, kSx1262, kRung, rungMask);
  Serial.printf("gradini annunciati: 0x%04X\n", rungMask);
  Serial.printf("protocollo immagini (non ancora collegato alla radio): mittente %u byte, ricevitore %u byte, collegamento %u byte di RAM\n", static_cast<unsigned>(sizeof(v3::img::Sender)),
                static_cast<unsigned>(sizeof(v3::img::Receiver)), static_cast<unsigned>(sizeof(v3::img::Link)));
  Serial.printf("nominativo: %s\n", call[0] ? call : "(non impostato: scrivi CALL IU5HJU)");

  passkey = 100000 + (esp_random() % 900000);           // codice a 6 cifre per l'accoppiamento (sulla seriale; lo schermo OLED dopo)
  NimBLEDevice::init("VoLoRa-V3");
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
  static uint32_t last = millis();
  Frame f;
  while (pop(&f)) {
    if (f.kind == 0) bridge->onCommand(f.d, f.len);
    else if (f.kind == 1) bridge->onData(f.d, f.len);
    else if (f.kind == 2) { bleConnected = true; bridge->onConnect(); Serial.println("[ble] telefono collegato"); }
    else { bleConnected = false; bridge->onDisconnect(); Serial.println("[ble] telefono scollegato"); }
  }
  const uint32_t now = millis();
  const double dt = (now - last) / 1000.0;
  last = now;
  bridge->tick(dt);
  handleSerial();
  delay(5);
}
