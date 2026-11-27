// Firmware V3, PROVA A BANCO del protocollo immagini fra due schede: una manda un oggetto di prova, l'altra lo riceve. STUDIO: mai eseguito su una scheda.
// Serve a provare il mezzo (src/medium.h) e il driver radio (src/radio_board.h) con le radio vere: due schede uguali, con l'antenna (o un attenuatore) collegata.
// Seriale a 115200 baud:  CALL <nominativo> | SEND <byte, da 1 a 32768> | STATO.   La scheda che riceve non fa niente: stampa quello che arriva.
#include <Arduino.h>
#include <SPI.h>

#include "freq.h"
#include "pmu.h"
#include "radio_board.h"

using namespace v3;
using namespace v3::img;

constexpr size_t kBenchMax = 32768;
static uint8_t txObj[kBenchMax];
static uint8_t rxBuf[kBenchMax];
static uint8_t rxLen[kBenchMax / kPiece];
static uint16_t rxPieces = 0;

struct RamStore : Store {
  void reset(uint16_t n) override { rxPieces = n > kBenchMax / kPiece ? kBenchMax / kPiece : n; memset(rxLen, 0, sizeof(rxLen)); }
  void put(uint16_t i, const uint8_t* d, size_t n) override { if (i < rxPieces && n <= kPiece) { memcpy(rxBuf + static_cast<size_t>(i) * kPiece, d, n); rxLen[i] = static_cast<uint8_t>(n); } }
  size_t get(uint16_t i, uint8_t* out) override { if (i >= rxPieces) return 0; memcpy(out, rxBuf + static_cast<size_t>(i) * kPiece, rxLen[i]); return rxLen[i]; }
};
static RamStore store;
static BoardRadio radio;
static Station* station = nullptr;
static char call[9] = "";
static bool announcedSend = false, announcedRx = false;
static int lastRung = -1;
static uint32_t sendStartMs = 0;

static void makeStation() {
  delete station;
  const size_t n = strlen(call);
  station = new Station(reinterpret_cast<const uint8_t*>(call), n, kBoardSx1262, false, &radio, &store, kWindowFrames, true,
                       kBoardSx1262 ? 0 : static_cast<uint16_t>(1u << 3), radio.frequencyKhz());     // R3 (LoRa 500/SF6) sull'SX1278 vuole l'intestazione implicita: il driver non lo fa
}

static void handleLine(const char* line) {
  if (!strncasecmp(line, "CALL ", 5)) {
    int k = 0;
    for (const char* p = line + 5; *p && k < 8; p++) if (*p != ' ') call[k++] = static_cast<char>(toupper(*p));
    call[k] = 0;
    makeStation();
    Serial.printf("OK nominativo %s\n", call);
  } else if (!strncasecmp(line, "SEND ", 5)) {
    if (!call[0] || !station) { Serial.println("ERR serve CALL <nominativo>"); return; }
    const long n = atol(line + 5);
    if (n < 1 || n > static_cast<long>(kBenchMax)) { Serial.println("ERR SEND da 1 a 32768 byte"); return; }
    for (long i = 0; i < n; i++) txObj[i] = static_cast<uint8_t>((i * 131 + 7) ^ (i >> 8));
    const int np = static_cast<int>((n + kPiece - 1) / kPiece);
    uint16_t ends[3] = {static_cast<uint16_t>((np + 2) / 3), static_cast<uint16_t>((2 * np + 2) / 3), static_cast<uint16_t>(np)};
    if (ends[0] < 1) ends[0] = 1;
    if (ends[1] < ends[0]) ends[1] = ends[0];
    if (!station->startSend(txObj, static_cast<size_t>(n), ends, 3, 600.0, static_cast<uint16_t>(1 + esp_random() % 65000))) { Serial.println("ERR invio non partito"); return; }
    announcedSend = false; sendStartMs = millis();
    Serial.printf("OK invio di %ld byte (CRC32 %08X): HELLO a R10...\n", n, static_cast<unsigned>(crc32(txObj, static_cast<size_t>(n))));
  } else if (const FreqParse fp = parseFreq(line, kBoardSx1262); fp.cmd != FreqCmd::NotFreq) {
    if (fp.cmd == FreqCmd::Show) Serial.printf("frequenza %.3f MHz (campo del chip %s)\n", radio.frequencyKhz() / 1000.0, kBoardSx1262 ? "150-960 MHz" : "137-175 e 410-525 MHz");
    else if (fp.cmd == FreqCmd::Invalid) Serial.printf("ERR FREQ %s\n", fp.why);
    else if (station && station->sending()) Serial.println("ERR invio in corso");
    else if (!radio.setFrequencyKhz(fp.khz)) Serial.println("ERR la radio non accetta questa frequenza");
    else { makeStation(); Serial.printf("OK frequenza %.3f MHz: impostala uguale sull'altra scheda\n", fp.khz / 1000.0); }
  } else if (radio.powerCommand(line) || radio.boostCommand(line)) {
    // gestito dal driver radio (BOOST ON RISCHIO | OFF | STATUS)
  } else if (!strncasecmp(line, "STATO", 5)) {
    if (!station) { Serial.println("nessun nominativo"); return; }
    Serial.printf("%.3f MHz, gradino R%d, in ricerca %s, invio %s, radio: errori di ricezione %u\n", radio.frequencyKhz() / 1000.0, station->link().rung, station->link().lost ? "si" : "no", station->sending() ? "in corso" : "fermo", static_cast<unsigned>(radio.rxErrors()));
  } else if (line[0]) Serial.println("comandi: CALL <nominativo> | FREQ <MHz> | SEND <byte> | STATO | POWER <dBm> | BOOST|IOF ON RISCHIO|OFF|STATUS");
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("\nVoLoRa V3 prova a banco (STUDIO) %s, %.3f MHz, %d dBm\n", VL3_CHIP, radio.frequencyKhz() / 1000.0, kPowerDbm);
  pmuBegin();
  SPI.begin(pins::kRadioSclk, pins::kRadioMiso, pins::kRadioMosi, pins::kRadioCs);
  Serial.println(radio.begin() ? "radio pronta a R10" : "ERRORE: la radio non parte");
  Serial.println("scrivi CALL <nominativo>, poi SEND <byte> su una scheda");
}

void loop() {
  static char line[40];
  static int n = 0;
  const double now = millis() / 1000.0;
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r' || c == '\n') { line[n] = 0; n = 0; handleLine(line); }
    else if (n < static_cast<int>(sizeof(line)) - 1) line[n++] = c;
  }
  if (!station) { delay(5); return; }
  radio.service(*station, now);
  station->poll(now);
  if (station->link().rung != lastRung) { lastRung = station->link().rung; Serial.printf("[%.1f s] gradino R%d\n", now, lastRung); }
  if (station->sendFinished() && !announcedSend) {
    announcedSend = true;
    if (station->sendOk()) Serial.printf("[%.1f s] INVIO FINITO: %d livelli, %u byte consegnati in %.1f s\n", now, station->layersDelivered(), static_cast<unsigned>(station->bytesDelivered()), (millis() - sendStartMs) / 1000.0);
    else Serial.printf("[%.1f s] INVIO FALLITO (motivo %d)\n", now, static_cast<int>(station->sendFailure()));
  }
  if (station->receiver().hasDone() && !announcedRx) {
    announcedRx = true;
    Serial.printf("[%.1f s] OGGETTO RICEVUTO: %u pezzi, CRC %s\n", now, static_cast<unsigned>(rxPieces), station->receiver().doneOk() ? "GIUSTO" : "SBAGLIATO");
  }
  if (!station->receiver().hasDone()) announcedRx = false;
  delay(1);
}
