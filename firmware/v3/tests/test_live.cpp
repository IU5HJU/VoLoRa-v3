// Prova del PONTE COLLEGATO AL MEZZO (src/live_bridge.h) sul PC: un telefono finto (buffer, E_PULL servite con ritardo BLE) -> LiveBridge + Station A -> canale radio con perdite
// -> Station B + LiveBridge -> un secondo telefono finto. Si controlla che l'oggetto arrivi identico da telefono a telefono e che i casi limite (errori, caduta del collegamento,
// annullo, telefono sparito, destinatario senza telefono) si comportino come da specifica (docs/ble-telefono.md).
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <random>
#include <string>
#include <vector>

#include "../src/live_bridge.h"
#include "../src/position.h"
#include "sim_world.h"

using namespace v3::ble;
namespace bd = v3::ble::detail;

static int g_fails = 0, g_checks = 0;
#define CHECK(c, ...) do { g_checks++; if (!(c)) { g_fails++; std::printf("FALLITO: "); std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)

// il telefono: tiene l'oggetto, risponde alle E_PULL con il ritardo del BLE, registra gli eventi
struct Phone : LiveSink {
  World* w = nullptr;
  LiveBridge* br = nullptr;
  std::vector<uint8_t> obj;
  uint16_t objId = 0;
  bool connected = true;
  int epoch = 0;
  double latency = 0.10, chunkGap = 0.015;
  size_t chunk = 100;
  int pulls = 0, done = -1, beginOk = 0, progress = 0, rxEvents = 0;
  int diagWhy = -1, diagLayers = -1, diagRung = -1, diagPct = -1, diagSecs = -1; uint32_t diagBytes = 0;
  std::vector<std::string> logs;
  void log(const char* l) override { logs.push_back(l); }
  std::vector<int> errs;
  std::vector<uint8_t> rx;
  uint16_t rxObj = 0; uint8_t rxKind = 0; uint32_t rxSize = 0, rxCrc = 0; std::string rxFrom;

  void evt(const uint8_t* d, size_t n) override {
    if (d[0] == E_PULL) {
      pulls++;
      if (!connected) return;
      const uint32_t off = bd::rd(d + 3, 3), len = bd::rd(d + 6, 2);
      const int ep = epoch;
      size_t sent = 0;
      for (int i = 0; sent < len; i++) {
        const size_t m = std::min<size_t>(chunk, len - sent);
        const uint32_t o = off + static_cast<uint32_t>(sent);
        w->schedule(latency + i * chunkGap, [this, ep, o, m] {
          if (!connected || ep != epoch || o + m > obj.size()) return;
          std::vector<uint8_t> f(5 + m);
          bd::wr(f.data(), objId, 2); bd::wr(f.data() + 2, o, 3);
          memcpy(f.data() + 5, obj.data() + o, m);
          br->onData(f.data(), f.size());
        });
        sent += m;
      }
    } else if (d[0] == E_BEGIN_OK) beginOk++;
    else if (d[0] == E_DONE) done = d[3];
    else if (d[0] == E_ERR) errs.push_back(d[3]);
    else if (d[0] == E_PROGRESS) progress++;
    else if (d[0] == E_DIAG && n == 12) { diagWhy = d[3]; diagLayers = d[4]; diagBytes = bd::rd(d + 5, 3); diagRung = d[8]; diagPct = d[9]; diagSecs = static_cast<int>(bd::rd(d + 10, 2)); }
    else if (d[0] == E_RX) {
      rxEvents++;
      rxObj = static_cast<uint16_t>(bd::rd(d + 1, 2)); rxKind = d[3]; rxSize = bd::rd(d + 4, 3); rxCrc = bd::rd(d + 7, 4);
      rxFrom.assign(reinterpret_cast<const char*>(d + 12), d[11]);
      rx.assign(rxSize, 0);
    }
    (void)n;
  }
  void rxChunk(uint16_t o, uint32_t off, const uint8_t* d, size_t n) override {
    if (o == rxObj && off + n <= rx.size()) memcpy(rx.data() + off, d, n);
  }
  void drop() { connected = false; epoch++; br->onDisconnect(); }
  void back() { connected = true; br->onConnect(); }
};

static std::vector<uint8_t> encBegin(uint16_t obj, uint8_t kind, const std::vector<uint8_t>& data, const std::vector<uint32_t>& ends, const char* dest = "IK5XYZ", const char* name = "") {
  std::vector<uint8_t> b;
  b.push_back(C_BEGIN);
  uint8_t t[4];
  bd::wr(t, obj, 2); b.insert(b.end(), t, t + 2);
  b.push_back(kind);
  bd::wr(t, static_cast<uint32_t>(data.size()), 3); b.insert(b.end(), t, t + 3);
  bd::wr(t, v3::img::crc32(data.data(), data.size()), 4); b.insert(b.end(), t, t + 4);
  b.push_back(0); b.push_back(0); b.push_back(0); b.push_back(0);            // larghezza, altezza
  b.push_back(static_cast<uint8_t>(ends.size()));
  for (uint32_t e : ends) { bd::wr(t, e, 3); b.insert(b.end(), t, t + 3); }
  b.push_back(static_cast<uint8_t>(strlen(dest))); b.insert(b.end(), dest, dest + strlen(dest));
  b.push_back(static_cast<uint8_t>(strlen(name))); b.insert(b.end(), name, name + strlen(name));
  return b;
}
static std::vector<uint8_t> cmd3(uint8_t c, uint16_t obj) { return {c, static_cast<uint8_t>(obj >> 8), static_cast<uint8_t>(obj & 255)}; }
static std::vector<uint8_t> randomBytes(size_t n, uint64_t seed) { std::mt19937_64 r(seed); std::vector<uint8_t> v(n); for (auto& x : v) x = static_cast<uint8_t>(r() & 255); return v; }

static std::function<bool()> g_cond;
static bool condStop(World&) { return g_cond(); }

struct Rig {
  World w;
  MemStore sA, sB;
  Phone pA, pB;
  Station a, b;
  LiveBridge brA, brB;
  static const uint8_t* callA() { static const uint8_t c[] = {'I', 'U', '5', 'H', 'J', 'U'}; return c; }
  static const uint8_t* callB() { static const uint8_t c[] = {'I', 'K', '5', 'X', 'Y', 'Z'}; return c; }
  Rig(uint64_t seed, double prx, const char* chipA = "SX1278", const char* chipB = "SX1278", uint32_t rxMaxB = 32768)
      : w(seed, ChannelParams{prx, 0, 0, 1, "costante"}),
        a(callA(), 6, std::string(chipA) == "SX1262", false, &w.radio[0], &sA, kWindowFrames, true, 0),
        b(callB(), 6, std::string(chipB) == "SX1262", false, &w.radio[1], &sB, kWindowFrames, true, 0),
        brA(&pA, &a, "IU5HJU", std::string(chipA) == "SX1262", rungMask(std::string(chipA) == "SX1262", false), &sA, 32768),
        brB(&pB, &b, "IK5XYZ", std::string(chipB) == "SX1262", rungMask(std::string(chipB) == "SX1262", false), &sB, rxMaxB) {
    w.st[0] = &a; w.st[1] = &b;
    pA.w = pB.w = &w; pA.br = &brA; pB.br = &brB;
    w.tickHook = [this](double t) { brA.poll(t); brB.poll(t); };
    w.wakeHook = [](double t) { return t + 0.05; };
  }
  void position(LiveBridge& br) { const uint8_t p[] = {C_POSITION, 0, 'J', 'N', '5', '3', 'a', 'b'}; br.onCommand(p, sizeof(p)); }
  void send(uint16_t id, uint8_t kind, const std::vector<uint8_t>& data, const std::vector<uint32_t>& ends) {
    pA.obj = data; pA.objId = id;
    const std::vector<uint8_t> b = encBegin(id, kind, data, ends);
    brA.onCommand(b.data(), b.size());
  }
  void runUntilDone(double maxT = 3 * 3600.0) { g_cond = [this] { return pA.done >= 0; }; w.run(maxT, condStop); }
  // aspetta che il telefono B (o A) abbia ricevuto tutto l'oggetto passato dalla scheda
  void settleB(double cap = 300) { const double end = w.t + cap; g_cond = [this, end] { return w.t >= end || (pB.rxEvents > 0 && !brB.rxBusy()); }; w.run(end + 1, condStop); }
  void settleA(double cap = 300) { const double end = w.t + cap; g_cond = [this, end] { return w.t >= end || (pA.rxEvents > 0 && !brA.rxBusy()); }; w.run(end + 1, condStop); }
  void runFor(double sec) { const double end = w.t + sec; g_cond = [this, end] { return w.t >= end || pA.done >= 0; }; w.run(end + 1, condStop); }
};

static void checkDelivered(const char* name, Rig& r, const std::vector<uint8_t>& obj, uint8_t kind, bool expectFull = true) {
  CHECK(r.pA.done == DONE_DELIVERED, "%s: il mittente deve avere E_DONE consegnato (ha %d)", name, r.pA.done);
  CHECK(r.pB.rxEvents == 1, "%s: il destinatario riceve un solo E_RX (%d)", name, r.pB.rxEvents);
  CHECK(r.pB.rxFrom == "IU5HJU", "%s: E_RX porta il nominativo del mittente ('%s')", name, r.pB.rxFrom.c_str());
  CHECK(r.pB.rxKind == kind, "%s: tipo %d invece di %d", name, r.pB.rxKind, kind);
  if (expectFull) {
    CHECK(r.pB.rxSize == obj.size(), "%s: dimensione %u invece di %zu", name, r.pB.rxSize, obj.size());
    CHECK(r.pB.rx == obj, "%s: l'oggetto al telefono B non e' identico all'originale", name);
  }
  CHECK(v3::img::crc32(r.pB.rx.data(), r.pB.rx.size()) == r.pB.rxCrc, "%s: il CRC di E_RX non torna con i byte passati al telefono", name);
  CHECK(!r.brA.stats().crcMismatch, "%s: il CRC dei blocchi del telefono non torna con quello di BEGIN", name);
  CHECK(r.brA.held() <= kLiveBlocks * kBlock, "%s: la scheda tiene piu' di %d blocchi", name, kLiveBlocks);
  CHECK(r.b.receiver().offerHasPos() && memcmp(r.b.receiver().offerPos(), "\0JN53ab", 7) == 0, "%s: l'OFFER porta la posizione del mittente", name);
}

int main() {
  // 1. testo corto, collegamento buono
  {
    Rig r(1, -100.0);
    r.position(r.brA); r.position(r.brB);
    const std::vector<uint8_t> obj = randomBytes(200, 11);
    r.send(7, kKindText, obj, {200});
    CHECK(r.pA.beginOk == 1, "BEGIN_OK atteso (%d)", r.pA.beginOk);
    r.runUntilDone();
    std::printf("testo 200 B       -100 dBm: E_DONE %d dopo %.1f s, E_RX %d, pull %d\n", r.pA.done, r.w.t, r.pB.rxEvents, r.pA.pulls);
    r.settleB();
    checkDelivered("testo", r, obj, kKindText);
    CHECK(r.pA.diagWhy == 0 && r.pA.diagLayers == 1 && r.pA.diagBytes == 200 && r.pA.diagPct == 100, "E_DIAG consegnato: motivo 0, 1 livello, 200 byte, 100%% (%d %d %u %d)", r.pA.diagWhy, r.pA.diagLayers, r.pA.diagBytes, r.pA.diagPct);
    CHECK(r.pA.logs.size() == 2 && r.pA.logs[0].find("inizio invio") == 0 && r.pA.logs[1].find("fine invio") == 0, "il registro ha l'inizio e la fine dell'invio");
  }
  // 2. immagine a tre livelli (fine dei livelli allineata a 16 byte), canale mediocre
  {
    Rig r(2, -118.0);
    r.position(r.brA); r.position(r.brB);
    const std::vector<uint8_t> obj = randomBytes(20000, 22);
    r.send(8, kKindImage, obj, {6672, 13344, 20000});
    r.runUntilDone();
    r.settleB();
    std::printf("immagine 20000 B  -118 dBm: E_DONE %d dopo %.0f s, pull %d (di nuovo %u), blocchi in cache al massimo %d, progressi %d\n", r.pA.done, r.w.t, r.pA.pulls, r.brA.stats().repulls, kLiveBlocks, r.pA.progress);
    checkDelivered("immagine", r, obj, kKindImage);
    CHECK(r.pA.pulls >= 20, "immagine: servono almeno 20 blocchi dal telefono (%d)", r.pA.pulls);
    CHECK(r.pA.progress >= 1, "immagine: almeno un E_PROGRESS");
  }
  // 3. errori di BEGIN
  {
    Rig r(3, -100.0);
    const std::vector<uint8_t> obj = randomBytes(100, 33);
    r.send(1, kKindText, obj, {100});                            // senza posizione
    CHECK(r.pA.errs.size() == 1 && r.pA.errs[0] == ERR_NO_POSITION, "senza posizione: ERR_NO_POSITION");
    r.position(r.brA);
    r.send(2, 9, obj, {100});
    CHECK(r.pA.errs.size() == 2 && r.pA.errs[1] == ERR_BAD_KIND, "tipo sconosciuto: ERR_BAD_KIND");
    r.send(3, kKindFile, randomBytes(70000, 5), {70000});
    CHECK(r.pA.errs.size() == 3 && r.pA.errs[2] == ERR_TOO_BIG, "oltre 64 kB: ERR_TOO_BIG");
    r.send(4, kKindText, randomBytes(1025, 6), {1025});
    CHECK(r.pA.errs.size() == 4 && r.pA.errs[3] == ERR_TOO_BIG, "testo oltre 1 kB: ERR_TOO_BIG");
    r.send(5, kKindText, obj, {100});
    CHECK(r.pA.beginOk == 1, "un BEGIN valido dopo gli errori parte");
    const std::vector<uint8_t> b2 = encBegin(6, kKindText, obj, {100});
    r.brA.onCommand(b2.data(), b2.size());
    CHECK(r.pA.errs.size() == 5 && r.pA.errs[4] == ERR_BUSY, "un secondo oggetto mentre uno e' in corso: ERR_BUSY");
    const uint8_t bad[] = {C_HELLO, 1};
    (void)bad;
  }
  // 4. la connessione BLE cade a meta' e torna: RESUME, i blocchi persi si richiedono di nuovo, l'oggetto arriva identico
  {
    Rig r(4, -105.0);
    r.position(r.brA); r.position(r.brB);
    const std::vector<uint8_t> obj = randomBytes(15000, 44);
    r.send(9, kKindFile, obj, {15000});
    r.runFor(8);
    CHECK(r.pA.done < 0, "caduta: a 8 s l'invio e' ancora in corso");
    r.pA.drop();
    r.runFor(6);                                                 // la scheda aspetta il blocco che non arriva
    r.pA.back();
    const std::vector<uint8_t> rs = cmd3(C_RESUME, 9);
    r.brA.onCommand(rs.data(), rs.size());
    r.runUntilDone();
    r.settleB();
    std::printf("caduta BLE 6 s    -105 dBm: E_DONE %d dopo %.0f s, pull %d, richiesti di nuovo %u, attesa massima di un blocco %u ms\n", r.pA.done, r.w.t, r.pA.pulls, r.brA.stats().repulls, r.brA.stats().maxStallMs);
    checkDelivered("caduta", r, obj, kKindFile);
  }
  // 5. annullo
  {
    Rig r(5, -105.0);
    r.position(r.brA); r.position(r.brB);
    const std::vector<uint8_t> obj = randomBytes(15000, 55);
    r.send(10, kKindFile, obj, {15000});
    r.runFor(10);
    const std::vector<uint8_t> c = cmd3(C_CANCEL, 10);
    r.brA.onCommand(c.data(), c.size());
    CHECK(r.pA.done == DONE_CANCELLED, "annullo: E_DONE annullato (%d)", r.pA.done);
    CHECK(r.pA.diagWhy == kDiagCancelled, "annullo: E_DIAG 101 (%d)", r.pA.diagWhy);
    CHECK(!r.a.sending(), "annullo: la stazione non trasmette piu'");
    const std::vector<uint8_t> o2 = randomBytes(300, 56);
    r.pA.done = -1;
    r.send(11, kKindText, o2, {300});                            // si puo' mandare altro subito
    CHECK(r.pA.beginOk == 2, "dopo l'annullo un nuovo oggetto parte");
    const std::vector<uint8_t> c2 = cmd3(C_CANCEL, 99);
    r.brA.onCommand(c2.data(), c2.size());
    CHECK(!r.pA.errs.empty() && r.pA.errs.back() == ERR_UNKNOWN_OBJ, "annullo di un oggetto sconosciuto: ERR_UNKNOWN_OBJ");
  }
  // 6. il telefono sparisce: dopo 60 s senza byte l'invio si chiude fallito
  {
    Rig r(6, -100.0);
    r.position(r.brA); r.position(r.brB);
    const std::vector<uint8_t> obj = randomBytes(8000, 66);
    r.send(12, kKindFile, obj, {8000});
    r.runFor(4);
    r.pA.drop();
    r.runUntilDone(600);
    std::printf("telefono sparito: E_DONE %d dopo %.0f s\n", r.pA.done, r.w.t);
    CHECK(r.pA.done == -1 || r.pA.done == DONE_FAILED, "telefono sparito: l'esito non puo' essere consegnato (%d)", r.pA.done);
    // senza telefono collegato E_DONE non si notifica: al ritorno RESUME lo recupera
    r.pA.back();
    const std::vector<uint8_t> rs = cmd3(C_RESUME, 12);
    r.brA.onCommand(rs.data(), rs.size());
    CHECK(r.pA.done == DONE_FAILED, "dopo il ritorno RESUME dice 'fallito' (%d)", r.pA.done);
    CHECK(r.brA.stats().maxStallMs > 59000, "stallo registrato");
    CHECK(!r.a.sending(), "dopo lo stallo la stazione non trasmette piu'");
  }
  // 7. il destinatario non ha il telefono: non accetta, il mittente chiude fallito
  {
    Rig r(7, -100.0);
    r.position(r.brA);
    r.pB.drop();
    const std::vector<uint8_t> obj = randomBytes(500, 77);
    r.send(13, kKindText, obj, {500});
    r.runUntilDone(2 * 3600.0);
    std::printf("destinatario senza telefono: E_DONE %d dopo %.0f s, E_RX %d\n", r.pA.done, r.w.t, r.pB.rxEvents);
    CHECK(r.pA.done == DONE_FAILED, "senza telefono dall'altra parte l'invio fallisce (%d)", r.pA.done);
    CHECK(r.pA.diagWhy == 3, "senza telefono dall'altra parte il motivo e' 'offerta' (%d)", r.pA.diagWhy);
    CHECK(r.pB.rxEvents == 0, "senza telefono non c'e' nessun E_RX");
  }
  // 8. l'oggetto supera quello che il destinatario puo' tenere
  {
    Rig r(8, -100.0, "SX1278", "SX1278", 4096);
    r.position(r.brA); r.position(r.brB);
    const std::vector<uint8_t> obj = randomBytes(6000, 88);
    r.send(14, kKindFile, obj, {6000});
    r.runUntilDone(2 * 3600.0);
    CHECK(r.pA.done == DONE_FAILED && r.pB.rxEvents == 0, "oggetto troppo grande per il destinatario: fallito e nessun E_RX (%d, %d)", r.pA.done, r.pB.rxEvents);
  }
  // 9. oggetto massimo (64 kB) con un buon collegamento tra SX1262
  {
    Rig r(9, -100.0, "SX1262", "SX1262", 65536);
    r.position(r.brA); r.position(r.brB);
    const std::vector<uint8_t> obj = randomBytes(65536, 99);
    r.send(15, kKindFile, obj, {65536});
    r.runUntilDone();
    r.settleB();
    std::printf("oggetto 64 kB     -100 dBm SX1262: E_DONE %d dopo %.0f s, pull %d (di nuovo %u)\n", r.pA.done, r.w.t, r.pA.pulls, r.brA.stats().repulls);
    checkDelivered("64 kB", r, obj, kKindFile);
  }
  // 10. mittente e destinatario a ruoli invertiti nella stessa prova: B manda ad A mentre A ha appena finito
  {
    Rig r(10, -100.0);
    r.position(r.brA); r.position(r.brB);
    const std::vector<uint8_t> o1 = randomBytes(1000, 101);
    r.send(16, kKindText, o1.size() > 1024 ? o1 : o1, {1000});
    r.runUntilDone();
    r.settleB();
    CHECK(r.pB.rx == o1, "andata: oggetto identico");
    // ora B manda ad A
    const std::vector<uint8_t> o2 = randomBytes(900, 102);
    r.pB.obj = o2; r.pB.objId = 17; r.pB.done = -1;
    const std::vector<uint8_t> b = encBegin(17, kKindText, o2, {900});
    r.brB.onCommand(b.data(), b.size());
    g_cond = [&r] { return r.pB.done >= 0; };
    r.w.run(r.w.t + 3 * 3600.0, condStop);
    r.settleA();
    std::printf("andata e ritorno: E_DONE ritorno %d, E_RX su A %d\n", r.pB.done, r.pA.rxEvents);
    CHECK(r.pB.done == DONE_DELIVERED && r.pA.rx == o2, "ritorno: oggetto identico al telefono A (%d)", r.pB.done);
  }
  // 11. canale cattivo con oggetto lungo: le ritrasmissioni rileggono pezzi gia' passati (dalla cache, o richiesti di nuovo al telefono se buttati)
  {
    Rig r(11, -124.0);
    r.position(r.brA); r.position(r.brB);
    const std::vector<uint8_t> obj = randomBytes(30000, 111);
    r.send(18, kKindImage, obj, {10000, 20000, 30000});
    r.runUntilDone(6 * 3600.0);
    r.settleB();
    std::printf("immagine 30000 B  -124 dBm: E_DONE %d dopo %.0f s, pull %d (di nuovo %u)\n", r.pA.done, r.w.t, r.pA.pulls, r.brA.stats().repulls);
    CHECK(r.pA.done == DONE_DELIVERED || r.pA.done == DONE_FAILED, "canale cattivo: esito definito (%d)", r.pA.done);
    if (r.pA.done == DONE_DELIVERED) checkDelivered("canale cattivo", r, obj, kKindImage);
    CHECK(!r.brA.stats().crcMismatch, "canale cattivo: CRC dei blocchi coerente");
  }
  // 12. posizione GPS della scheda: se c'e' un fix va nell'OFFER al posto del locatore del telefono; senza fix torna il locatore; senza telefono e con il GPS si parte lo stesso
  {
    Rig r(12, -100.0);
    r.position(r.brA); r.position(r.brB);                 // locatore JN53ab dal telefono
    v3::Position gp; gp.valid = true; gp.fromGps = true; gp.latE7 = 437696000; gp.lonE7 = 112558000;
    uint8_t blk[7];
    CHECK(v3::encodePosition(gp, blk), "il blocco GPS si codifica");
    r.brA.setGps(blk);
    CHECK(r.brA.positionBlock()[0] == 1, "con il GPS la posizione e' quella del GPS");
    const std::vector<uint8_t> o1 = randomBytes(300, 121);
    r.send(30, kKindText, o1, {300});
    r.runUntilDone(); r.settleB();
    CHECK(r.pA.done == DONE_DELIVERED && r.b.receiver().offerHasPos() && r.b.receiver().offerPos()[0] == 1, "l'OFFER porta la posizione GPS");
    v3::Position got;
    CHECK(v3::positionFromBlock(r.b.receiver().offerPos(), got) && got.fromGps && std::abs(got.latE7 - gp.latE7) < 20000 && std::abs(got.lonE7 - gp.lonE7) < 30000, "la posizione GPS arriva al ricevente entro 2 m");
    // il ricevente puo' calcolare la distanza da se' (locatore JN53ab, centro 43.0625 N 10.0417 E)
    v3::Position mine;
    CHECK(v3::positionFromBlock(r.brB.positionBlock(), mine) && !mine.fromGps, "il ricevente ha il locatore del suo telefono");
    const double km = v3::distanceKm(got, mine);
    std::printf("distanza fra il GPS di A (43.7696 N 11.2558 E) e il locatore di B (JN53ab): %.1f km\n", km);
    CHECK(km > 125.0 && km < 126.5, "distanza attesa 125,8 km (0,707 gradi di latitudine = 78,6 km e 1,214 gradi di longitudine a 43,4 N = 98,2 km): %.1f", km);
    // fix perso: torna il locatore
    r.brA.setGps(nullptr);
    CHECK(r.brA.positionBlock()[0] == 0 && std::memcmp(r.brA.positionBlock() + 1, "JN53ab", 6) == 0, "senza fix torna il locatore del telefono");
  }
  // 13. solo GPS, nessuna posizione dal telefono: l'invio parte (la posizione c'e')
  {
    Rig r(13, -100.0);
    r.position(r.brB);
    v3::Position gp; gp.valid = true; gp.fromGps = true; gp.latE7 = 437696000; gp.lonE7 = 112558000;
    uint8_t blk[7]; v3::encodePosition(gp, blk);
    r.brA.setGps(blk);
    const std::vector<uint8_t> o1 = randomBytes(100, 131);
    r.send(31, kKindText, o1, {100});
    CHECK(r.pA.beginOk == 1 && r.pA.errs.empty(), "con il solo GPS BEGIN non da NO_POSITION");
  }
  std::printf("firmware/v3 ponte collegato al mezzo: %d controlli, %d falliti\n", g_checks, g_fails);
  return g_fails ? 1 : 0;
}
