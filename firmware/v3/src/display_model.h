// Cosa mostrare sull'OLED SSD1306 128x64 della scheda mobile V3: il MODELLO delle schermate, senza dipendenze dalla scheda, provato sul PC (tests/test_display.cpp).
// Fedele alla v2 (third_party/VoLoRa-v2/src/ui.cpp, docs/display.md): stessa struttura (riga 1 nominativo e frequenza, lettera del modo in alto a destra, linea a y=10,
// riga grande a y=16, righe piccole a y=38 e 47, ultima riga a y=56 con a destra la batteria "(Batt=4.12V)"), stesso testo grande (10 caratteri, oltre passa al piccolo),
// stesse barre di avanzamento, righe di al massimo 21 caratteri.  Cosa cambia per il V3: niente PTT e volume (si manda dal telefono), quindi l'ultima riga a sinistra dice
// gradino e potenza ("R10 17dBm") e al posto della lettera del profilo (S/R/M/D/T) c'e' la lettera del livello di potenza: V normale, B BOOST, I IOF MODE.
// STUDIO: mai visto su un OLED vero.
#pragma once
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "battery_info.h"

namespace v3 {
namespace disp {

constexpr int kCols = 21;                                  // caratteri per riga a testo piccolo (6 px l'uno)
constexpr int kBigCols = 10;                               // a testo grande (12 px) ne entrano 10
constexpr uint32_t kLastShownMs = 20000;                   // "Ultimo ..." resta a schermo dopo una ricezione
constexpr uint32_t kNoticeMs = 4000;

enum class Power { Normal, Boost, Iof };
enum class Kind { Normal, Pairing, Message, Menu, Info };

struct Input {
  const char* call = "";
  double freqMhz = 433.7;
  int rung = 10;
  bool linkLost = false;
  Power power = Power::Normal;
  int powerDbm = 17;
  bool radioOk = true;
  bool noCall = false;                                    // nominativo non impostato: la scheda non trasmette
  // telefono
  bool bleConnected = false;                              // telefono collegato (Bluetooth o Wi-Fi della scheda)
  // schermata di collegamento (telefono non collegato): riga in alto, segreto in carattere doppio (codice Bluetooth a 6 cifre o password Wi-Fi a 8), riga in basso
  const char* pairTop = "Collega il telefono";
  const char* pairSecret = "";
  const char* pairBottom = "VoLoRa-V3";
  bool hasPos = false;
  char posText[8] = "";
  // GPS (T-Beam): acceso, fix, satelliti
  bool gpsEnabled = false, gpsFix = false;
  int gpsSats = 0;
  // distanza dal mittente dell'oggetto in arrivo e dall'ultimo ricevuto ("12.3km"), vuota se non nota
  char distText[12] = "";
  char lastDistText[12] = "";
  // invio dal telefono
  bool sending = false;
  int sendPct = 0;
  uint8_t sendKind = 0;                                    // 0 testo, 1 file, 2 immagine
  // ricezione dalla radio
  bool receiving = false;
  const char* rxCall = "";
  int rxPct = 0;
  double rssi = 0, snr = 0;
  // ultimo oggetto ricevuto
  bool haveLast = false;
  const char* lastCall = "";
  uint32_t lastBytes = 0;
  bool lastOk = true;
  uint32_t lastAgoMs = 0;
  // avviso a tempo (CONSEGNATO, FALLITO...), vuoto = nessuno
  const char* notice = "";
  float batteryV = -1.0f;
};

struct Screen {
  Kind kind = Kind::Normal;
  char head[24] = "";            // riga 1: nominativo e frequenza
  char badge = 'V';              // lettera in alto a destra
  char big[24] = "";             // riga grande (a y=16)
  bool bigFits = true;           // false: va a testo piccolo
  char l38[24] = "", l47[24] = "";
  int bar = -1;                  // barra di avanzamento sulla riga 47 (0-100), -1 nessuna
  char code[12] = "";            // schermata di collegamento: codice Bluetooth a 6 cifre o password Wi-Fi a 8
  char name[24] = "";            // nome Bluetooth
  char left[12] = "";            // ultima riga a sinistra
  char batt[20] = "";            // ultima riga a destra
  bool lowBatt = false;
  char footer[24] = "";          // schermata a messaggio: riga in basso (y=52); menu: istruzioni (y=57)
  char rows[5][24] = {"", "", "", "", ""};   // menu e info: righe di testo piccolo da y=12, una ogni 9 punti
  int rowSel = -1;               // menu: riga scelta (in negativo), -1 nessuna
  bool operator==(const Screen& o) const { return std::memcmp(this, &o, sizeof(Screen)) == 0; }
};

inline void put(char* dst, size_t cap, const char* s) { std::snprintf(dst, cap, "%.*s", kCols, s); }

inline const char* kindName(uint8_t k) { return k == 0 ? "testo" : k == 1 ? "file" : "immagine"; }

// Lettera del livello di potenza: V normale, B BOOST, I IOF MODE
inline char badgeFor(Power p) { return p == Power::Iof ? 'I' : p == Power::Boost ? 'B' : 'V'; }

// Glifi 10x9 della lettera in alto a destra (stile della v2: tratti da 2 punti)
inline const char* const* glyph(char b) {
  static const char* const kV[9] = {"XX......XX", "XX......XX", "XX......XX", "XXX....XXX", ".XX....XX.", ".XXX..XXX.", "..XX..XX..", "...XXXX...", "....XX...."};
  static const char* const kB[9] = {"XXXXXXXX..", "XXXXXXXXX.", "XX.....XXX", "XXXXXXXXX.", "XXXXXXXX..", "XX.....XXX", "XX.....XXX", "XXXXXXXXX.", "XXXXXXXX.."};
  static const char* const kI[9] = {"XXXXXXXXXX", "XXXXXXXXXX", "....XX....", "....XX....", "....XX....", "....XX....", "....XX....", "XXXXXXXXXX", "XXXXXXXXXX"};
  return b == 'B' ? kB : b == 'I' ? kI : kV;
}

inline void bottom(Screen* s, const Input& in) {
  std::snprintf(s->left, sizeof(s->left), "R%d %ddBm", in.rung, in.powerDbm);        // al massimo 9 caratteri ("R14 22dBm"): la batteria occupa gli altri 12
  formatBatteryText(s->batt, sizeof(s->batt), in.batteryV);
  s->lowBatt = isLowBattery(in.batteryV);
}

// Schermata normale o di accoppiamento, secondo lo stato
inline void build(const Input& in, Screen* s) {
  *s = Screen();
  std::snprintf(s->head, sizeof(s->head), "%.8s %.3fMHz", in.call[0] ? in.call : "-", in.freqMhz);
  s->badge = badgeFor(in.power);
  bottom(s, in);
  char b[40];
  if (!in.radioOk) {                                        // errore all'avvio: come la v2, "ERRORE" e il nome del blocco
    std::snprintf(s->big, sizeof(s->big), "ERRORE");
    put(s->l38, sizeof(s->l38), "radio");
    return;
  }
  if (in.noCall) {                                          // come la v2 con N0CALL: "SOLO RX" e "Imposta il nominativo"
    std::snprintf(s->big, sizeof(s->big), "SOLO RX");
    put(s->l38, sizeof(s->l38), "Imposta il nominativo");
    std::snprintf(b, sizeof(b), "Codice %.8s", in.pairSecret);
    put(s->l47, sizeof(s->l47), b);
  } else if (in.sending) {
    std::snprintf(s->big, sizeof(s->big), "INVIO");
    if (in.linkLost) put(s->l38, sizeof(s->l38), "Cerco il collegamento");
    else if (in.sendPct <= 0) put(s->l38, sizeof(s->l38), "Trasmetto messaggio");
    else { std::snprintf(b, sizeof(b), "Invio %s %d%%", kindName(in.sendKind), in.sendPct); put(s->l38, sizeof(s->l38), b); }
    if (in.sendPct > 0 && !in.linkLost) s->bar = in.sendPct > 100 ? 100 : in.sendPct;
  } else if (in.receiving) {
    std::snprintf(s->big, sizeof(s->big), "RX %s", in.rxCall[0] ? in.rxCall : "...");
    if (in.rxPct > 0) std::snprintf(b, sizeof(b), "Ricevo messaggio %d%%", in.rxPct > 100 ? 100 : in.rxPct);
    else std::snprintf(b, sizeof(b), "Ricevo il messaggio");
    put(s->l38, sizeof(s->l38), b);
    if (in.distText[0]) std::snprintf(b, sizeof(b), "%s  RSSI %d", in.distText, static_cast<int>(std::lround(in.rssi)));   // come la v2 col messaggio: distanza e RSSI
    else std::snprintf(b, sizeof(b), "RSSI %d  SNR %.1f", static_cast<int>(std::lround(in.rssi)), in.snr);
    put(s->l47, sizeof(s->l47), b);
  } else if (!in.bleConnected) {                            // senza telefono la scheda non puo' mandare ne' accettare: serve il codice per collegarlo
    s->kind = Kind::Pairing;
    std::snprintf(s->code, sizeof(s->code), "%.8s", in.pairSecret);
    put(s->name, sizeof(s->name), in.pairBottom);
    put(s->l38, sizeof(s->l38), in.pairTop);
  } else {
    std::snprintf(s->big, sizeof(s->big), "ASCOLTO");
    if (in.haveLast && in.lastAgoMs < kLastShownMs) {
      int n = std::snprintf(b, sizeof(b), "Ultimo %s%s", in.lastCall[0] ? in.lastCall : "-", in.lastOk ? "" : " ERR");
      if (in.lastDistText[0] && n > 0 && n + 1 + static_cast<int>(std::strlen(in.lastDistText)) <= kCols) std::snprintf(b + n, sizeof(b) - n, " %s", in.lastDistText);   // la distanza solo se la riga resta nei 21 caratteri
      put(s->l38, sizeof(s->l38), b);
      std::snprintf(b, sizeof(b), "%lu byte CRC %s", static_cast<unsigned long>(in.lastBytes), in.lastOk ? "ok" : "NO");
      put(s->l47, sizeof(s->l47), b);
    } else {
      put(s->l38, sizeof(s->l38), "Telefono collegato");
      if (in.gpsEnabled) {                                  // come la v2: stato del GPS sulla riga libera a riposo
        if (in.gpsFix) { std::snprintf(b, sizeof(b), "GPS fix, %d satelliti", in.gpsSats); put(s->l47, sizeof(s->l47), b); }
        else put(s->l47, sizeof(s->l47), "GPS cerco satelliti");
      } else if (in.hasPos) { std::snprintf(b, sizeof(b), "Pos %s", in.posText); put(s->l47, sizeof(s->l47), b); }
      else put(s->l47, sizeof(s->l47), "Manca la posizione");
    }
  }
  s->bigFits = std::strlen(s->big) <= static_cast<size_t>(kBigCols);
  if (in.notice[0] && s->kind == Kind::Normal) put(s->l38, sizeof(s->l38), in.notice);
}

// Schermata di avvio come la v2: nominativo, "AVVIO" grande e "fw <versione>" in basso (se piu' lunga di 18 caratteri si mostra la coda, che ha il codice del commit)
inline void buildStartup(const char* call, const char* version, Screen* s) {
  *s = Screen();
  s->kind = Kind::Message;
  put(s->head, sizeof(s->head), call[0] ? call : "-");
  std::snprintf(s->big, sizeof(s->big), "AVVIO");
  const size_t vl = std::strlen(version);
  char b[40];
  std::snprintf(b, sizeof(b), "fw %s", vl > 18 ? version + (vl - 18) : version);
  put(s->footer, sizeof(s->footer), b);
}

// Menu a bordo (come drawMenu della v2): cinque righe da 9 punti sotto l'intestazione, la voce scelta in negativo; con piu' voci la finestra scorre e la scelta resta visibile.
inline void buildMenu(const Input& in, const char (*labels)[24], size_t count, size_t selected, Screen* s) {
  *s = Screen();
  s->kind = Kind::Menu;
  std::snprintf(s->head, sizeof(s->head), "%.8s %.3fMHz", in.call[0] ? in.call : "-", in.freqMhz);
  s->badge = badgeFor(in.power);
  constexpr size_t kRows = 5;
  const size_t first = selected >= kRows ? selected - (kRows - 1) : 0;
  for (size_t i = first; i < count && i < first + kRows; i++) {
    put(s->rows[i - first], sizeof(s->rows[0]), labels[i]);
    if (i == selected) s->rowSel = static_cast<int>(i - first);
  }
  put(s->footer, sizeof(s->footer), "breve=avanti lungo=ok");
}

// Schermata "Info" della voce di menu: cinque righe fisse (versione, nomi di collegamento, password), per qualche secondo.
inline void buildInfo(const Input& in, const char* l1, const char* l2, const char* l3, const char* l4, const char* l5, Screen* s) {
  *s = Screen();
  s->kind = Kind::Info;
  std::snprintf(s->head, sizeof(s->head), "%.8s %.3fMHz", in.call[0] ? in.call : "-", in.freqMhz);
  s->badge = badgeFor(in.power);
  const char* l[5] = {l1, l2, l3, l4, l5};
  for (int i = 0; i < 5; i++) put(s->rows[i], sizeof(s->rows[0]), l[i] ? l[i] : "");
}

}  // namespace disp
}  // namespace v3
