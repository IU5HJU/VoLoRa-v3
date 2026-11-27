// Prova del MODELLO del display (src/display_model.h, src/battery_info.h) sul PC: ogni schermata sta nelle regole dell'OLED della v2 (righe da 21 caratteri,
// testo grande da 10, niente ritorni a capo) e dice quello che deve dire. Stampa le schermate come testo (un mockup per chi non ha la scheda).
#include <cstdio>
#include <cstring>
#include <string>

#include "../src/display_model.h"

using namespace v3;
using namespace v3::disp;
static int g_fails = 0, g_checks = 0;
#define CHECK(c, ...) do { g_checks++; if (!(c)) { g_fails++; std::printf("FALLITO: "); std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)

static void dump(const char* title, const Screen& s) {
  std::printf("--- %s\n", title);
  if (s.kind == Kind::Message) { std::printf("| %-21s |\n| %-21s | (grande)\n| %-21s |\n", s.head, s.big, s.footer); return; }
  std::printf("| %-21s |%c\n", s.head, s.badge);
  if (s.kind == Kind::Pairing) { std::printf("| %-21s |\n| [%s] (doppio)      |\n| %-21s |\n| %-9s %12s |\n", s.l38, s.code, s.name, s.left, s.batt); return; }
  std::printf("| %-21s |%s\n| %-21s |\n| %-21s |", s.big, s.bigFits ? " (grande)" : " (piccolo)", s.l38, s.bar >= 0 ? "[barra]" : s.l47);
  if (s.bar >= 0) std::printf(" %d%%", s.bar);
  std::printf("\n| %-9s %12s |%s\n", s.left, s.batt, s.lowBatt ? " (batteria in negativo)" : "");
}
// una schermata e' valida se nessuna riga supera i limiti dello schermo
static bool fits(const Screen& s) {
  const size_t c = kCols;
  if (std::strlen(s.head) > c - 2 && s.kind != Kind::Message) return false;            // la lettera parte a x=118: 19 caratteri da 6 punti (114)
  if (std::strlen(s.l38) > c || std::strlen(s.l47) > c || std::strlen(s.footer) > c || std::strlen(s.name) > c) return false;
  if (std::strlen(s.big) > (s.bigFits ? static_cast<size_t>(kBigCols) : c)) return false;
  if (std::strlen(s.left) > 9) return false;                                           // 128 - 72 (batteria) = 56 punti = 9 caratteri
  if (std::strlen(s.batt) > 12) return false;
  return true;
}

int main() {
  Input in;
  in.call = "IU5HJU";
  in.bleConnected = true;
  in.batteryV = 4.12f;
  in.hasPos = true;
  std::snprintf(in.posText, sizeof(in.posText), "JN53ab");
  Screen s;
  // a riposo
  build(in, &s); dump("a riposo, telefono collegato", s);
  CHECK(std::strcmp(s.head, "IU5HJU 433.700MHz") == 0 && s.badge == 'V' && std::strcmp(s.big, "ASCOLTO") == 0 && s.bigFits, "a riposo: intestazione, lettera V e ASCOLTO");
  CHECK(std::strcmp(s.l38, "Telefono collegato") == 0 && std::strcmp(s.l47, "Pos JN53ab") == 0, "a riposo: telefono e posizione");
  CHECK(std::strcmp(s.left, "R10 17dBm") == 0 && std::strcmp(s.batt, "(Batt=4.12V)") == 0 && !s.lowBatt, "ultima riga: gradino e potenza, batteria nel formato di Guzman");
  CHECK(fits(s), "a riposo sta nello schermo");
  in.hasPos = false; build(in, &s);
  CHECK(std::strcmp(s.l47, "Manca la posizione") == 0, "senza posizione lo dice");
  in.hasPos = true;
  // senza telefono: schermata di accoppiamento
  in.bleConnected = false; in.pairSecret = "917558"; in.pairBottom = "VoLoRa-V3 IU5HJU";
  build(in, &s); dump("senza telefono: accoppiamento", s);
  CHECK(s.kind == Kind::Pairing && std::strcmp(s.code, "917558") == 0 && std::strcmp(s.name, "VoLoRa-V3 IU5HJU") == 0 && fits(s), "accoppiamento: codice a 6 cifre e nome Bluetooth");
  // Wi-Fi della scheda: la password a 8 cifre in carattere doppio, la rete in alto e l'indirizzo in basso
  in.pairTop = "WiFi VoLoRa-IU5HJU"; in.pairSecret = "48291637"; in.pairBottom = "http://192.168.4.1"; build(in, &s); dump("senza telefono: Wi-Fi della scheda", s);
  CHECK(s.kind == Kind::Pairing && std::strcmp(s.l38, "WiFi VoLoRa-IU5HJU") == 0 && std::strcmp(s.code, "48291637") == 0 && std::strcmp(s.name, "http://192.168.4.1") == 0 && fits(s), "Wi-Fi: rete, password a 8 cifre e indirizzo");
  in.pairTop = "Collega il telefono"; in.pairSecret = "000042"; in.pairBottom = "VoLoRa-V3 IU5HJU"; build(in, &s);
  CHECK(std::strcmp(s.code, "000042") == 0, "il codice si mostra com'e'");
  in.bleConnected = true;
  // senza nominativo
  in.call = ""; in.noCall = true; in.bleConnected = false; build(in, &s); dump("senza nominativo", s);
  CHECK(std::strcmp(s.big, "SOLO RX") == 0 && std::strcmp(s.l38, "Imposta il nominativo") == 0 && std::strstr(s.l47, "000042") && fits(s), "senza nominativo: SOLO RX e il codice Bluetooth");
  in.call = "IU5HJU"; in.noCall = false; in.bleConnected = true;
  // invio
  in.sending = true; in.sendPct = 0; in.sendKind = 0; build(in, &s);
  CHECK(std::strcmp(s.big, "INVIO") == 0 && std::strcmp(s.l38, "Trasmetto messaggio") == 0 && s.bar < 0, "invio appena partito");
  in.sendPct = 40; in.sendKind = 2; in.rung = 7; build(in, &s); dump("invio immagine 40%", s);
  CHECK(std::strcmp(s.l38, "Invio immagine 40%") == 0 && s.bar == 40 && std::strcmp(s.left, "R7 17dBm") == 0 && fits(s), "invio con barra al 40%%");
  in.sendPct = 100; in.sendKind = 1; build(in, &s);
  CHECK(std::strcmp(s.l38, "Invio file 100%") == 0 && s.bar == 100, "100%%");
  in.sendPct = 20; in.linkLost = true; build(in, &s);
  CHECK(std::strcmp(s.l38, "Cerco il collegamento") == 0 && s.bar < 0 && fits(s), "collegamento perso: cerco");
  in.linkLost = false; in.sending = false;
  // ricezione
  in.receiving = true; in.rxCall = "IZ5FSN"; in.rxPct = 0; in.rssi = -97.4; in.snr = 7.5; build(in, &s);
  CHECK(std::strcmp(s.big, "RX IZ5FSN") == 0 && s.bigFits && std::strcmp(s.l38, "Ricevo il messaggio") == 0 && std::strcmp(s.l47, "RSSI -97  SNR 7.5") == 0, "ricezione all'inizio");
  in.rxPct = 63; in.rssi = -120.2; in.snr = -15.0; build(in, &s); dump("ricezione 63%, caso peggiore", s);
  CHECK(std::strcmp(s.l38, "Ricevo messaggio 63%") == 0 && std::strcmp(s.l47, "RSSI -120  SNR -15.0") == 0 && fits(s), "ricezione al 63%%, riga peggiore da 20 caratteri");
  in.rxCall = "IU5HJU/P"; build(in, &s);
  CHECK(!s.bigFits && std::strcmp(s.big, "RX IU5HJU/P") == 0 && fits(s), "nominativo di 8 caratteri: la riga grande passa al testo piccolo (come la v2)");
  in.receiving = false;
  // ultimo ricevuto
  in.haveLast = true; in.lastCall = "IZ5FSN"; in.lastBytes = 5000; in.lastOk = true; in.lastAgoMs = 1000; build(in, &s); dump("ultimo ricevuto", s);
  CHECK(std::strcmp(s.l38, "Ultimo IZ5FSN") == 0 && std::strcmp(s.l47, "5000 byte CRC ok") == 0, "ultimo ricevuto");
  in.lastOk = false; build(in, &s);
  CHECK(std::strcmp(s.l38, "Ultimo IZ5FSN ERR") == 0 && std::strcmp(s.l47, "5000 byte CRC NO") == 0, "ultimo ricevuto con CRC sbagliato");
  in.lastAgoMs = kLastShownMs + 1; build(in, &s);
  CHECK(std::strcmp(s.l38, "Telefono collegato") == 0, "dopo 20 s torna lo stato di riposo");
  in.haveLast = false;
  // GPS e distanza (come la v2)
  in.gpsEnabled = true; in.gpsFix = false; build(in, &s);
  CHECK(std::strcmp(s.l47, "GPS cerco satelliti") == 0, "GPS acceso senza fix");
  in.gpsFix = true; in.gpsSats = 8; build(in, &s);
  CHECK(std::strcmp(s.l47, "GPS fix, 8 satelliti") == 0 && fits(s), "GPS con fix e satelliti");
  in.gpsEnabled = false;
  in.receiving = true; in.rxCall = "IZ5FSN"; in.rxPct = 10; in.rssi = -97; std::snprintf(in.distText, sizeof(in.distText), "125.8km"); build(in, &s);
  CHECK(std::strcmp(s.l47, "125.8km  RSSI -97") == 0, "ricezione con distanza: distanza e RSSI");
  in.receiving = false; in.haveLast = true; in.lastOk = true; in.lastCall = "IZ5FSN"; in.lastAgoMs = 100; std::snprintf(in.lastDistText, sizeof(in.lastDistText), "12.3km"); build(in, &s);
  CHECK(std::strcmp(s.l38, "Ultimo IZ5FSN 12.3km") == 0 && fits(s), "ultimo con distanza (20 caratteri)");
  in.lastCall = "IU5HJU/P"; in.lastOk = false; build(in, &s);
  CHECK(std::strcmp(s.l38, "Ultimo IU5HJU/P ERR") == 0, "la distanza non si aggiunge se la riga supera i 21 caratteri");
  in.haveLast = false; in.distText[0] = 0; in.lastDistText[0] = 0; in.lastOk = true;
  // livelli di potenza
  in.rung = 10; in.power = Power::Boost; in.powerDbm = 20; build(in, &s);
  CHECK(s.badge == 'B' && std::strcmp(s.left, "R10 20dBm") == 0, "BOOST: lettera B e +20 dBm");
  in.power = Power::Iof; in.powerDbm = 22; in.rung = 14; build(in, &s); dump("IOF MODE, R14", s);
  CHECK(s.badge == 'I' && std::strcmp(s.left, "R14 22dBm") == 0 && fits(s), "IOF MODE: lettera I e +22 dBm, anche a R14");
  CHECK(std::strcmp(glyph('B')[0], "XXXXXXXX..") == 0 && std::strcmp(glyph('I')[0], "XXXXXXXXXX") == 0 && std::strcmp(glyph('V')[8], "....XX....") == 0, "i tre glifi sono diversi e di 10x9 punti");
  for (char c : {'V', 'B', 'I'}) for (int y = 0; y < 9; y++) CHECK(std::strlen(glyph(c)[y]) == 10, "glifo %c riga %d larga 10", c, y);
  in.power = Power::Normal; in.powerDbm = 17; in.rung = 10;
  // avvisi
  in.notice = "CONSEGNATO"; build(in, &s); dump("avviso", s);
  CHECK(std::strcmp(s.l38, "CONSEGNATO") == 0, "l'avviso sostituisce la riga 38");
  in.bleConnected = false; build(in, &s);
  CHECK(s.kind == Kind::Pairing && std::strcmp(s.l38, "Collega il telefono") == 0, "senza telefono l'accoppiamento non e' coperto dagli avvisi");
  in.bleConnected = true; in.notice = "";
  // batteria
  in.batteryV = 3.30f; build(in, &s); dump("batteria scarica", s);
  CHECK(s.lowBatt && std::strcmp(s.batt, "(Batt=3.30V)") == 0, "sotto 3,40 V: in negativo");
  in.batteryV = 3.40f; build(in, &s);
  CHECK(!s.lowBatt, "3,40 V non e' ancora scarica");
  in.batteryV = -1.0f; build(in, &s);
  CHECK(!s.lowBatt && std::strcmp(s.batt, "(Batt=--)") == 0, "batteria assente: (Batt=--)");
  CHECK(std::strlen(s.batt) <= 12, "la batteria sta nei 12 caratteri");
  in.batteryV = 4.12f;
  // errore radio
  in.radioOk = false; build(in, &s); dump("errore radio", s);
  CHECK(std::strcmp(s.big, "ERRORE") == 0 && std::strcmp(s.l38, "radio") == 0, "errore all'avvio");
  in.radioOk = true;
  // nominativo lungo e frequenza alta: l'intestazione sta nei 19 caratteri
  in.call = "IU5HJU/P"; in.freqMhz = 868.0; build(in, &s);
  CHECK(fits(s) && std::strlen(s.head) <= 19, "intestazione con 8 caratteri e 868 MHz: %zu caratteri", std::strlen(s.head));
  // avvio
  buildStartup("IU5HJU", "v0.1.0-rc.1", &s); dump("avvio", s);
  CHECK(std::strcmp(s.big, "AVVIO") == 0 && std::strcmp(s.footer, "fw v0.1.0-rc.1") == 0, "avvio: AVVIO e la versione");
  buildStartup("IU5HJU", "v0.1.0-rc.1-12-g833fcd5-dirty", &s);
  CHECK(std::strlen(s.footer) <= static_cast<size_t>(kCols) && std::strstr(s.footer, "833fcd5-dirty"), "versione lunga: si mostra la coda col codice del commit (%s)", s.footer);
  // menu (come la v2)
  {
    const char* lab[8] = {"Modo Standard", "Modo Range", "Modo Messaggio", "Modo Diretta", "Invia testo", "MeshCom", "MeshCom ascolto", "Wi-Fi"};
    const uint8_t ids[8] = {2, 0, 1, 3, 101, 102, 104, 100};
    bool en[8] = {true, true, true, true, true, true, true, true};
    Input mi; mi.call = "IU5HJU";
    buildMenu(mi, lab, en, ids, 8, 1, 0, &s);
    CHECK(s.kind == Kind::Menu && s.rowSel == 1 && std::strcmp(s.rows[0], "  Modo Standard") == 0 && std::strcmp(s.rows[1], "* Modo Range") == 0, "menu: l'asterisco segna la voce in uso, la scelta e' la seconda");
    CHECK(std::strcmp(s.footer, "PTT=avanti  VOL=ok") == 0, "menu: istruzioni come la v2");
    buildMenu(mi, lab, en, ids, 8, 7, 0, &s);
    CHECK(s.rowSel == 4 && std::strcmp(s.rows[4], "  Wi-Fi") == 0 && std::strcmp(s.rows[0], "  Modo Diretta") == 0, "menu: con otto voci la finestra scorre e la scelta resta visibile");
    en[7] = false;
    buildMenu(mi, lab, en, ids, 8, 0, 255, &s);
    CHECK(s.rowSel == 0 && std::strcmp(s.rows[0], "  Modo Standard") == 0 && std::strcmp(s.rows[4], "  Invia testo") == 0, "menu: all'inizio si vedono le prime cinque");
    buildMenu(mi, lab, en, ids, 8, 7, 255, &s);
    CHECK(std::strncmp(s.rows[4], "  Wi-Fi (presto)", 16) == 0, "menu: le voci non disponibili hanno (presto)");
    for (int i = 0; i < 5; i++) CHECK(std::strlen(s.rows[i]) <= 21, "menu: riga %d entro i 21 caratteri", i);
  }
  // batteria: formato e medie come la v2
  char b[20];
  formatBatteryText(b, sizeof(b), 4.123f); CHECK(std::strcmp(b, "(Batt=4.12V)") == 0, "formato batteria");
  BatterySmoother sm(0.02f); float v = 0; for (int i = 0; i < 200; i++) v = sm.update(i < 1 ? 4.0f : 4.4f);
  CHECK(v > 4.3f && v < 4.4f, "la media lenta segue il salto di tensione (%.3f)", v);
  AverageFilter af; for (int i = 0; i < 40; i++) af.add(i < 24 ? 0.0f : 100.0f);
  CHECK(af.average() == 100.0f, "la media mobile tiene solo le ultime 16 letture");
  std::printf("firmware/v3 display: %d controlli, %d falliti\n", g_checks, g_fails);
  return g_fails ? 1 : 0;
}
