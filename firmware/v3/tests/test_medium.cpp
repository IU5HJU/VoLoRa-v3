// Prova del MEZZO (src/medium.h) sul PC: due stazioni, un canale con perdite (lo stesso modello del simulatore Python: tools/sim_immagini.py, Channel) e un orologio a eventi.
// Il mezzo C++ e' diverso da quello del Python (qui i tempi di risposta sono veri: commutazione, silenzi, tempi limite): si controlla che l'oggetto arrivi INTERO e identico,
// e che esiti e tempi siano dello stesso ordine del riferimento Python (tools/gen_riferimento_medio.py), scenario per scenario su 8 semi.
// Uso: test_medium <file del riferimento Python>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#include "../src/medium.h"

using namespace v3;
using namespace v3::img;

struct MemStore : Store {
  std::vector<std::vector<uint8_t>> p;
  void reset(uint16_t n) override { p.assign(n, std::vector<uint8_t>()); }
  void put(uint16_t i, const uint8_t* d, size_t n) override { if (i < p.size()) p[i].assign(d, d + n); }
  size_t get(uint16_t i, uint8_t* out) override { if (i >= p.size()) return 0; memcpy(out, p[i].data(), p[i].size()); return p[i].size(); }
  std::vector<uint8_t> joined(size_t n) const { std::vector<uint8_t> v; for (const auto& q : p) { v.insert(v.end(), q.begin(), q.end()); if (v.size() >= n) break; } v.resize(std::min(n, v.size())); return v; }
};

struct ChannelParams { double prx0, extra, when, span; std::string scen; };

struct World;
struct SimRadio : Radio {
  World* w = nullptr;
  int id = 0, rung = kRendezvous;
  double txStart = -1, txEnd = -1;
  unsigned used = 0;
  void setRung(int r) override { rung = r; used |= 1u << r; }
  bool transmit(const uint8_t* f, size_t n) override;
  double random() override;
};

struct World {
  double t = 0;
  std::mt19937_64 rng;
  ChannelParams ch;
  SimRadio radio[2];
  Station* st[2] = {nullptr, nullptr};
  struct Ev { int kind; int to; std::vector<uint8_t> f; int rungAtTx; double t0; };   // 0 fine trasmissione, 1 consegna
  std::multimap<double, Ev> q;
  int framesLost = 0, framesHeard = 0;
  explicit World(uint64_t seed, const ChannelParams& c) : rng(seed), ch(c) { for (int i = 0; i < 2; i++) { radio[i].w = this; radio[i].id = i; } }
  double u01() { return std::uniform_real_distribution<double>(0.0, 1.0)(rng); }
  double lossExtra(double tt) const {
    if (ch.scen == "degrada") return ch.extra * std::min(1.0, tt / ch.span);
    if (ch.scen == "gradino") return tt >= ch.when ? ch.extra : 0.0;
    if (ch.scen == "oscilla") return ch.extra / 2 * (1 + std::sin(2 * M_PI * tt / ch.span));
    return 0.0;
  }
  void deliver(const Ev& e) {
    SimRadio& rx = radio[e.to];
    SimRadio& tx = radio[1 - e.to];
    const bool overlap = rx.txEnd > e.t0 && rx.txStart < t;          // l'altra stazione stava trasmettendo: non puo' sentire
    if (rx.rung != e.rungAtTx || overlap) { framesLost++; return; }
    const double prx = ch.prx0 - lossExtra(t) + std::normal_distribution<double>(0.0, 1.5)(rng);
    const double x = prx - sensitivityDbm(e.rungAtTx);
    double pOk = 1.0 / (1.0 + std::exp(-x / 0.8));
    pOk = std::pow(pOk, std::max<double>(static_cast<double>(e.f.size()), 1.0) / 64.0);
    (void)tx;
    if (u01() < pOk) { framesHeard++; st[e.to]->onRx(e.f.data(), e.f.size(), prx, prx - noiseFloorDbm(e.rungAtTx), t); }
    else framesLost++;
  }
  void run(double maxT, bool (*stop)(World&)) {
    long it = 0, same = 0;
    double last = -1;
    while (t < maxT && !stop(*this)) {
      if (++it > 20000000L) { std::printf("ABORT: troppe iterazioni a t=%.3f\n", t); break; }
      if (t == last) { if (++same > 2000) { std::printf("ABORT: il tempo non avanza a t=%.6f (coda %zu, A wake %.6f, B wake %.6f, rungA %d rungB %d)\n", t, q.size(), st[0]->nextWake(t), st[1]->nextWake(t), st[0]->link().rung, st[1]->link().rung); break; } } else { same = 0; last = t; }
      double nt = t + 0.1;
      for (int i = 0; i < 2; i++) nt = std::min(nt, st[i]->nextWake(t));
      if (!q.empty()) nt = std::min(nt, q.begin()->first);
      if (nt < t) nt = t;
      t = nt;
      while (!q.empty() && q.begin()->first <= t) {
        Ev e = q.begin()->second;
        q.erase(q.begin());
        if (e.kind == 0) st[e.to]->onTxDone(t); else deliver(e);
      }
      for (int i = 0; i < 2; i++) st[i]->poll(t);
    }
  }
};
bool SimRadio::transmit(const uint8_t* f, size_t n) {
  const double air = n ? frameAirtimeS(rung, static_cast<int>(n)) : 0.0;
  txStart = w->t; txEnd = w->t + air;
  w->q.insert({w->t + air, World::Ev{0, id, {}, rung, w->t}});
  w->q.insert({w->t + air, World::Ev{1, 1 - id, std::vector<uint8_t>(f, f + n), rung, w->t}});
  return true;
}
double SimRadio::random() { return w->u01(); }

static int g_fails = 0, g_checks = 0;
#define CHECK(c, ...) do { g_checks++; if (!(c)) { g_fails++; std::printf("FALLITO: "); std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)

struct Result { bool delivered = false, unconfirmed = false; double time = 0; int layers = 0; uint32_t bytes = 0; bool intact = true; FailKind fail = FAIL_NONE; int rungChangesA = 0; };

static bool senderDone(World& w) { return w.st[0]->sendFinished(); }

static unsigned g_usedRungs = 0;
static Result runOne(const std::string& chipA, const std::string& chipB, const ChannelParams& cp, int size, bool tcxo, double budget, uint64_t seed, const std::vector<double>& fractions, uint16_t unsupported = 0) {
  World w(seed, cp);
  MemStore storeA, storeB;
  const uint8_t callA[] = {'I', 'U', '5', 'H', 'J', 'U'}, callB[] = {'I', 'K', '5', 'X', 'Y', 'Z'};
  Station a(callA, 6, chipA == "SX1262", tcxo, &w.radio[0], &storeA, kWindowFrames, true, unsupported), b(callB, 6, chipB == "SX1262", tcxo, &w.radio[1], &storeB, kWindowFrames, true, unsupported);
  w.st[0] = &a; w.st[1] = &b;
  std::mt19937_64 orng(seed + 7);
  std::vector<uint8_t> obj(size);
  for (auto& x : obj) x = static_cast<uint8_t>(orng() & 255);
  const int np = (size + kPiece - 1) / kPiece;
  std::vector<uint16_t> ends;
  for (double f : fractions) ends.push_back(static_cast<uint16_t>(std::max(1, std::min(np, static_cast<int>(std::ceil(np * f))))));
  ends.back() = static_cast<uint16_t>(np);
  const uint16_t sess = static_cast<uint16_t>(1 + (seed * 7919) % 65000);
  a.startSend(obj.data(), obj.size(), ends.data(), static_cast<int>(ends.size()), budget, sess);
  w.run(6 * 3600.0, senderDone);
  g_usedRungs |= w.radio[0].used | w.radio[1].used;
  Result r;
  r.time = w.t;
  r.fail = a.sendFailure();
  r.delivered = a.sendOk() || (a.sendFinished() && a.sendFailure() == FAIL_DONE && b.receiver().hasDone());
  r.unconfirmed = a.sendFinished() && a.sendFailure() == FAIL_DONE && b.receiver().hasDone();
  r.layers = a.layersDelivered(); r.bytes = a.bytesDelivered();
  if (b.receiver().hasDone() && b.receiver().doneOk()) {
    // i byte consegnati sono il prefisso dell'oggetto
    const size_t n = a.sendOk() ? a.bytesDelivered() : 0;
    if (n) r.intact = storeB.joined(n) == std::vector<uint8_t>(obj.begin(), obj.begin() + n);
  } else if (a.sendOk()) r.intact = false;
  return r;
}

int main(int argc, char** argv) {
  if (argc < 2) { std::printf("uso: test_medium <riferimento_medio.txt>\n"); return 1; }
  std::ifstream f(argv[1]);
  std::string line;
  while (std::getline(f, line)) {
    std::istringstream ss(line);
    std::string name, ca, cb, scen;
    double prx, extra, when, span, budget, pyTime;
    int size, tcxo, nSeeds, pyOk;
    ss >> name >> ca >> cb >> prx >> scen >> extra >> when >> span >> size >> tcxo >> budget >> nSeeds >> pyOk >> pyTime;
    ChannelParams cp{prx, extra, when, span, scen};
    int ok = 0, intact = 0, confirmed = 0, partial = 0;
    std::vector<double> times;
    for (int seed = 1; seed <= nSeeds; seed++) {
      const Result r = runOne(ca, cb, cp, size, tcxo != 0, budget, seed, {1.0 / 3, 2.0 / 3, 1.0});
      if (r.delivered) { ok++; times.push_back(r.time); if (r.intact) intact++; if (r.layers > 0 && r.layers < 3) partial++; }
      if (r.fail == FAIL_NONE && r.delivered) confirmed++;
    }
    std::sort(times.begin(), times.end());
    const double med = times.empty() ? 0.0 : times[times.size() / 2];
    std::printf("%-8s %s-%s %.0f dBm %-9s %5d byte: consegnati %d/%d (Python %d/%d), tempo mediano %.0f s (Python %.0f s), oggetto identico %d/%d, confermati dal mittente %d\n", name.c_str(), ca.c_str(), cb.c_str(), prx,
                scen.c_str(), size, ok, nSeeds, pyOk, nSeeds, med, pyTime, intact, ok, confirmed);
    CHECK(std::abs(ok - pyOk) <= 2, "%s: consegnati %d contro %d del Python (scarto oltre 2 su %d)", name.c_str(), ok, pyOk, nSeeds);
    CHECK(intact == ok, "%s: un oggetto consegnato non e' identico all'originale", name.c_str());
    if (pyOk >= 6 && ok >= 6 && pyTime > 0) CHECK(med > 0.4 * pyTime && med < 2.5 * pyTime, "%s: tempo mediano %.0f s fuori da 0,4-2,5 volte quello del Python (%.0f s)", name.c_str(), med, pyTime);
    if (name == "vicino" || name == "medio" || name == "misto") CHECK(ok == nSeeds, "%s: con un buon collegamento devono arrivare tutti (%d/%d)", name.c_str(), ok, nSeeds);
    if (name == "perso") CHECK(ok == 0, "%s: senza collegamento non deve arrivare niente", name.c_str());
    if (name == "budget") CHECK(partial >= 1, "%s: con un budget breve almeno una consegna si ferma a un livello intermedio", name.c_str());
  }
  // un gradino che la radio non sa fare (R3 sull'SX1278) non si annuncia e non si usa, anche con un collegamento fortissimo dove la negoziazione lo sceglierebbe
  {
    g_usedRungs = 0;
    int okR3 = 0;
    for (int seed = 1; seed <= 4; seed++) { const Result r = runOne("SX1278", "SX1278", ChannelParams{-108.0, 0, 0, 1, "costante"}, 20000, false, 600.0, seed, {1.0 / 3, 2.0 / 3, 1.0}, static_cast<uint16_t>(1u << 3)); if (r.delivered && r.intact) okR3++; }
    const unsigned with3 = g_usedRungs;
    g_usedRungs = 0;
    for (int seed = 1; seed <= 4; seed++) runOne("SX1278", "SX1278", ChannelParams{-108.0, 0, 0, 1, "costante"}, 20000, false, 600.0, seed, {1.0 / 3, 2.0 / 3, 1.0}, 0);
    const unsigned all = g_usedRungs;
    std::printf("R3 non supportato: consegnati %d/4, gradini usati 0x%04X (con R3 permesso: 0x%04X)\n", okR3, with3, all);
    CHECK(okR3 == 4, "senza R3 il trasferimento arriva comunque (%d/4)", okR3);
    CHECK(!(with3 & (1u << 3)) && (all & (1u << 3)), "senza R3 non lo si usa mai; con R3 permesso la negoziazione lo sceglie (0x%04X, 0x%04X)", with3, all);
  }
  std::printf("firmware/v3 mezzo: %d controlli, %d falliti\n", g_checks, g_fails);
  return g_fails ? 1 : 0;
}
