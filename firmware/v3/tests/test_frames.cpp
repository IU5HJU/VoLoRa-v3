// Conformita' dei frame del protocollo immagini (src/frames.h) al riferimento Python: codificatori e decodificatore contro i vettori di tools/gen_vettori_firmware.py.
// Uso: test_frames <cartella dei vettori>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "../src/frames.h"

using namespace v3::img;

static int g_checks = 0, g_fails = 0;

static std::string hex(const uint8_t* d, size_t n) {
  static const char* h = "0123456789abcdef";
  std::string s;
  for (size_t i = 0; i < n; i++) { s += h[d[i] >> 4]; s += h[d[i] & 15]; }
  return s;
}
static std::string hexOrDot(const uint8_t* d, size_t n) { return n ? hex(d, n) : "."; }
static std::vector<uint8_t> unhex(const std::string& s) {
  std::vector<uint8_t> v;
  if (s == "-" || s == ".") return v;
  for (size_t i = 0; i + 1 < s.size(); i += 2) v.push_back(static_cast<uint8_t>(std::stoi(s.substr(i, 2), nullptr, 16)));
  return v;
}

// Lo stesso riassunto che stampa tools/gen_vettori_firmware.py (resumen)
static std::string resumen(const uint8_t* b, size_t n) {
  Msg m;
  if (!decode(b, n, &m)) return "NONE";
  std::ostringstream o;
  o << static_cast<int>(m.type) << " " << m.sess << " " << static_cast<int>(m.flags) << " " << m.len;
  auto pos = [&]() { return m.hasPos ? hex(m.pos, 7) : std::string("-"); };
  auto opt = [&]() { return m.hasOpts ? hexOrDot(m.opts, m.optsLen) : std::string("-"); };
  switch (m.type) {
    case HELLO:
      o << " " << hexOrDot(m.call, m.callLen) << " " << static_cast<int>(m.chip) << " " << m.rungMask << " " << static_cast<int>(m.maxFrame) << " " << m.memKb << " " << (m.reply ? 1 : 0) << " ";
      if (m.hasMeasure) o << static_cast<int>(m.rssi) << " " << static_cast<int>(m.snr); else o << "- -";
      o << " " << pos() << " " << opt();
      break;
    case PROBE: o << " " << static_cast<int>(m.rung) << " " << static_cast<int>(m.idx) << " " << static_cast<int>(m.count); break;
    case PROBE_REPORT: o << " " << static_cast<int>(m.rung) << " " << static_cast<int>(m.expected) << " " << static_cast<int>(m.received) << " " << static_cast<int>(m.rssi) << " " << static_cast<int>(m.snr); break;
    case MODE_SET: o << " " << static_cast<int>(m.rung) << " " << static_cast<int>(m.k) << " " << static_cast<int>(m.repeat); break;
    case MODE_ACK: o << " " << static_cast<int>(m.rung); break;
    case OFFER: {
      o << " " << hexOrDot(m.call, m.callLen) << " " << static_cast<int>(m.objType) << " " << m.size << " " << static_cast<int>(m.piece) << " " << m.nPieces << " " << m.w << " " << m.h << " ";
      if (m.nl == 0) o << "-"; else for (int i = 0; i < m.nl; i++) o << (i ? "," : "") << m.layerEnds[i];
      o << " " << m.crc << " " << pos() << " " << opt();
      break;
    }
    case ACCEPT: o << " " << static_cast<int>(m.layers) << " " << static_cast<int>(m.window) << " " << static_cast<int>(m.k); break;
    case DATA: o << " " << m.offset << " " << ((m.flags & F_RELAYED) ? 1 : 0) << " " << (m.flags >> kHopShift) << " " << hexOrDot(m.payload, m.payloadLen); break;
    case STATUS: o << " " << m.base << " " << m.bitmap << " " << static_cast<int>(m.rssi) << " " << static_cast<int>(m.snr) << " " << static_cast<int>(m.lossPct) << " " << static_cast<int>(m.layersDone); break;
    case DONE: o << " " << hexOrDot(m.call, m.callLen) << " " << static_cast<int>(m.layers) << " " << m.nbytes << " " << m.crc; break;
    case ABORT: o << " " << static_cast<int>(m.reason); break;
    default: break;
  }
  return o.str();
}

static const uint8_t* opt(const std::string& s, std::vector<uint8_t>* store) { if (s == "-") return nullptr; *store = unhex(s); return store->data(); }

static void codifica(const std::string& dir) {
  std::ifstream f(dir + "/frames_enc.txt");
  if (!f) { std::printf("FALLITO: manca frames_enc.txt\n"); g_fails++; return; }
  int n = 0, ko = 0;
  for (std::string line; std::getline(f, line);) {
    std::istringstream ss(line);
    std::vector<std::string> t;
    for (std::string w; ss >> w;) t.push_back(w);
    if (t.size() < 2) continue;
    const std::string want = t.back();
    uint8_t out[300];
    size_t len = 0;
    const std::string& ty = t[0];
    auto I = [&](size_t i) { return std::strtoull(t[i].c_str(), nullptr, 10); };
    auto S = [&](size_t i) { return static_cast<int>(std::strtol(t[i].c_str(), nullptr, 10)); };
    if (ty == "HELLO") {
      const std::vector<uint8_t> call = unhex(t[2]);
      int rssi = 0, snr = 0;
      const bool meas = t[8] != "-";
      if (meas) { rssi = S(8); snr = S(9); }
      std::vector<uint8_t> ps, os;
      const uint8_t* p = opt(t[10], &ps);
      const uint8_t* o = opt(t[11], &os);
      len = encHello(out, sizeof(out), static_cast<uint16_t>(I(1)), call.data(), call.size(), I(3) != 0, static_cast<uint16_t>(I(4)), static_cast<uint8_t>(I(5)), static_cast<uint16_t>(I(6)), I(7) != 0,
                     meas ? &rssi : nullptr, meas ? &snr : nullptr, p, o, os.size());
    } else if (ty == "PROBE") len = encProbe(out, sizeof(out), static_cast<uint16_t>(I(1)), static_cast<uint8_t>(I(2)), static_cast<uint8_t>(I(3)), static_cast<uint8_t>(I(4)), I(5));
    else if (ty == "PROBE_REPORT") len = encProbeReport(out, sizeof(out), static_cast<uint16_t>(I(1)), static_cast<uint8_t>(I(2)), static_cast<uint8_t>(I(3)), static_cast<uint8_t>(I(4)), S(5), S(6));
    else if (ty == "MODE_SET") len = encModeSet(out, sizeof(out), static_cast<uint16_t>(I(1)), static_cast<uint8_t>(I(2)), static_cast<uint8_t>(I(3)), static_cast<uint8_t>(I(4)));
    else if (ty == "MODE_ACK") len = encModeAck(out, sizeof(out), static_cast<uint16_t>(I(1)), static_cast<uint8_t>(I(2)));
    else if (ty == "ACCEPT") len = encAccept(out, sizeof(out), static_cast<uint16_t>(I(1)), static_cast<uint8_t>(I(2)), static_cast<uint8_t>(I(3)), static_cast<uint8_t>(I(4)));
    else if (ty == "ABORT") len = encAbort(out, sizeof(out), static_cast<uint16_t>(I(1)), static_cast<uint8_t>(I(2)));
    else if (ty == "DONE") { const std::vector<uint8_t> call = unhex(t[2]); len = encDone(out, sizeof(out), static_cast<uint16_t>(I(1)), call.data(), call.size(), static_cast<uint8_t>(I(3)), static_cast<uint32_t>(I(4)), static_cast<uint32_t>(I(5))); }
    else if (ty == "OFFER") {
      const std::vector<uint8_t> call = unhex(t[2]);
      uint16_t ends[kMaxLayers];
      size_t nl = 0;
      if (t[9] != "-") { std::istringstream es(t[9]); std::string e; while (std::getline(es, e, ',')) ends[nl++] = static_cast<uint16_t>(std::strtoul(e.c_str(), nullptr, 10)); }
      std::vector<uint8_t> ps, os;
      const uint8_t* p = opt(t[11], &ps);
      const uint8_t* o = opt(t[12], &os);
      len = encOffer(out, sizeof(out), static_cast<uint16_t>(I(1)), call.data(), call.size(), static_cast<uint8_t>(I(3)), static_cast<uint32_t>(I(4)), static_cast<uint8_t>(I(5)), static_cast<uint16_t>(I(6)),
                     static_cast<uint16_t>(I(7)), static_cast<uint16_t>(I(8)), ends, nl, static_cast<uint32_t>(I(10)), p, o, os.size());
    } else if (ty == "DATA") { const std::vector<uint8_t> pl = unhex(t[4]); len = encData(out, sizeof(out), static_cast<uint16_t>(I(1)), static_cast<uint16_t>(I(2)), pl.data(), pl.size(), static_cast<uint8_t>(I(3))); }
    else if (ty == "STATUS") len = encStatus(out, sizeof(out), static_cast<uint16_t>(I(1)), static_cast<uint16_t>(I(2)), I(3), S(4), S(5), S(6), static_cast<uint8_t>(I(7)), static_cast<uint8_t>(I(8)));
    else { std::printf("FALLITO: tipo sconosciuto %s\n", ty.c_str()); g_fails++; return; }
    n++;
    g_checks++;
    if (hex(out, len) != want) { g_fails++; if (ko++ < 3) std::printf("FALLITO: %s: atteso %s, ottenuto %s\n", ty.c_str(), want.c_str(), hex(out, len).c_str()); }
  }
  std::printf("codificatori: %d frame, %d diversi\n", n, ko);
}

static void decodifica(const std::string& dir) {
  std::ifstream f(dir + "/frames_dec.txt");
  if (!f) { std::printf("FALLITO: manca frames_dec.txt\n"); g_fails++; return; }
  int n = 0, ko = 0, nonePy = 0;
  for (std::string line; std::getline(f, line);) {
    const size_t sp = line.find(' ');
    const std::string h = line.substr(0, sp), want = line.substr(sp + 1);
    const std::vector<uint8_t> b = unhex(h);
    const std::string got = resumen(b.data(), b.size());
    n++;
    g_checks++;
    if (want == "NONE") nonePy++;
    if (got != want) { g_fails++; if (ko++ < 5) std::printf("FALLITO: decodifica di %s\n   atteso  %s\n   ottenuto %s\n", h.c_str(), want.c_str(), got.c_str()); }
  }
  std::printf("decodificatore: %d frame (di cui %d non validi), %d diversi\n", n, nonePy, ko);
}

int main(int argc, char** argv) {
  const std::string dir = argc > 1 ? argv[1] : "tests/vettori";
  codifica(dir);
  decodifica(dir);
  std::printf("firmware/v3 frame: %d controlli, %d falliti\n", g_checks, g_fails);
  return g_fails ? 1 : 0;
}
