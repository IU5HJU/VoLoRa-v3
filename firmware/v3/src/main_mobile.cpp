// Firmware V3, scheda MOBILE COMPLETA: telefono -> ponte -> mezzo -> radio vera, e radio -> ponte -> telefono. STUDIO: mai eseguito su una scheda.
// Il telefono si collega in due modi, con lo stesso protocollo di comandi ed eventi (docs/ble-telefono.md), UNO ALLA VOLTA:
//  - Bluetooth LE (sempre acceso all'avvio): per Android, con l'app VoLoRa-V3.apk (app/, docs/app-android.md).
//  - Wi-Fi della scheda, SPENTO ALL'AVVIO e acceso solo da chi ne ha bisogno (iPhone): tasto BOOT premuto 2 s oppure WIFI ON sulla seriale. La scheda crea il Wi-Fi "VoLoRa-<NOMINATIVO>",
//    SERVE LA PAGINA DEL TELEFONO (incorporata nel firmware, niente Internet) su http://192.168.4.1 e parla con la pagina via WebSocket (/ws). Con il Wi-Fi acceso il Bluetooth tace.
// Nucleo: src/live_bridge.h (ponte collegato al mezzo), src/medium.h (stazione), src/radio_board.h (driver RadioLib).
// Il buffer e' il telefono: la scheda tiene 8 blocchi da 1 kB e li chiede a richiesta (E_PULL); nessuna microSD. Gli oggetti dalla radio si accettano solo col telefono collegato.
// Seriale a 115200 baud: CALL, FREQ, WIFI, GPS, BOOST, IOF, DISPLAY, LOG, STATO.
#include <Arduino.h>
#include <DNSServer.h>
#include <ESPAsyncWebServer.h>
#include <NimBLEDevice.h>
#include <WiFi.h>

#include "web_assets.h"
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

static const char* kService = "c49a1433-9f1b-4af8-9826-951953e47edb";
static const char* kCmd = "c49a1434-9f1b-4af8-9826-951953e47edb";
static const char* kDataIn = "c49a1435-9f1b-4af8-9826-951953e47edb";
static const char* kEvt = "c49a1436-9f1b-4af8-9826-951953e47edb";
static const char* kDataOut = "c49a1437-9f1b-4af8-9826-951953e47edb";

// ---------------------------------------------------------------- coda fra i callback del BLE (altro task) e il ciclo principale
struct Frame { uint8_t kind; uint8_t len; uint8_t d[250]; };      // kind: 0 comando, 1 dati, 2 Bluetooth collegato, 3 Bluetooth scollegato, 4 WebSocket collegato, 5 WebSocket scollegato
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

// ---------------------------------------------------------------- collegamento col telefono: Bluetooth LE (Android, app VoLoRa-V3.apk)
static NimBLECharacteristic* chEvt = nullptr;
static NimBLECharacteristic* chDataOut = nullptr;
static uint32_t passkey = 0;
static bool wifiOn = false;                              // il Wi-Fi della scheda e' acceso (solo su richiesta: iPhone)
static bool bleLink = false, wsLink = false;             // quale collegamento ha un telefono
static bool bleConnected = false;                        // (nome storico) un telefono e' collegato, in uno dei due modi

class ServerCb : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer*, ble_gap_conn_desc*) override { push(2, nullptr, 0); }
  void onDisconnect(NimBLEServer*) override { push(3, nullptr, 0); if (!wifiOn) NimBLEDevice::startAdvertising(); }
  uint32_t onPassKeyRequest() override { return passkey; }
  void onAuthenticationComplete(ble_gap_conn_desc* desc) override { Serial.printf("[ble] accoppiamento %s\n", desc->sec_state.encrypted ? "completato (cifrato)" : "NON cifrato"); }
};
class CmdCb : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c) override { const std::string v = c->getValue(); push(0, reinterpret_cast<const uint8_t*>(v.data()), v.size()); }
};
class DataCb : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c) override { const std::string v = c->getValue(); push(1, reinterpret_cast<const uint8_t*>(v.data()), v.size()); }
};
static void bleEvt(const uint8_t* d, size_t n) { if (!chEvt) return; chEvt->setValue(d, n); chEvt->notify(); }
static void bleData(const uint8_t* d, size_t n) { if (!chDataOut) return; chDataOut->setValue(d, n); chDataOut->notify(); }

// ---------------------------------------------------------------- collegamento col telefono: Wi-Fi della scheda (punto di accesso), pagina servita dalla scheda, WebSocket (iPhone)
static AsyncWebServer webServer(80);
static AsyncWebSocket ws("/ws");
static DNSServer dns;
static char wifiSsid[24] = "", wifiPass[12] = "";
static AsyncWebSocketClient* wsClient = nullptr;        // un solo telefono alla volta

// messaggi WebSocket: il primo byte e' il canale (0 comando, 1 dati dal telefono; 2 evento, 3 dati verso il telefono)
static void wsEvt(const uint8_t* d, size_t n) { uint8_t m[260]; if (n + 1 > sizeof(m)) return; m[0] = 2; memcpy(m + 1, d, n); ws.binaryAll(m, n + 1); }
static void wsData(const uint8_t* d, size_t n) { uint8_t m[260]; if (n + 1 > sizeof(m)) return; m[0] = 3; memcpy(m + 1, d, n); ws.binaryAll(m, n + 1); }
static void onWsEvent(AsyncWebSocket*, AsyncWebSocketClient* c, AwsEventType type, void* arg, uint8_t* data, size_t len) {
  if (type == WS_EVT_CONNECT) {
    if (wsClient && wsClient != c && wsClient->status() == WS_CONNECTED) wsClient->close();     // il telefono nuovo prende il posto del vecchio
    wsClient = c;
    push(4, nullptr, 0);
  } else if (type == WS_EVT_DISCONNECT) {
    if (c == wsClient) { wsClient = nullptr; push(5, nullptr, 0); }
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

// verso il telefono: dal collegamento che ha un telefono
static void linkEvt(const uint8_t* d, size_t n) { if (wsLink) wsEvt(d, n); else if (bleLink) bleEvt(d, n); }
static void linkData(const uint8_t* d, size_t n) { if (wsLink) wsData(d, n); else if (bleLink) bleData(d, n); }
static const char* linkWord() { return wsLink ? "Wi-Fi" : "Bluetooth"; }

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
  static String top, bottom;
  static char code[12];
  if (wifiOn) {                                          // Wi-Fi della scheda (iPhone): rete, password a 8 cifre, indirizzo
    top = String("WiFi ") + wifiName();
    bottom = String("http://") + WiFi.softAPIP().toString();
    in.pairTop = top.c_str();
    in.pairSecret = wifiPass;
    in.pairBottom = bottom.c_str();
  } else {                                               // Bluetooth (Android): codice a 6 cifre; ogni 4 s un richiamo per chi ha l'iPhone
    snprintf(code, sizeof(code), "%06u", static_cast<unsigned>(passkey % 1000000u));
    const bool hint = (millis() / 4000) % 2 == 1;
    top = hint ? String("iPhone: tasto BOOT") : String("Collega il telefono");
    bottom = hint ? String("premuto 2 s = Wi-Fi") : bleName();
    in.pairTop = top.c_str();
    in.pairSecret = code;
    in.pairBottom = bottom.c_str();
  }
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

// ---- Wi-Fi della scheda, solo su richiesta (iPhone). Con il Wi-Fi acceso il Bluetooth tace: un solo telefono alla volta ----
static void setWifi(bool on) {
  if (on == wifiOn) return;
  if (on) {
    if (bleLink) { Serial.println("[wifi] il telefono Bluetooth viene scollegato"); }
    NimBLEDevice::getAdvertising()->stop();
    for (auto& c : NimBLEDevice::getServer()->getPeerDevices()) NimBLEDevice::getServer()->disconnect(c);
    WiFi.mode(WIFI_MODE_NULL);
    WiFi.mode(WIFI_AP);
    if (!WiFi.softAP(wifiSsid, wifiPass, 1, 0, 2)) { Serial.println("ERRORE: il punto di accesso Wi-Fi non parte"); NimBLEDevice::getAdvertising()->start(); WiFi.mode(WIFI_OFF); return; }
    dns.start(53, "*", WiFi.softAPIP());            // ogni nome porta alla scheda: il telefono trova le sue pagine e tiene la rete come buona anche senza Internet
    webServer.begin();
    wifiOn = true;
    Serial.printf("Wi-Fi ACCESO: rete \"%s\", password %s, pagina su http://%s/ (il Bluetooth e' spento)\n", wifiSsid, wifiPass, WiFi.softAPIP().toString().c_str());
    tlog.add(nowSec(), "Wi-Fi acceso (iPhone): Bluetooth spento");
  } else {
    wifiOn = false;
    ws.closeAll();
    dns.stop();
    webServer.end();
    WiFi.softAPdisconnect(true);
    WiFi.mode(WIFI_OFF);
    NimBLEDevice::getAdvertising()->start();
    Serial.println("Wi-Fi spento: Bluetooth di nuovo acceso");
    tlog.add(nowSec(), "Wi-Fi spento: Bluetooth acceso");
  }
}

// tasto BOOT (GPIO0): tenuto premuto 2 s accende o spegne il Wi-Fi della scheda (per chi ha l'iPhone); sulla T3 e sul T-Beam e' il pulsante di bordo
static void checkButton() {
  static uint32_t downAt = 0;
  static bool fired = false;
  const bool down = digitalRead(0) == LOW;
  const uint32_t ms = millis();
  if (!down) { downAt = 0; fired = false; return; }
  if (downAt == 0) downAt = ms;
  if (!fired && ms - downAt >= 2000) { fired = true; setWifi(!wifiOn); setNotice(wifiOn ? "WI-FI ACCESO" : "WI-FI SPENTO"); }
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
        if (changed) { Serial.printf("riavvio per annunciare i nomi \"%s\" (Bluetooth) e \"%s\" (Wi-Fi)...\n", bleName().c_str(), wifiName().c_str()); Serial.flush(); delay(300); ESP.restart(); }
      } else if (const FreqParse fp = parseFreq(line, kBoardSx1262); fp.cmd != FreqCmd::NotFreq) {
        if (fp.cmd == FreqCmd::Show) Serial.printf("frequenza %.3f MHz (campo del chip %s)\n", radio.frequencyKhz() / 1000.0, kBoardSx1262 ? "150-960 MHz" : "137-175 e 410-525 MHz");
        else if (fp.cmd == FreqCmd::Invalid) Serial.printf("ERR FREQ %s\n", fp.why);
        else if (station && station->sending()) Serial.println("ERR invio in corso");
        else if (!radio.setFrequencyKhz(fp.khz)) Serial.println("ERR la radio non accetta questa frequenza");
        else { prefs.putUInt("khz", static_cast<uint32_t>(fp.khz + 0.5)); rebuild(); Serial.printf("OK frequenza %.3f MHz (salvata): impostala uguale sull'altra scheda\n", fp.khz / 1000.0); }
      } else if (!strncasecmp(line, "LOG", 3)) {                          // registro delle prove: LOG stampa, LOG CLEAR lo svuota
        if (!strncasecmp(line + 3, " CLEAR", 6)) { tlog.clear(); Serial.println("registro svuotato"); }
        else { static char buf[v3::TestLog::kBytes + 8]; tlog.dump(buf, sizeof(buf)); Serial.print("--- registro delle prove ---\n"); Serial.print(buf); Serial.print("--- fine ---\n"); }
      } else if (!strncasecmp(line, "WIFI", 4)) {                         // WIFI ON/OFF accende o spegne il Wi-Fi della scheda (per iPhone); WIFI NUOVA cambia la password; WIFI mostra lo stato
        if (!strncasecmp(line + 4, " NUOVA", 6)) { char b[12]; snprintf(b, sizeof(b), "%08u", static_cast<unsigned>(esp_random() % 100000000u)); prefs.putString("wpass", b); Serial.println("password nuova salvata: riavvio"); Serial.flush(); delay(300); ESP.restart(); }
        else if (!strncasecmp(line + 4, " ON", 3)) setWifi(true);
        else if (!strncasecmp(line + 4, " OFF", 4)) setWifi(false);
        else Serial.printf("Wi-Fi %s: rete \"%s\", password %s, pagina http://192.168.4.1/ (WIFI ON | WIFI OFF | WIFI NUOVA)\n", wifiOn ? "ACCESO" : "spento", wifiSsid, wifiPass);
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

  {                                                     // Wi-Fi della scheda: password e pagine pronte, ma la rete resta SPENTA finche' non la accende chi ha l'iPhone
    String pw = prefs.getString("wpass", "");
    if (pw.length() != 8) { char b[12]; snprintf(b, sizeof(b), "%08u", static_cast<unsigned>(esp_random() % 100000000u)); pw = b; prefs.putString("wpass", pw); }   // 8 cifre, salvate (come la v2)
    snprintf(wifiPass, sizeof(wifiPass), "%s", pw.c_str());
    snprintf(wifiSsid, sizeof(wifiSsid), "%s", wifiName().c_str());
    WiFi.onEvent([](WiFiEvent_t ev, WiFiEventInfo_t) {
      if (ev == ARDUINO_EVENT_WIFI_AP_STACONNECTED) { Serial.println("[wifi] un telefono si e' collegato alla rete"); tlog.add(nowSec(), "wifi: telefono collegato alla rete"); }
      if (ev == ARDUINO_EVENT_WIFI_AP_STADISCONNECTED) { Serial.println("[wifi] il telefono si e' scollegato dalla rete"); tlog.add(nowSec(), "wifi: telefono scollegato dalla rete"); }
    });
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
    ws.onEvent(onWsEvent);
    webServer.addHandler(&ws);
    Serial.printf("pagina del telefono nel firmware: %u byte compressi; Wi-Fi spento (WIFI ON o tasto BOOT 2 s per l'iPhone)\n", static_cast<unsigned>(kPageHtmlLen + kPageJsLen));
  }
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
  pinMode(0, INPUT_PULLUP);                              // tasto BOOT
  tlog.addf(nowSec(), "avvio: %s, firmware %s, %s, %.3f MHz, Bluetooth acceso, Wi-Fi spento", VL3_CHIP, LCR_VERSION, call[0] ? call : "(senza nominativo)", radio.frequencyKhz() / 1000.0);
}

void loop() {
  Frame f;
  while (pop(&f)) {
    if (f.kind >= 2 && f.kind <= 5) {                    // un telefono si collega o si scollega (2/3 Bluetooth, 4/5 WebSocket)
      const bool up = (f.kind == 2 || f.kind == 4);
      if (f.kind <= 3) bleLink = up; else wsLink = up;
      const bool any = bleLink || wsLink;
      if (any != bleConnected) { bleConnected = any; if (bridge) { if (any) bridge->onConnect(); else bridge->onDisconnect(); } }
      Serial.printf("[%s] telefono %s\n", f.kind <= 3 ? "Bluetooth" : "Wi-Fi", up ? "collegato" : "scollegato");
      tlog.addf(nowSec(), "telefono %s (%s)", up ? "collegato" : "scollegato", f.kind <= 3 ? "Bluetooth" : "Wi-Fi");
    }
    else if (bridge) { if (f.kind == 0) bridge->onCommand(f.d, f.len); else if (f.kind == 1) bridge->onData(f.d, f.len); }
  }
  handleSerial();
  checkButton();
  if (!station) { updateDisplay(nowS()); delay(5); return; }
  const double now = nowS();
  radio.service(*station, now);
  station->poll(now);
  bridge->poll(now);
  if (wifiOn) { dns.processNextRequest(); ws.cleanupClients(); }
  logChanges(now);
  updateDisplay(now);
  delay(1);
}
