// Il reflector V3 (reflector/v3.patch sulla v2): client finti (veri NodeLink) collegati a un ReflectorCore con una rete finta. Prove del comportamento V3; il comportamento
// v2 lo prova gia' tests/test_reflector_core.cpp della v2 (non modificato).
#include <cstring>
#include <deque>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "node_link.h"
#include "packet.h"
#include "protocol.h"
#include "reflector_core.h"
#include "testing.h"

using namespace lcr;

static uint32_t g_rng = 7;
static uint32_t rngFn() { return g_rng += 7919; }
typedef std::vector<uint8_t> Bytes;
static const uint32_t kRefId = 900;

struct Net : public IReflectorNet {
  std::map<Endpoint, std::deque<Bytes>> toEp;
  void send(Endpoint to, const uint8_t* d, size_t n) override { toEp[to].push_back(Bytes(d, d + n)); }
};

struct Client {
  uint32_t id;
  Endpoint ep;
  bool v3;
  std::unique_ptr<NodeLink> link;
  std::vector<Bytes> raw;  // pacchetti (contenuto) arrivati dal reflector
  Client(uint32_t id_, Endpoint ep_, bool v3_) : id(id_), ep(ep_), v3(v3_) {
    NodeLink::Config c;
    c.nodeId = id;
    c.peerId = kRefId;
    memset(c.key, static_cast<int>(id), sizeof(c.key));
    link.reset(new NodeLink(c, 0xC000 + id, rngFn));
    if (v3) {
      const uint8_t e[4] = {'V', '3', 1, kV3CapFrames | kV3CapDirectory};
      link->setStatusExtension(e, sizeof(e));
    }
  }
};

struct Rig {
  Net net;
  ReflectorCore core;
  std::vector<std::unique_ptr<Client>> cl;
  uint32_t t = 1000;
  Rig() : core(net, kRefId, kModeCodec2_3200, 0x5000, rngFn) {}
  Client& add(uint32_t id, bool v3) {
    cl.emplace_back(new Client(id, 5000 + id, v3));
    uint8_t k[kNodeKeyBytes];
    memset(k, static_cast<int>(id), sizeof(k));
    core.addClient(id, k, ("c" + std::to_string(id)).c_str());
    return *cl.back();
  }
  void pump() {
    for (int round = 0; round < 8; round++) {
      bool any = false;
      for (auto& c : cl) {
        auto& q = net.toEp[c->ep];
        while (!q.empty()) {
          any = true;
          const Bytes d = q.front();
          q.pop_front();
          NodeLink::Rx& rx = c->link->onDatagram(d.data(), d.size(), t);
          for (size_t i = 0; i < rx.nReplies; i++) core.onDatagram(c->ep, rx.replies[i].data, rx.replies[i].len, t);
          if (rx.kind == NodeLink::Kind::Packet) c->raw.push_back(Bytes(rx.packet, rx.packet + rx.packetLen));
        }
      }
      if (!any) break;
    }
  }
  void step() {
    uint8_t out[kNodeMaxDatagram];
    for (auto& c : cl) {
      const size_t m = c->link->maintenance(t, out, sizeof(out));
      if (m) core.onDatagram(c->ep, out, m, t);
    }
    core.tick(t);
    pump();
  }
  void run(uint32_t ms, uint32_t stepMs = 100) {
    const uint32_t end = t + ms;
    while (t < end) {
      step();
      t += stepMs;
    }
  }
  void send(Client& c, const Bytes& wire) {
    uint8_t out[kNodeMaxDatagram];
    const size_t k = c.link->makePacket(wire.data(), wire.size(), out, sizeof(out));
    core.onDatagram(c.ep, out, k, t);
    pump();
  }
  bool allUp() {
    for (auto& c : cl)
      if (!c->link->linkUp(t)) return false;
    return true;
  }
};

static const uint8_t kA[6] = {1, 2, 3, 4, 5, 6}, kB[6] = {9, 8, 7, 6, 5, 4}, kSrc[6] = {11, 12, 13, 14, 15, 16};

static Bytes annuncio(std::initializer_list<std::pair<const uint8_t*, int>> v) {
  Bytes f = {kV3FrameByte0, kV3SubAnnuncio, static_cast<uint8_t>(v.size())};
  for (auto& e : v) {
    f.insert(f.end(), e.first, e.first + 6);
    f.push_back(static_cast<uint8_t>(e.second >> 8));
    f.push_back(static_cast<uint8_t>(e.second));
  }
  return f;
}
static Bytes inoltro(const uint8_t* dest, uint8_t ttl, const Bytes& inner) {
  Bytes f = {kV3FrameByte0, kV3SubInoltro};
  f.insert(f.end(), dest, dest + 6);
  f.insert(f.end(), kSrc, kSrc + 6);
  f.push_back(ttl);
  f.insert(f.end(), inner.begin(), inner.end());
  return f;
}
static bool isEsito(const Bytes& b, const uint8_t* dest, uint8_t code) {
  return b.size() == 9 && b[0] == kV3FrameByte0 && b[1] == kV3SubEsito && memcmp(&b[2], dest, 6) == 0 && b[8] == code;
}

static void testDeclaration() {
  Rig r;
  Client& a = r.add(2, false);
  Client& b = r.add(3, true);
  r.run(8000);
  CHECK(r.allUp());
  bool v3a = true, v3b = false;
  for (const auto& i : r.core.clients(r.t)) {
    if (i.id == a.id) v3a = i.v3;
    if (i.id == b.id) v3b = i.v3;
  }
  CHECK(!v3a);  // un client v2 non dichiara nulla
  CHECK(v3b);   // il client V3 si' (dalla dichiarazione nei HELLO e KEEPALIVE)
  CHECK(b.link->peerExtensionLen() >= 4 && b.link->peerExtension()[0] == 'V' && b.link->peerExtension()[1] == '3');  // e il reflector risponde con la sua
  CHECK(a.link->peerExtensionLen() == 0);  // al client v2 non manda niente di piu' di prima
}

static void testV2ClientCannotInject() {
  Rig r;
  Client& a = r.add(2, false);
  Client& b = r.add(3, true);
  r.run(8000);
  r.send(a, annuncio({{kA, 5}}));
  r.send(a, inoltro(kA, 3, Bytes{0x3E, 1, 0, 0, 0, 0}));
  CHECK(r.core.stats().v3Refused == 2);
  CHECK(b.raw.empty() && a.raw.empty());
  CHECK(r.core.stats().badPacket == 0);  // non e' un pacchetto v2 rovinato: e' un frame V3 non ammesso
}

static void testDirectoryAndRouting() {
  Rig r;
  Client& v2 = r.add(2, false);
  Client& g1 = r.add(4, true);
  Client& g2 = r.add(5, true);
  r.run(8000);
  r.send(g1, annuncio({{kA, 10}, {kB, 20}}));
  CHECK(r.core.stats().v3Announces == 1);
  const Bytes inner = {0x3E, 1, 2, 3};
  r.send(g2, inoltro(kA, 3, inner));
  CHECK(r.core.stats().v3Forwarded == 1);
  bool got = false, esito = false;
  for (const Bytes& p : g1.raw) {
    if (p.size() == 2 + 13 + inner.size() && p[0] == kV3FrameByte0 && p[1] == kV3SubInoltro && memcmp(&p[2], kA, 6) == 0 && memcmp(&p[8], kSrc, 6) == 0 && p[14] == 2 &&
        memcmp(&p[15], inner.data(), inner.size()) == 0)
      got = true;
  }
  for (const Bytes& p : g2.raw) esito = esito || isEsito(p, kA, kV3EsitoConsegnato);
  CHECK(got);     // la busta arriva al gateway che sente la destinazione, con il ttl ridotto di uno
  CHECK(esito);   // il mittente sa che e' stata consegnata
  CHECK(v2.raw.empty());  // il client v2 non vede mai niente del V3
  g2.raw.clear();
  const uint8_t nobody[6] = {0, 0, 0, 0, 0, 1};
  r.send(g2, inoltro(nobody, 3, inner));
  bool nf = false;
  for (const Bytes& p : g2.raw) nf = nf || isEsito(p, nobody, kV3EsitoNonTrovato);
  CHECK(nf);
  g2.raw.clear();
  r.send(g2, inoltro(kA, 0, inner));
  bool rif = false;
  for (const Bytes& p : g2.raw) rif = rif || isEsito(p, kA, kV3EsitoRifiutato);
  CHECK(rif);
  const uint32_t fw = r.core.stats().v3Forwarded;
  r.send(g1, inoltro(kA, 3, inner));  // mai a se stesso
  CHECK(r.core.stats().v3Forwarded == fw);
}

static void testDirectoryExpires() {
  Rig r;
  r.add(2, false);
  Client& g1 = r.add(4, true);
  Client& g2 = r.add(5, true);
  r.run(8000);
  r.send(g1, annuncio({{kA, 10}}));
  r.run(kV3DirectoryLifeMs + 20000, 1000);
  g2.raw.clear();
  r.send(g2, inoltro(kA, 3, Bytes{0x3E, 1}));
  bool nf = false;
  for (const Bytes& p : g2.raw) nf = nf || isEsito(p, kA, kV3EsitoNonTrovato);
  CHECK(r.allUp());
  CHECK(nf);  // la rubrica scade dopo 10 minuti senza un nuovo annuncio
}

static void testAnnouncementWithOldAge() {
  Rig r;
  Client& g1 = r.add(4, true);
  Client& g2 = r.add(5, true);
  r.run(8000);
  r.send(g1, annuncio({{kA, 65535}}));  // eta' di 18 ore (piu' del tempo trascorso): il calcolo con segno non deve rompersi
  r.send(g2, inoltro(kA, 3, Bytes{0x3E, 1}));
  CHECK(r.core.stats().v3Forwarded == 0);
  CHECK(r.core.stats().v3Announces == 1);
}

static void testKeyChangeResetsV3() {
  Rig r;
  Client& g1 = r.add(4, true);
  r.add(5, true);
  r.run(8000);
  bool v3 = false;
  for (const auto& i : r.core.clients(r.t)) v3 = v3 || (i.id == g1.id && i.v3);
  CHECK(v3);
  uint8_t k[kNodeKeyBytes];
  memset(k, 99, sizeof(k));
  CHECK(r.core.setClientKey(g1.id, k));
  for (const auto& i : r.core.clients(r.t)) CHECK(!(i.id == g1.id && i.v3));
}

static void testMalformedFrames() {
  Rig r;
  Client& g1 = r.add(4, true);
  r.add(5, true);
  r.run(8000);
  r.send(g1, Bytes{kV3FrameByte0});                                  // troppo corto
  r.send(g1, Bytes{kV3FrameByte0, kV3SubAnnuncio, 3, 1, 2, 3});      // dichiara 3 voci e non le ha
  r.send(g1, Bytes{kV3FrameByte0, kV3SubInoltro, 1, 2, 3});          // busta troncata
  r.send(g1, Bytes{kV3FrameByte0, 200, 0, 0});                       // sottotipo sconosciuto
  r.send(g1, Bytes{0x3D, 0, 0, 0, 0, 0, 0});                         // un beacon: locale, non va in rete
  CHECK(r.core.stats().v3Refused == 5);
  CHECK(r.core.stats().v3Announces == 0 && r.core.stats().v3Forwarded == 0);
}

int main() {
  testDeclaration();
  testV2ClientCannotInject();
  testDirectoryAndRouting();
  testDirectoryExpires();
  testAnnouncementWithOldAge();
  testKeyChangeResetsV3();
  testMalformedFrames();
  TEST_MAIN_END();
}
