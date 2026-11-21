// Firmware di misura (fase 1, studio VoLoRa V3). Comandi di testo sulla seriale a 921600 baud, una riga per comando.
// Serve a misurare sensibilita', tempo in aria, perdite e deriva di frequenza di ogni modo LoRa e FSK. Non e' il firmware V3.
#include <Arduino.h>
#include <RadioLib.h>
#include <SPI.h>

#include "board.h"
#include "misura_core.h"

using namespace misura;

#define FW_VERSION "misura 0.1.0"

#if defined(RADIO_SX1262)
#define CHIP "SX1262"
static SX1262 radio = new Module(pins::kRadioCs, pins::kRadioDio1, pins::kRadioRst, pins::kRadioBusy);
#else
#define CHIP "SX1278"
static SX1278 radio = new Module(pins::kRadioCs, pins::kRadioDio0, pins::kRadioRst, pins::kRadioDio1);
#endif

static Params P;
static char callsign[9] = "";
static bool verbose = true;
static bool modeReady = false;

static volatile bool isrFlag = false;
static volatile uint32_t isrUs = 0;
static void IRAM_ATTR onRadioDone() {
  isrUs = micros();
  isrFlag = true;
}

// ---------- Utilita' ----------
static bool serialKey() {
  if (Serial.available()) {
    while (Serial.available()) Serial.read();
    return true;
  }
  return false;
}

static bool callOk() {
  if (!callsign[0]) {
    Serial.println("ERR serve CALL <nominativo> prima di trasmettere");
    return false;
  }
  return true;
}

static bool applyMode() {
  modeReady = false;
  int st;
  if (!P.fsk) {
#if defined(RADIO_SX1262)
    st = radio.begin(P.freqMhz, P.bwKhz, P.sf, P.cr, MISURA_SYNC, P.powerDbm, P.preamble, MISURA_TCXO_V);
#else
    st = radio.begin(P.freqMhz, P.bwKhz, P.sf, P.cr, MISURA_SYNC, P.powerDbm, P.preamble);
#endif
    if (st == RADIOLIB_ERR_NONE) st = radio.setCRC(true);
  } else {
#if defined(RADIO_SX1262)
    st = radio.beginFSK(P.freqMhz, P.kbps, P.devKhz, P.rxBwKhz, P.powerDbm, P.preamble, MISURA_TCXO_V);
#else
    st = radio.beginFSK(P.freqMhz, P.kbps, P.devKhz, P.rxBwKhz, P.powerDbm, P.preamble, false);
#endif
    if (st == RADIOLIB_ERR_NONE) st = radio.fixedPacketLengthMode(static_cast<uint8_t>(P.payload));
#if defined(RADIO_SX1262)
    if (st == RADIOLIB_ERR_NONE) st = radio.setCRC(2);
#else
    if (st == RADIOLIB_ERR_NONE) st = radio.setCRC(true);
#endif
    if (st == RADIOLIB_ERR_NONE && P.shape != 0)
      st = radio.setDataShaping(P.shape == 3 ? RADIOLIB_SHAPING_0_3 : (P.shape == 5 ? RADIOLIB_SHAPING_0_5 : RADIOLIB_SHAPING_1_0));
  }
  if (st != RADIOLIB_ERR_NONE) {
    Serial.printf("ERR radio st=%d\n", st);
    return false;
  }
  radio.setPacketSentAction(onRadioDone);
  radio.setPacketReceivedAction(onRadioDone);
  modeReady = true;
  return true;
}

static void showParams() {
  if (P.fsk)
    Serial.printf("MODE FSK %.2f kbit/s dev %.1f kHz rxbw %.1f kHz shape %d | ", P.kbps, P.devKhz, P.rxBwKhz, P.shape);
  else
    Serial.printf("MODE LORA bw %.2f kHz sf %d cr 4/%d | ", P.bwKhz, P.sf, P.cr);
  Serial.printf("freq %.4f MHz power %d dBm payload %d preamble %d call %s ready %d\n", P.freqMhz, P.powerDbm, P.payload, P.preamble,
                callsign[0] ? callsign : "-", modeReady ? 1 : 0);
}

static uint32_t expectedToaUs() {
  return P.fsk ? fskToaUs(P.kbps, P.payload, P.preamble) : loraToaUs(P.sf, P.bwKhz, P.cr, P.payload, P.preamble);
}

// ---------- Comandi ----------
static void cmdTx(int n, int intervalMs, uint32_t startSeq) {
  if (!callOk() || !modeReady) return;
  static uint8_t buf[kMaxPayload];
  const uint32_t calc = expectedToaUs();
  uint32_t ok = 0;
  uint64_t sumToa = 0;
  for (int i = 0; i < n; i++) {
    const uint32_t seq = startSeq + static_cast<uint32_t>(i);
    buildPacket(buf, P.payload, seq, callsign);
    const uint32_t loopStart = millis();
    isrFlag = false;
    const uint32_t t0 = micros();
    const int st = radio.startTransmit(buf, static_cast<size_t>(P.payload));
    bool done = false;
    const uint32_t limit = calc * 2 + 1000000UL;
    while (st == RADIOLIB_ERR_NONE && micros() - t0 < limit) {
      if (isrFlag) {
        done = true;
        break;
      }
    }
    const uint32_t toa = done ? isrUs - t0 : 0;
    radio.finishTransmit();
    if (st == RADIOLIB_ERR_NONE && done) {
      ok++;
      sumToa += toa;
    }
    if (verbose) Serial.printf("TX seq=%u len=%d toa_us=%u calc_us=%u st=%d\n", seq, P.payload, toa, calc, done ? st : (st ? st : -999));
    if (serialKey()) {
      Serial.println("STOP");
      break;
    }
    const uint32_t spent = millis() - loopStart;
    if (spent < static_cast<uint32_t>(intervalMs)) delay(static_cast<uint32_t>(intervalMs) - spent);
  }
  Serial.printf("TXSUM sent=%u toa_mean_us=%u calc_us=%u\n", ok, ok ? static_cast<uint32_t>(sumToa / ok) : 0u, calc);
}

static void cmdRx(int seconds) {
  if (!modeReady) return;
  static uint8_t buf[kMaxPayload + 8];
  Stats s;
  isrFlag = false;
  int st = radio.startReceive();
  if (st != RADIOLIB_ERR_NONE) {
    Serial.printf("ERR startReceive st=%d\n", st);
    return;
  }
  const uint32_t end = millis() + static_cast<uint32_t>(seconds) * 1000UL;
  while (static_cast<int32_t>(end - millis()) > 0) {
    if (serialKey()) {
      Serial.println("STOP");
      break;
    }
    if (!isrFlag) continue;
    isrFlag = false;
    const size_t len = radio.getPacketLength();
    const int rs = radio.readData(buf, len > sizeof(buf) ? sizeof(buf) : len);
    const bool radioCrcErr = rs == RADIOLIB_ERR_CRC_MISMATCH;
    const float rssi = radio.getRSSI();
    float snr = NAN, fei = NAN;
    if (!P.fsk) {
      snr = radio.getSNR();
      fei = radio.getFrequencyError();
    }
    const Parsed p = parsePacket(buf, static_cast<int>(len));
    s.add(p, radioCrcErr, rssi, snr, fei);
    if (verbose)
      Serial.printf("RX seq=%u len=%u rssi=%.1f snr=%.1f fei=%.0f rs=%d status=%d bit_err=%d\n", p.seq, static_cast<unsigned>(len), rssi, snr, fei,
                    rs, static_cast<int>(p.status), p.bitErrors);
    radio.startReceive();
  }
  radio.standby();
  char line[200];
  formatSummary(line, sizeof(line), s);
  Serial.println(line);
}

// Portante per il misuratore di potenza: pacchetti FSK tutti 0xFF a 4,8 kbit/s (stesso metodo della v2 per il Morse), uno dopo l'altro.
// La portante sta alla frequenza scelta piu' la deviazione (1 kHz): irrilevante per la potenza. Poi si rimette il modo di prima.
static void cmdCw(int seconds) {
  if (!callOk()) return;
  if (seconds < 1 || seconds > 30) {
    Serial.println("ERR CW da 1 a 30 secondi");
    return;
  }
  const Params saved = P;
  P.fsk = true;
  P.kbps = 4.8f;
  P.devKhz = 1.0f;
  P.rxBwKhz = 12.5f;
  P.shape = 0;
  P.preamble = 0;
  P.payload = 255;
  if (!applyMode()) {
    P = saved;
    applyMode();
    return;
  }
  static uint8_t buf[255];
  memset(buf, 0xFF, sizeof(buf));
  Serial.printf("CW start %d s su %.4f MHz, %d dBm\n", seconds, P.freqMhz, P.powerDbm);
  const uint32_t end = millis() + static_cast<uint32_t>(seconds) * 1000UL;
  uint32_t n = 0;
  while (static_cast<int32_t>(end - millis()) > 0) {
    radio.transmit(buf, sizeof(buf));  // bloccante, circa 0,43 s
    n++;
    if (serialKey()) {
      Serial.println("STOP");
      break;
    }
  }
  radio.standby();
  Serial.printf("CW fine pacchetti=%u\n", n);
  P = saved;
  applyMode();
}

static void printHelp() {
  Serial.println(
      "Comandi: INFO | SHOW | HELP | CALL <nominativo> | MODE LORA <bwKHz> <sf> <cr 5-8> | MODE FSK <kbps> <devKHz> <rxbwKHz> [shape 0|3|5|10]\n"
      "         FREQ <MHz 430-440> | POWER <dBm> | PAYLOAD <26-255> | PREAMBLE <n> | VERBOSE 0|1\n"
      "         TX <n> <intervallo ms> [seq iniziale] | RX <secondi> | CW <secondi 1-30> | un tasto qualsiasi ferma TX, RX e CW");
}

static void handleLine(const char* line) {
  const Tokens t = tokenize(line);
  if (t.n == 0) return;
  const char* c = t.tok[0];
  float f;
  int a, b, d;
  if (!strcmp(c, "HELP")) {
    printHelp();
  } else if (!strcmp(c, "INFO")) {
    Serial.printf("INFO %s %s sync=0x%02X tcxo=%.1f\n", FW_VERSION, CHIP, MISURA_SYNC, static_cast<double>(MISURA_TCXO_V));
    Serial.println("ATTENZIONE: antenna o carico da 50 ohm collegati PRIMA di trasmettere. Solo con il proprio nominativo.");
    showParams();
  } else if (!strcmp(c, "SHOW")) {
    showParams();
  } else if (!strcmp(c, "CALL") && t.n == 2) {
    const size_t l = strlen(t.tok[1]);
    bool ok = l >= 3 && l <= 8;
    for (size_t i = 0; i < l; i++) ok = ok && isalnum(static_cast<unsigned char>(t.tok[1][i]));
    if (!ok) {
      Serial.println("ERR nominativo: da 3 a 8 lettere o cifre");
    } else {
      strcpy(callsign, t.tok[1]);
      Serial.printf("OK call %s\n", callsign);
    }
  } else if (!strcmp(c, "MODE") && t.n >= 2 && !strcmp(t.tok[1], "LORA") && t.n == 5) {
    float bw;
    if (parseFloat(t.tok[2], &bw) && parseInt(t.tok[3], &a) && parseInt(t.tok[4], &b) && loraValid(bw, a, b)) {
      P.fsk = false;
      P.bwKhz = bw;
      P.sf = a;
      P.cr = b;
      if (applyMode()) showParams();
    } else {
      Serial.println("ERR MODE LORA: bw in 7.8 10.4 15.6 20.8 31.25 41.7 62.5 125 250 500, sf 5-12, cr 5-8");
    }
  } else if (!strcmp(c, "MODE") && t.n >= 2 && !strcmp(t.tok[1], "FSK") && (t.n == 5 || t.n == 6)) {
    float k, dv, rb;
    int sh = 0;
    if (parseFloat(t.tok[2], &k) && parseFloat(t.tok[3], &dv) && parseFloat(t.tok[4], &rb) && (t.n == 5 || parseInt(t.tok[5], &sh)) &&
        fskValid(k, dv, rb)) {
      P.fsk = true;
      P.kbps = k;
      P.devKhz = dv;
      P.rxBwKhz = rb;
      P.shape = sh;
      if (applyMode()) showParams();
    } else {
      Serial.println("ERR MODE FSK: kbps 0.5-300, dev 0.6-200 con dev + kbps/2 <= 250, rxbw la prima ammessa dalla radio (SX1278 fino a 250, SX1262 fino a 467)");
    }
  } else if (!strcmp(c, "FREQ") && t.n == 2 && parseFloat(t.tok[1], &f) && freqOk(f)) {
    P.freqMhz = f;
    if (applyMode()) showParams();
  } else if (!strcmp(c, "POWER") && t.n == 2 && parseInt(t.tok[1], &a) && a >= -9 && a <= 22) {
    P.powerDbm = a;
    if (applyMode()) showParams();
  } else if (!strcmp(c, "PAYLOAD") && t.n == 2 && parseInt(t.tok[1], &a) && a >= kMinPayload && a <= kMaxPayload) {
    P.payload = a;
    if (applyMode()) showParams();
  } else if (!strcmp(c, "PREAMBLE") && t.n == 2 && parseInt(t.tok[1], &a) && a >= 0 && a <= 255) {
    P.preamble = a;
    if (applyMode()) showParams();
  } else if (!strcmp(c, "VERBOSE") && t.n == 2 && parseInt(t.tok[1], &a)) {
    verbose = a != 0;
    Serial.printf("OK verbose %d\n", verbose ? 1 : 0);
  } else if (!strcmp(c, "TX") && (t.n == 3 || t.n == 4) && parseInt(t.tok[1], &a) && parseInt(t.tok[2], &b) && a > 0 && b >= 0 &&
             (t.n == 3 || parseInt(t.tok[3], &d))) {
    cmdTx(a, b, t.n == 4 ? static_cast<uint32_t>(d) : 1u);
  } else if (!strcmp(c, "RX") && t.n == 2 && parseInt(t.tok[1], &a) && a > 0) {
    cmdRx(a);
  } else if (!strcmp(c, "CW") && t.n == 2 && parseInt(t.tok[1], &a)) {
    cmdCw(a);
  } else {
    Serial.println("ERR comando non riconosciuto (HELP)");
  }
}

void setup() {
  Serial.begin(921600);
  delay(300);
  SPI.begin(pins::kRadioSclk, pins::kRadioMiso, pins::kRadioMosi, pins::kRadioCs);
  Serial.printf("\n%s %s\n", FW_VERSION, CHIP);
  applyMode();
  Serial.println("ATTENZIONE: antenna o carico da 50 ohm collegati PRIMA di trasmettere. HELP per i comandi.");
  showParams();
}

void loop() {
  static char line[96];
  static size_t n = 0;
  while (Serial.available()) {
    const char ch = static_cast<char>(Serial.read());
    if (ch == '\r' || ch == '\n') {
      line[n] = 0;
      if (n) handleLine(line);
      n = 0;
    } else if (n < sizeof(line) - 1) {
      line[n++] = ch;
    }
  }
}
