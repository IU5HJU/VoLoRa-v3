// Conformita' del nucleo C++ del firmware V3 al riferimento Python: riproduce i vettori generati da tools/gen_vettori_firmware.py (ingressi e uscite del ponte, byte per byte)
// e controlla le stime di tempo. Uso: test_conformance <cartella dei vettori>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "../src/ble_bridge.h"

using namespace v3;
using namespace v3::ble;

static int g_checks = 0, g_fails = 0;
#define CHECK(c, msg)                                                       \
  do {                                                                      \
    g_checks++;                                                             \
    if (!(c)) { g_fails++; std::printf("FALLITO: %s (%s)\n", msg, #c); }  \
  } while (0)

static std::string hex(const uint8_t* d, size_t n) {
  static const char* h = "0123456789abcdef";
  std::string s;
  for (size_t i = 0; i < n; i++) { s += h[d[i] >> 4]; s += h[d[i] & 15]; }
  return s;
}
static std::vector<uint8_t> unhex(const std::string& s) {
  std::vector<uint8_t> v;
  if (s == "-") return v;
  for (size_t i = 0; i + 1 < s.size(); i += 2) v.push_back(static_cast<uint8_t>(std::stoi(s.substr(i, 2), nullptr, 16)));
  return v;
}

struct Raccolta : Sink {
  std::vector<std::string> evt_;
  std::vector<std::string> blocchi_;
  uint32_t rxObjects = 0;
  void evt(const uint8_t* d, size_t n) override { evt_.push_back(hex(d, n)); }
  void radioBlock(uint16_t obj, uint16_t blk, const uint8_t*, size_t n, bool again) override { blocchi_.push_back(std::to_string(obj) + ":" + std::to_string(blk) + ":" + std::to_string(n) + (again ? "r" : "")); }
  void rxObject(uint16_t, const uint8_t*, size_t) override { rxObjects++; }
};
static double g_dur = 1.0;
static double durFn(uint32_t, int, bool, void*) { return g_dur; }

static std::string kv(const std::string& line, const char* key) {
  std::istringstream ss(line);
  std::string tok;
  const std::string k = std::string(key) + "=";
  while (ss >> tok) if (tok.compare(0, k.size(), k) == 0) return tok.substr(k.size());
  return "";
}

// riproduce una traccia; ritorna il numero di righe d'uscita verificate
static int riproduci(const std::string& dir, const std::string& nome) {
  std::ifstream f(dir + "/" + nome + ".txt");
  if (!f) { std::printf("FALLITO: manca %s\n", nome.c_str()); g_fails++; return 0; }
  std::vector<std::string> L;
  for (std::string s; std::getline(f, s);) L.push_back(s);
  Raccolta* sink = new Raccolta;
  Bridge* br = nullptr;
  int verificate = 0, righeKo = 0;
  size_t i = 0;
  while (i < L.size()) {
    const std::string& line = L[i];
    std::istringstream ss(line);
    std::string op;
    ss >> op;
    if (op == "init") {
      delete br;
      sink->evt_.clear();
      br = new Bridge(sink, kv(line, "call").c_str(), kv(line, "chip") == "SX1262", atoi(kv(line, "rung").c_str()), static_cast<uint16_t>(atoi(kv(line, "mask").c_str())));
      br->setEstimate(durFn, nullptr);
      br->setRadioOk(kv(line, "ok") == "1");
      if (kv(line, "pos") == "1") { const uint8_t p[7] = {0, 'J', 'N', '5', '3', 'a', 'b'}; br->setPosition(p); }
      uint64_t m = 0;
      const std::string rx = kv(line, "retx");
      if (rx != "-") { std::istringstream rs(rx); std::string t; while (std::getline(rs, t, ',')) m |= 1ULL << atoi(t.c_str()); }
      br->setRetxPlan(m);
      i++;
      continue;
    }
    if (op == "out") { std::printf("FALLITO: %s: uscita senza ingresso alla riga %zu\n", nome.c_str(), i + 1); g_fails++; return verificate; }
    if (op == "dur") { std::string v; ss >> v; g_dur = std::strtod(v.c_str(), nullptr); i++; continue; }
    if (op == "stats") {
      const Stats& s = br->stats();
      CHECK(s.badFrames == static_cast<uint32_t>(atoi(kv(line, "bad").c_str())), (nome + ": bad_frames").c_str());
      CHECK(s.dropped == static_cast<uint32_t>(atoi(kv(line, "dropped").c_str())), (nome + ": dropped").c_str());
      CHECK(s.maxHeld == static_cast<uint32_t>(atoi(kv(line, "maxheld").c_str())), (nome + ": max_held").c_str());
      CHECK(s.pulls == static_cast<uint32_t>(atoi(kv(line, "pulls").c_str())), (nome + ": pulls").c_str());
      CHECK(s.repulls == static_cast<uint32_t>(atoi(kv(line, "repulls").c_str())), (nome + ": repulls").c_str());
      CHECK(s.blocksSent == static_cast<uint32_t>(atoi(kv(line, "sent").c_str())), (nome + ": blocks_sent").c_str());
      CHECK(std::fabs(s.stalledS - std::strtod(kv(line, "stalled").c_str(), nullptr)) < 1e-9, (nome + ": stalled_s").c_str());
      i++;
      continue;
    }
    sink->evt_.clear();
    if (op == "cmd" || op == "data") { std::string h; ss >> h; const std::vector<uint8_t> b = unhex(h); if (op == "cmd") br->onCommand(b.data(), b.size()); else br->onData(b.data(), b.size()); }
    else if (op == "tick") { std::string v; ss >> v; br->tick(std::strtod(v.c_str(), nullptr)); }
    else if (op == "disc") br->onDisconnect();
    else if (op == "conn") br->onConnect();
    else if (op == "rx") { unsigned obj, kind, crc, n; std::string from; ss >> obj >> kind >> crc >> from >> n; std::vector<uint8_t> d(n, 0); br->radioReceived(static_cast<uint16_t>(obj), static_cast<uint8_t>(kind), d.data(), n, from.c_str(), crc); }
    else { std::printf("FALLITO: operazione sconosciuta '%s'\n", op.c_str()); g_fails++; return verificate; }
    i++;
    std::vector<std::string> attese;
    while (i < L.size() && L[i].compare(0, 4, "out ") == 0) { attese.push_back(L[i].substr(4)); i++; }
    if (attese != sink->evt_) {
      if (righeKo < 3) {
        std::printf("FALLITO: %s riga %zu (%s): attese %zu uscite, ottenute %zu\n", nome.c_str(), i, op.c_str(), attese.size(), sink->evt_.size());
        for (size_t k = 0; k < attese.size() || k < sink->evt_.size(); k++)
          std::printf("   attesa %s | ottenuta %s\n", k < attese.size() ? attese[k].c_str() : "-", k < sink->evt_.size() ? sink->evt_[k].c_str() : "-");
      }
      righeKo++;
      g_fails++;
    }
    verificate += static_cast<int>(attese.size());
    g_checks++;
  }
  delete br;
  delete sink;
  return verificate;
}

static void stime(const std::string& dir) {
  std::ifstream f(dir + "/estimate.txt");
  CHECK(static_cast<bool>(f), "manca estimate.txt");
  std::string chip, sec, air;
  int rid, chunk;
  unsigned size;
  int n = 0, ko = 0;
  while (f >> chip >> rid >> size >> sec >> chunk >> air) {
    const bool x62 = chip == "SX1262";
    const double e = estimateSeconds(size, rid, x62), want = std::strtod(sec.c_str(), nullptr);
    const double a = frameAirtimeS(rid, 255), wa = std::strtod(air.c_str(), nullptr);
    n++;
    if (std::fabs(e - want) > 1e-9 * (1.0 + want) || chunkSize(rid, x62) != chunk || std::fabs(a - wa) > 1e-12 * (1.0 + wa)) {
      if (ko++ < 3) std::printf("   stima diversa: %s R%d %u byte: C++ %.12g, Python %.12g (blocco %d/%d)\n", chip.c_str(), rid, size, e, want, chunkSize(rid, x62), chunk);
    }
  }
  CHECK(n == 210 && ko == 0, "stime di tempo, dimensione del pezzo e tempo in aria uguali al riferimento Python (210 combinazioni)");
}

int main(int argc, char** argv) {
  const std::string dir = argc > 1 ? argv[1] : "tests/vettori";
  const char* nomi[] = {"testo", "file20k", "file64k", "retx", "interruzioni", "sparito", "annulla", "senza_posizione", "radio_fallita", "sx1262_r10", "fsk_r1", "ingressi", "rx", "fuzz"};
  stime(dir);
  for (const char* n : nomi) {
    const int before = g_fails;
    const int v = riproduci(dir, n);
    std::printf("%s: %d uscite verificate%s\n", n, v, g_fails == before ? "" : "  <-- DIVERSO");
  }
  std::printf("firmware/v3 conformita': %d controlli, %d falliti\n", g_checks, g_fails);
  return g_fails ? 1 : 0;
}
