// Prova del DISEGNO dell'OLED (src/display_draw.h) con la libreria VERA Adafruit_GFX 2.0.0 (la versione fissata in platformio.ini), su un canvas da 128x64 a 1 bit (GFXcanvas1).
// Il PC ha solo il minimo di Arduino (tests/arduino_stub); il disegno, il font 5x7 e il ritorno a capo sono quelli della libreria: se una modifica allo schermo fa andare una scritta a capo
// o la fa urtare contro un'altra, qui lo si vede PRIMA di caricare la scheda. Con un argomento scrive anche le schermate come immagini PBM (P1) in quella cartella.
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include <Adafruit_GFX.h>

#include "../src/display_draw.h"
#include "testing.h"

using namespace v3::disp;

// canvas che si accorge dei ritorni a capo (un testo che esce dallo schermo va a capo da solo e finisce sulla riga sotto)
struct Spy : GFXcanvas1 {
  Spy() : GFXcanvas1(128, 64) {}
  int wraps = 0;
  size_t write(uint8_t c) override {
    const int16_t y0 = getCursorY();
    const size_t r = GFXcanvas1::write(c);
    if (c != '\n' && c != '\r' && getCursorY() != y0) wraps++;
    return r;
  }
  int lit() const { int n = 0; for (int y = 0; y < 64; y++) for (int x = 0; x < 128; x++) n += getPixel(x, y) ? 1 : 0; return n; }
  int litRect(int x0, int y0, int x1, int y1) const { int n = 0; for (int y = y0; y <= y1; y++) for (int x = x0; x <= x1; x++) n += getPixel(x, y) ? 1 : 0; return n; }
};

static const char* g_dir = nullptr;
static int g_img = 0;
static void dump(const char* name, const Spy& c) {
  if (!g_dir) return;
  char path[256];
  std::snprintf(path, sizeof(path), "%s/%02d-%s.pbm", g_dir, ++g_img, name);
  FILE* f = std::fopen(path, "w");
  if (!f) return;
  std::fprintf(f, "P1\n128 64\n");
  for (int y = 0; y < 64; y++) { for (int x = 0; x < 128; x++) std::fputc(c.getPixel(x, y) ? '1' : '0', f); std::fputc('\n', f); }
  std::fclose(f);
}

static std::unique_ptr<Spy> render(const Screen& s, const char* name) {
  std::unique_ptr<Spy> c(new Spy());
  c->fillScreen(0);
  drawScreen(*c, s);
  CHECK(c->wraps == 0);                                    // nessuna scritta va a capo da sola
  CHECK(c->lit() > 0);
  dump(name, *c);
  return c;
}

int main(int argc, char** argv) {
  if (argc > 1) g_dir = argv[1];
  // la libreria vera: 6 punti per carattere a dimensione 1, 12 a dimensione 2; 21 e 10 caratteri per riga; a capo al 22esimo
  {
    Spy c; c.setTextSize(1); c.setCursor(0, 0); c.print("123456789012345678901");   // 21 caratteri
    CHECK(c.wraps == 0 && c.getCursorX() == 126 && c.getCursorY() == 0);
    c.print("X");                                                                  // il 22esimo va a capo
    CHECK(c.wraps == 1 && c.getCursorY() == 8);
    Spy d; d.setTextSize(2); d.setCursor(0, 0); d.print("1234567890");
    CHECK(d.wraps == 0 && d.getCursorX() == 120);
    d.print("X");
    CHECK(d.wraps == 1 && d.getCursorY() == 16);
    // il primo carattere "A": la colonna 0 del font e' 0x7C (5 colonne, 7 righe)
    Spy e; e.setTextSize(1); e.setCursor(0, 0); e.print("A");
    CHECK(e.lit() == 16 && e.getPixel(0, 6) == 1 && e.getPixel(0, 0) == 0 && e.getPixel(5, 0) == 0);      // 'A': colonne 0x7C 0x12 0x11 0x12 0x7C = 16 punti
  }

  Input in; in.call = "IU5HJU"; in.bleConnected = true; in.hasPos = true; in.batteryV = 4.12f;
  std::snprintf(in.posText, sizeof(in.posText), "JN53ab");
  Screen s;
  for (Layout lay : {Layout::A, Layout::B, Layout::C}) {
    in.layout = lay;
    const char* ln = lay == Layout::A ? "A" : lay == Layout::B ? "B" : "C";
    char nm[48];
    // a riposo, con il caso peggiore della riga 47 e della prima riga (nominativo di 8 caratteri e 868 MHz = 19 caratteri)
    in.call = "IU5HJU/P"; in.freqMhz = 868.0; in.rung = 14; in.powerDbm = 22; in.power = Power::Iof;
    build(in, &s);
    auto c = render(s, (std::snprintf(nm, sizeof(nm), "%s-riposo-iof", ln), nm));
    CHECK(c->litRect(118, 0, 127, 8) > 0);                                           // la lettera c'e' (I)
    int headRight = 0;                                                              // la scritta della prima riga non tocca la lettera: nessun punto acceso fra x=114 e x=117 nelle righe 0-8
    CHECK(c->litRect(114, 0, 117, 8) == 0);
    (void)headRight;
    in.call = "IU5HJU"; in.freqMhz = 433.7; in.rung = 10; in.powerDbm = 17; in.power = Power::Normal;
    build(in, &s); render(s, (std::snprintf(nm, sizeof(nm), "%s-riposo", ln), nm));
    in.gpsEnabled = true; in.gpsFix = true; in.gpsSats = 12; build(in, &s); render(s, (std::snprintf(nm, sizeof(nm), "%s-gps", ln), nm)); in.gpsEnabled = false;
    // la scritta a sinistra dell'ultima riga e la batteria non si toccano (A e C: 9 + 12 = 21 caratteri, si toccano ma non si sovrappongono)
    build(in, &s);
    auto r = render(s, (std::snprintf(nm, sizeof(nm), "%s-riposo2", ln), nm));
    const int leftW = static_cast<int>(std::strlen(s.left)) * 6, battX = 128 - static_cast<int>(std::strlen(s.batt)) * 6;
    CHECK(leftW <= battX);
    (void)r;
    in.sending = true; in.sendPct = 40; in.sendKind = 2; build(in, &s); render(s, (std::snprintf(nm, sizeof(nm), "%s-invio", ln), nm));
    in.sendPct = 100; build(in, &s); render(s, (std::snprintf(nm, sizeof(nm), "%s-invio100", ln), nm)); in.sending = false;
    in.receiving = true; in.rxCall = "IU5HJU/P"; in.rxPct = 63; in.rssi = -120.2; in.snr = -15.0; std::snprintf(in.distText, sizeof(in.distText), "125.8km"); build(in, &s);
    render(s, (std::snprintf(nm, sizeof(nm), "%s-ricezione", ln), nm)); in.receiving = false; in.distText[0] = 0;
    in.batteryV = 3.3f; build(in, &s); auto lb = render(s, (std::snprintf(nm, sizeof(nm), "%s-batteria-scarica", ln), nm));
    CHECK(lb->litRect(128 - 12 * 6, 55, 127, 63) > 150);                              // la batteria scarica e' in negativo: riquadro pieno
    in.batteryV = 4.12f;
    in.bleConnected = false; in.pairTop = "WiFi VoLoRa-IU5HJU"; in.pairSecret = "48291637"; in.pairBottom = "http://192.168.4.1"; build(in, &s);
    auto pr = render(s, (std::snprintf(nm, sizeof(nm), "%s-collegamento", ln), nm));
    CHECK(pr->litRect(0, 24, 127, 39) > 100);                                          // la password a 8 cifre in carattere doppio sta nello schermo (96 punti)
    in.bleConnected = true;
    in.noCall = true; build(in, &s); render(s, (std::snprintf(nm, sizeof(nm), "%s-senza-nominativo", ln), nm)); in.noCall = false;
    in.radioOk = false; build(in, &s); render(s, (std::snprintf(nm, sizeof(nm), "%s-errore-radio", ln), nm)); in.radioOk = true;
  }
  // menu a otto voci con la finestra che scorre, e schermata di avvio con la versione piu' lunga
  {
    in.layout = Layout::B;
    const char* lab[8] = {"Modo Standard", "Modo Range", "Modo Messaggio", "Modo Diretta", "Invia testo", "MeshCom", "MeshCom ascolto", "Wi-Fi"};
    const uint8_t ids[8] = {2, 0, 1, 3, 101, 102, 104, 100};
    const bool en[8] = {true, true, true, true, true, true, true, false};
    buildMenu(in, lab, en, ids, 8, 7, 0, &s);
    auto m = render(s, "menu");
    CHECK(m->litRect(0, 11 + 4 * 9, 127, 11 + 4 * 9 + 8) > 400);                      // la voce scelta (quinta riga) e' in negativo: riga piena
    buildInfo(in, "fw v0.1.0-rc.1-12-g833fcd5-d", "BT VoLoRa-V3 IU5HJU", "WiFi VoLoRa-IU5HJU", "Pass 48291637", "http://192.168.4.1", &s);
    render(s, "informazioni");
    buildStartup("IU5HJU/P", "v0.1.0-rc.1-12-g833fcd5-dirty", &s);
    render(s, "avvio");
  }
  TEST_MAIN_END();
}
