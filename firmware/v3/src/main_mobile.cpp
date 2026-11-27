// Firmware V3, scheda MOBILE COMPLETA: telefono -> ponte -> mezzo -> radio vera, e radio -> ponte -> telefono. STUDIO: mai eseguito su una scheda.
// Il telefono si collega in due modi (stesso protocollo di comandi ed eventi, docs/ble-telefono.md):
//  - VL3_WIFI=1 (ambienti mobile_*): la scheda crea il suo Wi-Fi "VoLoRa-<NOMINATIVO>", SERVE LA PAGINA DEL TELEFONO (incorporata nel firmware, niente Internet) su http://192.168.4.1
//    e parla con la pagina via WebSocket (/ws). Non serve Web Bluetooth, che vuole una pagina https.
//  - VL3_WIFI=0 (ambienti mobile_ble_*): Bluetooth LE, con la pagina da Internet. Nucleo: src/live_bridge.h (ponte collegato al mezzo), src/medium.h (stazione), src/radio_board.h (driver RadioLib).
// Il buffer e' il telefono: la scheda tiene 8 blocchi da 1 kB e li chiede a richiesta (E_PULL); nessuna microSD. Gli oggetti dalla radio si accettano solo col telefono collegato.
// Seriale a 115200 baud: CALL <nominativo> | STATO. Il codice di accoppiamento BLE si stampa all'avvio.
#include <Arduino.h>
#ifndef VL3_WIFI
#define VL3_WIFI 0
#endif
#if VL3_WIFI
#include <DNSServer.h>
#include <ESPAsyncWebServer.h>
#include <WiFi.h>

#include "web_assets.h"
#else
#include <NimBLEDevice.h>
#endif
#include <Preferences.h>
#include <SPI.h>
#include <esp_timer.h>

#include "battery_board.h"
#include "display_oled.h"
#include "freq.h"
#include "gps_board.h"
#include "position.h"
#include "live_bridge.h"
#include "pmu.h"
#include "radio_board.h"
#include "testlog.h"

using namespace v3;
using namespace v3::img;

#ifndef LCR_VERSION
#define LCR_VERSION "dev"
#endif
constexpr bool kTcxo = false;                 // il TCXO non si legge ancora dalla scheda: senza, R12-R14 non si annunciano (docs/confronto-datasheet.md)
constexpr size_t kRxMax = 32768;              // oggetti dalla radio: fino a 32 kB (RAM della scheda)

#if !VL3_WIFI
static const char* kService = "c49a1433-9f1b-4af8-9826-951953e47edb";
static const char* kCmd = "c49a1434-9f1b-4af8-9826-951953e47edb";
static const char* kDataIn = "c49a1435-9f1b-4af8-9826-951953e47edb";
static const char* kEvt = "c49a1436-9f1b-4af8-9826-951953e47edb";
static const char* kDataOut = "c49a1437-9f1b-4af8-9826-951953e47edb";
#endif

// ---------------------------------------------------------------- coda fra i callback del BLE (altro task) e il ciclo principale
struct Frame { uint8_t kind; uint8_t len; uint8_t d[250]; };      // kind: 0 comando, 1 dati, 2 collegato, 3 scollegato
constexpr int kQueue = 48;                    // i messaggi del WebSocket arrivano a raffica
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

// ---------------------------------------------------------------- collegamento col telefono: Bluetooth LE
#if !VL3_WIFI
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
static void linkEvt(const uint8_t* d, size_t n) { if (!chEvt) return; chEvt->setValue(d, n); chEvt->notify(); }
static void linkData(const uint8_t* d, size_t n) { if (!chDataOut) return; chDataOut->setValue(d, n); chDataOut->notify(); }
static const char* kLinkWord = "Bluetooth";
#else
// ---------------------------------------------------------------- collegamento col telefono: Wi-Fi della scheda (punto di accesso), pagina servita dalla scheda, WebSocket
static AsyncWebServer webServer(80);
static AsyncWebSocket ws("/ws");
static DNSServer dns;
static bool bleConnected = false;                       // (nome storico) telefono collegato
static char wifiSsid[24] = "", wifiPass[12] = "";
static AsyncWebSocketClient* wsClient = nullptr;        // un solo telefono alla volta
static const char* kLinkWord = "Wi-Fi";

// messaggi WebSocket: il primo byte e' il canale (0 comando, 1 dati dal telefono; 2 evento, 3 dati verso il telefono)
static void linkEvt(const uint8_t* d, size_t n) { uint8_t m[260]; if (n + 1 > sizeof(m)) return; m[0] = 2; memcpy(m + 1, d, n); ws.binaryAll(m, n + 1); }
static void linkData(const uint8_t* d, size_t n) { uint8_t m[260]; if (n + 1 > sizeof(m)) return; m[0] = 3; memcpy(m + 1, d, n); ws.binaryAll(m, n + 1); }
static void onWsEvent(AsyncWebSocket*, AsyncWebSocketClient* c, AwsEventType type, void* arg, uint8_t* data, size_t len) {
  if (type == WS_EVT_CONNECT) {
    if (wsClient && wsClient != c && wsClient->status() == WS_CONNECTED) wsClient->close();     // il telefono nuovo prende il posto del vecchio
    wsClient = c;
    push(2, nullptr, 0);
  } else if (type == WS_EVT_DISCONNECT) {
    if (c == wsClient) { wsClient = nullptr; push(3, nullptr, 0); }
  } else if (type == WS_EVT_DATA) {
    const AwsFrameInfo* info = static_cast<const AwsFrameInfo*>(arg);
    if (c != wsClient || !(info->final && info->index == 0 && info->len == len && info->opcode == WS_BINARY) || len < 2) return;
    if (data[0] == 0) push(0, data + 1, len - 1);
    else if (data[0] == 1) push(1, data + 1, len - 1);
  }
}
static void sendGz(AsyncWebServerRequest* r, const char* type, const uint8_t* d, size_t n) {
  AsyncWebServerResponse* resp = r->beginResponse(200, type, d, n);
  resp->addHeader("Content-Encoding", "gzip");
  resp->addHeader("Cache-Control", "no-store");
  r->send(resp);
}
#endif

static v3::TestLog tlog;
static double nowSec() { return esp_timer_get_time() / 1e6; }

// avviso a tempo sul display (riga 38), come gli avvisi della v2
static char noticeText[24] = "";
static uint32_t noticeUntilMs = 0;
static void setNotice(const char* t) { snprintf(noticeText, sizeof(noticeText), "%.21s", t); noticeUntilMs = millis() + v3::disp::kNoticeMs; }

struct PhoneSink : ble::LiveSink {
  void evt(const uint8_t* d, size_t n) override {
    if (n >= 4 && d[0] == ble::E_DONE) setNotice(d[3] == ble::DONE_DELIVERED ? "CONSEGNATO" : d[3] == ble::DONE_CANCELLED ? "ANNULLATO" : "INVIO FALLITO");
    else if (n >= 4 && d[0] == ble::E_ERR) setNotice(d[3] == ble::ERR_NO_POSITION ? "MANCA LA POSIZIONE" : d[3] == ble::ERR_NO_CALL ? "IMPOSTA NOMINATIVO" : d[3] == ble::ERR_BUSY ? "OCCUPATO" : "ERRORE DEL TELEFONO");
    if (!bleConnected) return;
    linkEvt(d, n);
  }
  void log(const char* line) override { tlog.add(nowSec(), line); Serial.printf("[prova] %s\n", line); }
  void rxChunk(uint16_t obj, uint32_t off, const uint8_t* d, size_t n) override {
    // dalla radio al telefono: obj(2) offset(3) byte, a pezzi piccoli (MTU minimo 64)
    if (!bleConnected || n > 100) return;
    uint8_t f[105];
    f[0] = obj >> 8; f[1] = obj & 255; f[2] = (off >> 16) & 255; f[3] = (off >> 8) & 255; f[4] = off & 255;
    memcpy(f + 5, d, n);
    linkData(f, 5 + n);
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
static bool radioOk = false;
static Station* station = nullptr;
static ble::LiveBridge* bridge = nullptr;
static Preferences prefs;
static OledDisplay oled;
static BatteryReader battery;
static GpsBoard gps;
static char call[13] = "";

// Nome Bluetooth: "VoLoRa-V3 <NOMINATIVO>", cosi' si riconoscono piu' schede (senza nominativo: "VoLoRa-V3"). Cambia con CALL: la scheda si riavvia per annunciarlo.
static String bleName() { return call[0] ? String("VoLoRa-V3 ") + call : String("VoLoRa-V3"); }
// Con il Wi-Fi: la rete si chiama "VoLoRa-<NOMINATIVO>" (senza nominativo "VoLoRa-V3"), cosi' con due schede accese si sa quale e' quale
static String wifiName() { return call[0] ? String("VoLoRa-") + call : String("VoLoRa-V3"); }

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

// ----- display: si costruisce lo stato e si ridisegna se cambia (display_model.h) -----
// distanza fra due blocchi di posizione da 7 byte (locatore o GPS); testo vuoto se una delle due non c'e' o non e' valida
static void distanceText(const uint8_t* mine, bool haveMine, const uint8_t* peer, bool havePeer, char* out, size_t cap) {
  out[0] = 0;
  v3::Position a, b;
  if (haveMine && havePeer && v3::positionFromBlock(mine, a) && v3::positionFromBlock(peer, b)) v3::formatDistance(out, cap, v3::distanceKm(a, b));
}

// il GPS della scheda (T-Beam) va al ponte: con un fix la posizione dell'OFFER e' il GPS, senza torna quella del telefono
static void feedGps(uint32_t ms) {
  gps.loop(ms);
  static uint32_t lastMs = 0;
  if (!bridge || ms - lastMs < 1000) return;
  lastMs = ms;
  if (gps.hasFix(ms)) {
    v3::Position p; p.valid = true; p.fromGps = true; p.latE7 = gps.latE7(); p.lonE7 = gps.lonE7();
    uint8_t blk[7];
    if (v3::encodePosition(p, blk)) { bridge->setGps(blk); return; }
  }
  bridge->setGps(nullptr);
}

static void updateDisplay(double now) {
  static int seenDone = 0;
  static char lastCall[16] = "";
  static uint32_t lastBytes = 0, lastAtMs = 0;
  static bool lastOk = true, haveLast = false;
  static char lastDist[12] = "";
  using namespace v3::disp;
  const uint32_t ms = millis();
  battery.update(ms);
  feedGps(ms);
  Input in;
  in.call = call;
  in.radioOk = radioOk;
  in.noCall = !call[0];
  in.freqMhz = radio.frequencyKhz() / 1000.0;
  in.batteryV = battery.volts();
  in.bleConnected = bleConnected;
#if VL3_WIFI
  static String top, bottom;
  top = String("WiFi ") + wifiName();
  bottom = String("http://") + WiFi.softAPIP().toString();
  in.pairTop = top.c_str();
  in.pairSecret = wifiPass;
  in.pairBottom = bottom.c_str();
#else
  static char code[12];
  snprintf(code, sizeof(code), "%06u", static_cast<unsigned>(passkey % 1000000u));
  static String name;
  name = bleName();
  in.pairSecret = code;
  in.pairBottom = name.c_str();
#endif
  in.powerDbm = radio.boostState().power();
  in.power = radio.boostState().iofOn() ? Power::Iof : radio.boostState().boostOn() ? Power::Boost : Power::Normal;
  in.notice = (noticeText[0] && ms < noticeUntilMs) ? noticeText : "";
  if (station && bridge) {
    Receiver& rx = station->receiver();
    if (rx.doneCount() < seenDone) seenDone = 0;                 // stazione ricreata (CALL o FREQ)
    if (rx.doneCount() != seenDone) {
      seenDone = rx.doneCount();
      snprintf(lastCall, sizeof(lastCall), "%.12s", reinterpret_cast<const char*>(rx.peerCall()));
      lastBytes = rx.doneBytes(); lastOk = rx.doneOk(); lastAtMs = ms; haveLast = true;
      distanceText(bridge->positionBlock(), bridge->hasPosition(), rx.offerPos(), rx.offerHasPos(), lastDist, sizeof(lastDist));
    }
    in.rung = station->link().rung;
    in.linkLost = station->link().lost;
    in.sending = station->sending();
    in.sendPct = bridge->sendPct();
    in.sendKind = bridge->sendKind();
    in.receiving = rx.receiving() && now - station->lastRxAt() < 30.0;
    in.rxCall = reinterpret_cast<const char*>(rx.peerCall());
    in.rxPct = rx.piecesOffered() > 0 ? 100 * rx.piecesHave() / rx.piecesOffered() : 0;
    in.rssi = station->lastRssi(); in.snr = station->lastSnr();
    in.hasPos = bridge->hasPosition();
    in.gpsEnabled = gps.active(); in.gpsFix = gps.hasFix(ms); in.gpsSats = gps.satellites();
    distanceText(bridge->positionBlock(), bridge->hasPosition(), rx.offerPos(), rx.offerHasPos(), in.distText, sizeof(in.distText));
    snprintf(in.lastDistText, sizeof(in.lastDistText), "%s", lastDist);
    bridge->positionText(in.posText);
    in.haveLast = haveLast; in.lastCall = lastCall; in.lastBytes = lastBytes; in.lastOk = lastOk; in.lastAgoMs = ms - lastAtMs;
  }
  Screen sc;
  build(in, &sc);
  oled.show(sc, ms, in.sending || in.receiving);
}

// registro delle prove: cambi di gradino, ricerca del collegamento, oggetti ricevuti
static void logChanges(double now) {
  static int rung = -1, seenDone = 0;
  static bool lost = false;
  if (!station) return;
  if (station->link().rung != rung) { rung = station->link().rung; tlog.addf(now, "gradino R%d", rung); }
  if (station->link().lost != lost) { lost = station->link().lost; tlog.add(now, lost ? "collegamento perso: ricerca" : "collegamento ritrovato"); }
  const Receiver& rx = station->receiver();
  if (rx.doneCount() < seenDone) seenDone = 0;
  if (rx.doneCount() != seenDone) {
    seenDone = rx.doneCount();
    tlog.addf(now, "ricevuto da %s: %u byte, %u livelli, CRC %s, RSSI %.0f SNR %.1f", reinterpret_cast<const char*>(rx.peerCall()), static_cast<unsigned>(rx.doneBytes()), rx.doneLayers(), rx.doneOk() ? "giusto" : "SBAGLIATO", station->lastRssi(), station->lastSnr());
  }
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
        if (changed) { Serial.printf("riavvio per annunciare il nome \"%s\"...\n", (VL3_WIFI ? wifiName() : bleName()).c_str()); Serial.flush(); delay(300); ESP.restart(); }
      } else if (const FreqParse fp = parseFreq(line, kBoardSx1262); fp.cmd != FreqCmd::NotFreq) {
        if (fp.cmd == FreqCmd::Show) Serial.printf("frequenza %.3f MHz (campo del chip %s)\n", radio.frequencyKhz() / 1000.0, kBoardSx1262 ? "150-960 MHz" : "137-175 e 410-525 MHz");
        else if (fp.cmd == FreqCmd::Invalid) Serial.printf("ERR FREQ %s\n", fp.why);
        else if (station && station->sending()) Serial.println("ERR invio in corso");
        else if (!radio.setFrequencyKhz(fp.khz)) Serial.println("ERR la radio non accetta questa frequenza");
        else { prefs.putUInt("khz", static_cast<uint32_t>(fp.khz + 0.5)); rebuild(); Serial.printf("OK frequenza %.3f MHz (salvata): impostala uguale sull'altra scheda\n", fp.khz / 1000.0); }
      } else if (!strncasecmp(line, "LOG", 3)) {                          // registro delle prove: LOG stampa, LOG CLEAR lo svuota
        if (!strncasecmp(line + 3, " CLEAR", 6)) { tlog.clear(); Serial.println("registro svuotato"); }
        else { static char buf[v3::TestLog::kBytes + 8]; tlog.dump(buf, sizeof(buf)); Serial.print("--- registro delle prove ---\n"); Serial.print(buf); Serial.print("--- fine ---\n"); }
#if VL3_WIFI
      } else if (!strncasecmp(line, "WIFI", 4)) {                         // WIFI mostra rete e password; WIFI NUOVA genera una password nuova
        if (!strncasecmp(line + 4, " NUOVA", 6)) { char b[12]; snprintf(b, sizeof(b), "%08u", static_cast<unsigned>(esp_random() % 100000000u)); prefs.putString("wpass", b); Serial.println("password nuova salvata: riavvio"); Serial.flush(); delay(300); ESP.restart(); }
        else Serial.printf("Wi-Fi: rete \"%s\", password %s, pagina http://%s/ (WIFI NUOVA = nuova password)\n", wifiSsid, wifiPass, WiFi.softAPIP().toString().c_str());
#endif
      } else if (!strncasecmp(line, "GPS", 3)) {
        if (!gps.present()) Serial.println("questa scheda non ha il GPS (solo il T-Beam)");
        else if (line[4] == 'O' || line[4] == 'o') {                       // GPS ON / GPS OFF (salvato; spento di base come la v2)
          const bool on = (line[5] == 'N' || line[5] == 'n');
          prefs.putBool("gps", on);
          gps.begin(on);
          if (!on && bridge) bridge->setGps(nullptr);
          Serial.printf("GPS %s\n", on ? "acceso: serve il cielo aperto, il primo fix puo' richiedere alcuni minuti" : "spento");
        } else Serial.printf("GPS %s, %s, %u satelliti (GPS ON | GPS OFF)\n", gps.active() ? "acceso" : "spento", gps.hasFix(millis()) ? "fix" : "nessun fix", static_cast<unsigned>(gps.satellites()));
      } else if (!strncasecmp(line, "DISPLAY", 7)) {
        if (!oled.present()) Serial.println("display OLED non trovato");
        else { oled.enable(line[8] != '0'); Serial.printf("display %s\n", oled.enabled() ? "acceso" : "spento"); }
      } else if (radio.boostCommand(line)) {
        // gestito dal driver radio (BOOST ON RISCHIO | OFF | STATUS)
      } else if (!strncasecmp(line, "STATO", 5)) {
        if (!station) { Serial.println("nessun nominativo (CALL xxx)"); continue; }
        const ble::LiveBridge::Stats& s = bridge->stats();
        Serial.printf("%s BLE %s, %.3f MHz, gradino R%d%s, invio %s, in RAM %u byte, richieste %u (ripetute %u), scartati %u, oggetti ricevuti %u, errori radio %u, coda persa %u\n", call, bleConnected ? "collegato" : "scollegato",
                      radio.frequencyKhz() / 1000.0, station->link().rung, station->link().lost ? " (in ricerca)" : "", station->sending() ? "in corso" : "fermo", static_cast<unsigned>(bridge->held()), s.pulls, s.repulls, s.dropped, s.rxObjects,
                      static_cast<unsigned>(radio.rxErrors()), static_cast<unsigned>(qDropped));
      } else if (line[0]) Serial.println("comandi: CALL <nominativo> | FREQ <MHz> | DISPLAY 0|1 | GPS ON|OFF | LOG | WIFI | STATO | BOOST|IOF ON RISCHIO|OFF|STATUS");
    } else if (n < static_cast<int>(sizeof(line)) - 1) line[n++] = c;
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("\nVoLoRa V3 mobile con radio vera (STUDIO) %s, %.3f MHz, %d dBm\n", VL3_CHIP, radio.frequencyKhz() / 1000.0, kPowerDbm);
  pmuBegin();
  SPI.begin(pins::kRadioSclk, pins::kRadioMiso, pins::kRadioMosi, pins::kRadioCs);
  radioOk = radio.begin();
  Serial.println(radioOk ? "radio pronta a R10" : "ERRORE: la radio non parte");
  battery.begin();
  oled.begin();
  prefs.begin("vl3", false);
  { const uint32_t k = prefs.getUInt("khz", 0); if (k && !radio.setFrequencyKhz(k)) Serial.printf("frequenza salvata %u kHz non valida: resta %.3f MHz\n", static_cast<unsigned>(k), radio.frequencyKhz() / 1000.0); }
  const String saved = prefs.getString("call", "");
  strncpy(call, saved.c_str(), sizeof(call) - 1);
  rebuild();
  gps.begin(prefs.getBool("gps", false));
  Serial.printf("nominativo: %s\n", call[0] ? call : "(non impostato: scrivi CALL IU5HJU)");

#if VL3_WIFI
  {
    String pw = prefs.getString("wpass", "");
    if (pw.length() != 8) { char b[12]; snprintf(b, sizeof(b), "%08u", static_cast<unsigned>(esp_random() % 100000000u)); pw = b; prefs.putString("wpass", pw); }   // 8 cifre, salvate (come la v2)
    snprintf(wifiPass, sizeof(wifiPass), "%s", pw.c_str());
    snprintf(wifiSsid, sizeof(wifiSsid), "%s", wifiName().c_str());
    WiFi.mode(WIFI_MODE_NULL);
    WiFi.mode(WIFI_AP);
    WiFi.onEvent([](WiFiEvent_t ev, WiFiEventInfo_t) {
      if (ev == ARDUINO_EVENT_WIFI_AP_STACONNECTED) { Serial.println("[wifi] un telefono si e' collegato alla rete"); tlog.add(nowSec(), "wifi: telefono collegato alla rete"); }
      if (ev == ARDUINO_EVENT_WIFI_AP_STADISCONNECTED) { Serial.println("[wifi] il telefono si e' scollegato dalla rete"); tlog.add(nowSec(), "wifi: telefono scollegato dalla rete"); }
    });
    if (!WiFi.softAP(wifiSsid, wifiPass, 1, 0, 2)) Serial.println("ERRORE: il punto di accesso Wi-Fi non parte");
    dns.start(53, "*", WiFi.softAPIP());            // ogni nome porta alla scheda: il telefono trova le sue pagine di prova e tiene la rete come buona anche senza Internet
    webServer.on("/", HTTP_GET, [](AsyncWebServerRequest* r) { sendGz(r, "text/html", kPageHtml, kPageHtmlLen); });
    webServer.on("/telefono.html", HTTP_GET, [](AsyncWebServerRequest* r) { sendGz(r, "text/html", kPageHtml, kPageHtmlLen); });
    webServer.on("/jpeg_prog.js", HTTP_GET, [](AsyncWebServerRequest* r) { sendGz(r, "text/javascript", kPageJs, kPageJsLen); });
    webServer.on("/log", HTTP_GET, [](AsyncWebServerRequest* r) {                // il registro delle prove (testlog.h), come file di testo
      static char buf[v3::TestLog::kBytes + 8];
      tlog.dump(buf, sizeof(buf));
      r->send(200, "text/plain; charset=utf-8", buf);
    });
    // sonde con cui Android, iOS e Windows controllano se c'e' Internet: si risponde "si", cosi' il telefono non lascia la rete della scheda per quella cellulare
    webServer.on("/generate_204", HTTP_GET, [](AsyncWebServerRequest* r) { r->send(204); });
    webServer.on("/gen_204", HTTP_GET, [](AsyncWebServerRequest* r) { r->send(204); });
    webServer.on("/hotspot-detect.html", HTTP_GET, [](AsyncWebServerRequest* r) { r->send(200, "text/html", "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"); });
    webServer.on("/library/test/success.html", HTTP_GET, [](AsyncWebServerRequest* r) { r->send(200, "text/html", "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"); });
    webServer.on("/connecttest.txt", HTTP_GET, [](AsyncWebServerRequest* r) { r->send(200, "text/plain", "Microsoft Connect Test"); });
    webServer.on("/ncsi.txt", HTTP_GET, [](AsyncWebServerRequest* r) { r->send(200, "text/plain", "Microsoft NCSI"); });
    ws.onEvent(onWsEvent);
    webServer.addHandler(&ws);
    webServer.begin();
    Serial.printf("Wi-Fi acceso: rete \"%s\", password %s, pagina su http://%s/\n", wifiSsid, wifiPass, WiFi.softAPIP().toString().c_str());
    Serial.printf("pagina del telefono nel firmware: %u byte compressi (%u + %u)\n", static_cast<unsigned>(kPageHtmlLen + kPageJsLen), static_cast<unsigned>(kPageHtmlLen), static_cast<unsigned>(kPageJsLen));
  }
  { v3::disp::Screen st; v3::disp::buildStartup(call, LCR_VERSION, &st); oled.showNow(st); delay(1800); }      // la versione del firmware all'accensione, come la v2
#else
  passkey = 100000 + (esp_random() % 900000);           // codice a 6 cifre per l'accoppiamento (sulla seriale; lo schermo OLED dopo)
  NimBLEDevice::init(bleName().c_str());
  Serial.printf("nome Bluetooth: %s\n", bleName().c_str());
  { v3::disp::Screen st; v3::disp::buildStartup(call, LCR_VERSION, &st); oled.showNow(st); delay(1800); }      // la versione del firmware all'accensione, come la v2
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
#endif
  tlog.addf(nowSec(), "avvio: %s, firmware %s, %s, %.3f MHz, collegamento %s", VL3_CHIP, LCR_VERSION, call[0] ? call : "(senza nominativo)", radio.frequencyKhz() / 1000.0, kLinkWord);
}

void loop() {
  Frame f;
  while (pop(&f)) {
    if (f.kind == 2) { bleConnected = true; if (bridge) bridge->onConnect(); Serial.printf("[%s] telefono collegato\n", kLinkWord); tlog.addf(nowSec(), "telefono collegato (%s)", kLinkWord); }
    else if (f.kind == 3) { bleConnected = false; if (bridge) bridge->onDisconnect(); Serial.printf("[%s] telefono scollegato\n", kLinkWord); tlog.addf(nowSec(), "telefono scollegato (%s)", kLinkWord); }
    else if (bridge) { if (f.kind == 0) bridge->onCommand(f.d, f.len); else bridge->onData(f.d, f.len); }
  }
  handleSerial();
  if (!station) { updateDisplay(nowS()); delay(5); return; }
  const double now = nowS();
  radio.service(*station, now);
  station->poll(now);
  bridge->poll(now);
#if VL3_WIFI
  dns.processNextRequest();
  ws.cleanupClients();
#endif
  logChanges(now);
  updateDisplay(now);
  delay(1);
}
