// Mondo di prova condiviso (test_medium, test_live): due stazioni, un canale con perdite (stesso modello del simulatore Python, tools/sim_immagini.py, Channel)
// e un orologio a eventi. Il canale e le funzioni del telefono si programmano con schedule()/tickHook/wakeHook.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <functional>
#include <map>
#include <random>
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
  struct Ev { int kind; int to; std::vector<uint8_t> f; int rungAtTx; double t0; std::function<void()> fn; };   // 0 fine trasmissione, 1 consegna, 2 funzione (telefono)
  std::multimap<double, Ev> q;
  int framesLost = 0, framesHeard = 0;
  std::function<void(double)> tickHook;                 // dopo ogni giro di poll (ponte, telefono)
  std::function<double(double)> wakeHook;               // entro quando serve un altro giro
  void schedule(double delay, std::function<void()> fn) { q.insert({t + delay, Ev{2, 0, {}, 0, t, std::move(fn)}}); }
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
      if (wakeHook) nt = std::min(nt, wakeHook(t));
      if (!q.empty()) nt = std::min(nt, q.begin()->first);
      if (nt < t) nt = t;
      t = nt;
      while (!q.empty() && q.begin()->first <= t) {
        Ev e = q.begin()->second;
        q.erase(q.begin());
        if (e.kind == 0) st[e.to]->onTxDone(t); else if (e.kind == 1) deliver(e); else e.fn();
      }
      for (int i = 0; i < 2; i++) st[i]->poll(t);
      if (tickHook) tickHook(t);
    }
  }
};
bool SimRadio::transmit(const uint8_t* f, size_t n) {
  const double air = n ? frameAirtimeS(rung, static_cast<int>(n)) : 0.0;
  txStart = w->t; txEnd = w->t + air;
  w->q.insert({w->t + air, World::Ev{0, id, {}, rung, w->t, nullptr}});
  w->q.insert({w->t + air, World::Ev{1, 1 - id, std::vector<uint8_t>(f, f + n), rung, w->t, nullptr}});
  return true;
}
double SimRadio::random() { return w->u01(); }

