// Prova della FREQUENZA CONFIGURABILE (src/freq.h) sul PC: comando FREQ, controllo del solo campo di sintonia del chip, e la frequenza che arriva fino alla maschera dei gradini
// annunciata nell'HELLO (i limiti dei chip dipendono dalla frequenza). Nessun altro limite: vale docs/regole-radioamatoriali.md.
#include <cstdio>
#include <random>

#include "../src/freq.h"
#include "sim_world.h"

static int g_fails = 0, g_checks = 0;
#define CHECK(c, ...) do { g_checks++; if (!(c)) { g_fails++; std::printf("FALLITO: "); std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)

static FreqParse P(const char* l, bool s1262) { return parseFreq(l, s1262); }

int main() {
  // comando
  CHECK(P("CALL IU5HJU", false).cmd == FreqCmd::NotFreq && P("FREQUENZA 1", false).cmd == FreqCmd::NotFreq && P("", false).cmd == FreqCmd::NotFreq, "altre righe non sono FREQ");
  CHECK(P("FREQ", false).cmd == FreqCmd::Show && P("  freq  ", true).cmd == FreqCmd::Show, "FREQ da solo mostra");
  FreqParse r = P("FREQ 433.700", false);
  CHECK(r.cmd == FreqCmd::Set && r.khz == 433700.0, "433.700 -> 433700 kHz (%.1f)", r.khz);
  r = P("freq 433,7", false);
  CHECK(r.cmd == FreqCmd::Set && r.khz == 433700.0, "virgola decimale");
  r = P("FREQ 434", false);
  CHECK(r.cmd == FreqCmd::Set && r.khz == 434000.0, "senza decimali");
  r = P("FREQ 438.12", false);
  CHECK(r.cmd == FreqCmd::Set && r.khz == 438120.0, "due decimali: 438.12 -> 438120 (%.1f)", r.khz);
  r = P("FREQ 433.705", false);
  CHECK(r.cmd == FreqCmd::Set && r.khz == 433705.0, "risoluzione di 1 kHz");
  CHECK(P("FREQ 433.7051", false).cmd == FreqCmd::Invalid, "oltre 3 decimali");
  CHECK(P("FREQ abc", false).cmd == FreqCmd::Invalid && P("FREQ 433.7.1", false).cmd == FreqCmd::Invalid && P("FREQ -5", false).cmd == FreqCmd::Invalid && P("FREQ 433.7 MHz", false).cmd == FreqCmd::Invalid && P("FREQ .5", false).cmd == FreqCmd::Invalid, "numeri sbagliati");
  CHECK(P("FREQ 12345", false).cmd == FreqCmd::Invalid, "numero troppo grande");
  // campo di sintonia: l'unico controllo
  CHECK(P("FREQ 137", false).cmd == FreqCmd::Set && P("FREQ 175", false).cmd == FreqCmd::Set && P("FREQ 410", false).cmd == FreqCmd::Set && P("FREQ 525", false).cmd == FreqCmd::Set, "SX1278: estremi dentro");
  CHECK(P("FREQ 136.999", false).cmd == FreqCmd::Invalid && P("FREQ 175.001", false).cmd == FreqCmd::Invalid && P("FREQ 300", false).cmd == FreqCmd::Invalid && P("FREQ 409.999", false).cmd == FreqCmd::Invalid && P("FREQ 525.001", false).cmd == FreqCmd::Invalid, "SX1278: fuori campo");
  CHECK(P("FREQ 868", false).cmd == FreqCmd::Invalid, "SX1278 non arriva a 868 MHz");
  CHECK(P("FREQ 150", true).cmd == FreqCmd::Set && P("FREQ 433.7", true).cmd == FreqCmd::Set && P("FREQ 868", true).cmd == FreqCmd::Set && P("FREQ 960", true).cmd == FreqCmd::Set, "SX1262: dentro");
  CHECK(P("FREQ 149.999", true).cmd == FreqCmd::Invalid && P("FREQ 960.001", true).cmd == FreqCmd::Invalid, "SX1262: fuori campo");
  CHECK(std::strstr(P("FREQ 300", false).why, "137-175") != nullptr && std::strstr(P("FREQ 100", true).why, "150-960") != nullptr, "la ragione dice il campo del chip");
  // nessun'altra restrizione: un canale qualunque dentro il campo (anche fuori dalle tabelle del progetto) e' valido, nessuna avvertenza
  CHECK(P("FREQ 439.9", false).cmd == FreqCmd::Set && P("FREQ 144.9", false).cmd == FreqCmd::Set && P("FREQ 446", false).cmd == FreqCmd::Set && P("FREQ 470.5", true).cmd == FreqCmd::Set, "canali liberi dentro il campo del chip");

  // la frequenza arriva alla maschera dei gradini della stazione (HELLO)
  const uint8_t call[] = {'I', 'U', '5', 'H', 'J', 'U'};
  struct NullRadio : Radio { void setRung(int) override {} bool transmit(const uint8_t*, size_t) override { return true; } double random() override { return 0.5; } } nr;
  struct NullStore : Store { void reset(uint16_t) override {} void put(uint16_t, const uint8_t*, size_t) override {} size_t get(uint16_t, uint8_t*) override { return 0; } } ns;
  const double fr[] = {137000, 150000, 433700, 438120, 525000, 868000, 915000, 960000};
  int diff = 0;
  for (double khz : fr) for (int chip = 0; chip < 2; chip++) for (int tcxo = 0; tcxo < 2; tcxo++) {
    if (!inTuning(chip == 1, khz)) continue;
    Station st(call, 6, chip == 1, tcxo == 1, &nr, &ns, kWindowFrames, true, 0, khz);
    const uint16_t want = rungMask(chip == 1, tcxo == 1, khz);
    CHECK(st.receiver().mask() == want, "maschera a %.0f kHz chip %d tcxo %d: 0x%04X invece di 0x%04X", khz, chip, tcxo, st.receiver().mask(), want);
    if (want != rungMask(chip == 1, tcxo == 1)) diff++;
  }
  std::printf("maschere diverse da quella a 433,7 MHz in %d combinazioni su %zu frequenze\n", diff, sizeof(fr) / sizeof(fr[0]));
  CHECK(diff > 0, "la frequenza cambia davvero la maschera in almeno un caso (altrimenti la prova non dice niente)");

  // due stazioni SX1262 a 868 MHz: il trasferimento riesce (la frequenza non cambia il protocollo)
  {
    ChannelParams cp{-110.0, 0, 0, 1, "costante"};
    World w(5, cp);
    MemStore sA, sB;
    const uint8_t cb[] = {'I', 'K', '5', 'X', 'Y', 'Z'};
    Station a(call, 6, true, false, &w.radio[0], &sA, kWindowFrames, true, 0, 868000.0), b(cb, 6, true, false, &w.radio[1], &sB, kWindowFrames, true, 0, 868000.0);
    w.st[0] = &a; w.st[1] = &b;
    std::mt19937_64 rng(77);
    std::vector<uint8_t> obj(4000);
    for (auto& x : obj) x = static_cast<uint8_t>(rng() & 255);
    const uint16_t ends[3] = {84, 167, 250};
    a.startSend(obj.data(), obj.size(), ends, 3, 600.0, 9);
    w.run(3600, [](World& ww) { return ww.st[0]->sendFinished(); });
    CHECK(a.sendOk() && b.receiver().doneOk() && sB.joined(obj.size()) == obj, "868 MHz SX1262: oggetto consegnato identico (ok %d, tempo %.0f s)", a.sendOk() ? 1 : 0, w.t);
    std::printf("SX1262 a 868 MHz, 4000 byte a -110 dBm: consegnato in %.0f s\n", w.t);
  }
  std::printf("firmware/v3 frequenza: %d controlli, %d falliti\n", g_checks, g_fails);
  return g_fails ? 1 : 0;
}
