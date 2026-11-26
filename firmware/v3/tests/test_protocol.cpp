// Conformita' del protocollo immagini in C++ (src/img_proto.h: collegamento, ricevitore, mittente) al riferimento Python (tools/img_proto.py): rifa' ogni scenario del simulatore
// da solo, stazione per stazione, con le tracce registrate da tools/gen_tracce_protocollo.py (ingressi e uscite esatti). Uso: test_protocol <cartella delle tracce>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "../src/img_proto.h"

using namespace v3;
using namespace v3::img;

static int g_checks = 0, g_fails = 0;
static std::string g_ctx;
static int g_printed = 0;
static void fail(const std::string& what, const std::string& want, const std::string& got) {
  g_fails++;
  if (g_printed++ < 12) std::printf("FALLITO [%s]: %s\n   atteso  %s\n   ottenuto %s\n", g_ctx.c_str(), what.c_str(), want.substr(0, 220).c_str(), got.substr(0, 220).c_str());
}
#define EXPECT(cond, what, want, got) do { g_checks++; if (!(cond)) fail(what, want, got); } while (0)

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
static std::vector<std::string> split(const std::string& s, char c) { std::vector<std::string> v; std::string t; std::istringstream ss(s); while (std::getline(ss, t, c)) v.push_back(t); return v; }
static std::vector<std::string> words(const std::string& s) { std::vector<std::string> v; std::istringstream ss(s); for (std::string w; ss >> w;) v.push_back(w); return v; }
static double D(const std::string& s) { return std::strtod(s.c_str(), nullptr); }
static std::vector<std::string> lines(const std::string& path) { std::ifstream f(path); std::vector<std::string> L; for (std::string s; std::getline(f, s);) L.push_back(s); return L; }
// divide una riga nelle sezioni separate da " | "
static std::vector<std::string> sections(const std::string& s) {
  std::vector<std::string> v;
  size_t at = 0;
  for (;;) { const size_t p = s.find(" | ", at); if (p == std::string::npos) { v.push_back(s.substr(at)); break; } v.push_back(s.substr(at, p - at)); at = p + 3; }
  return v;
}

// ---------------------------------------------------------------------------------------------------------------------------------- collegamento
static void linkState(const Link& l, const std::string& state) {
  std::map<std::string, std::string> kv;
  for (const std::string& w : words(state)) { const size_t e = w.find('='); kv[w.substr(0, e)] = w.substr(e + 1); }
  EXPECT(l.rung == atoi(kv["rung"].c_str()), "gradino", kv["rung"], std::to_string(l.rung));
  EXPECT(l.lost == (kv["lost"] != "-") && (!l.lost || l.lostSince == D(kv["lost"])), "in ricerca", kv["lost"], l.lost ? std::to_string(l.lostSince) : "-");
  EXPECT(l.hold == (kv["hold"] == "1"), "tenuta", kv["hold"], std::to_string(l.hold));
  EXPECT(l.holdUntil == D(kv["holdu"]), "tenuta fino a", kv["holdu"], std::to_string(l.holdUntil));
  EXPECT(l.lastHeard == D(kv["lh"]), "ultimo ascolto", kv["lh"], std::to_string(l.lastHeard));
  EXPECT(l.hadLink == (kv["had"] == "1"), "gia' collegato", kv["had"], std::to_string(l.hadLink));
}
static void linkEvents(const LinkEvent* ev, int n, const std::string& want) {
  std::vector<std::string> W;
  if (want != "-") W = split(want, ';');
  bool ok = static_cast<int>(W.size()) == n;
  for (int i = 0; ok && i < n; i++) {
    const std::vector<std::string> p = split(W[i], ':');
    if (ev[i].fallback) ok = p[0] == "F" && D(p[1]) == ev[i].silence && atoi(p[2].c_str()) == ev[i].a;
    else ok = p[0] == "R" && atoi(p[1].c_str()) == ev[i].a && atoi(p[2].c_str()) == ev[i].b;
  }
  EXPECT(ok, "eventi del collegamento", want, std::to_string(n) + " eventi");
}
static int linkReplay(const std::string& path) {
  Link lk;
  int n = 0;
  for (const std::string& line : lines(path)) {
    if (line.empty()) continue;
    const std::vector<std::string> sec = sections(line);
    const std::vector<std::string> w = words(sec[0]);
    LinkEvent ev[4];
    if (w[0] == "tick") {
      uint8_t order[kMaxCalendar];
      int on = 0;
      for (const std::string& o : split(w[3], ',')) order[on++] = static_cast<uint8_t>(atoi(o.c_str()));
      const int ne = lk.tick(D(w[1]), order, on, w[2] == "calendario", ev);
      linkEvents(ev, ne, sec[1]);
      linkState(lk, sec[2]);
    } else if (w[0] == "setrung") {
      const bool ch = lk.setRung(atoi(w[1].c_str()), ev);
      linkEvents(ev, ch ? 1 : 0, sec[1]);
      linkState(lk, sec[2]);
    } else if (w[0] == "tx") { lk.onTx(D(w[1])); linkState(lk, sec[1]); }
    else if (w[0] == "heard") { lk.onHeard(D(w[1]), w[2] == "-" ? -1 : atoi(w[2].c_str()), w[3] == "1"); linkState(lk, sec[1]); }
    else if (w[0] == "holdu") lk.holdUntil = D(w[1]);
    else if (w[0] == "holdclear") lk.hold = false;
    else { fail("riga sconosciuta", "tick/setrung/tx/heard", line); break; }
    n++;
  }
  return n;
}

// ---------------------------------------------------------------------------------------------------------------------------------- ricevitore
struct MemStore : Store {
  std::vector<std::vector<uint8_t>> p;
  void reset(uint16_t n) override { p.assign(n, std::vector<uint8_t>()); }
  void put(uint16_t i, const uint8_t* d, size_t n) override { if (i < p.size()) p[i].assign(d, d + n); }
  size_t get(uint16_t i, uint8_t* out) override { if (i >= p.size()) return 0; memcpy(out, p[i].data(), p[i].size()); return p[i].size(); }
};
static int rxReplay(const std::string& path) {
  const std::vector<std::string> L = lines(path);
  std::map<std::string, std::string> h;
  for (const std::string& w : words(L[0])) { const size_t e = w.find('='); if (e != std::string::npos) h[w.substr(0, e)] = w.substr(e + 1); }
  const std::vector<uint8_t> call = unhex(h["call"]);
  MemStore store;
  Receiver rx(call.data(), call.size(), h["sx1262"] == "1", h["tcxo"] == "1", atoi(h["window"].c_str()), h["hello"] == "1", &store);
  int n = 0;
  for (size_t i = 1; i < L.size(); i++) {
    if (L[i].empty()) continue;
    const std::vector<std::string> sec = sections(L[i]);
    const std::vector<std::string> w = words(sec[0]);
    const std::vector<std::string> o = words(sec[1]);
    if (w[0] == "frame") {
      const std::vector<uint8_t> raw = unhex(w[1]);
      Msg m;
      if (!decode(raw.data(), raw.size(), &m)) { fail("il frame ricevuto non si decodifica", w[1], "NONE"); continue; }
      const Reply r = rx.onFrame(m, D(w[2]), D(w[3]), D(w[4]), atoi(w[5].c_str()), w[6] == "1");
      EXPECT((r.frame ? hex(r.frame, r.len) : std::string("-")) == o[0], "frame di risposta", o[0], r.frame ? hex(r.frame, r.len) : "-");
      EXPECT(o[1] == "-" ? !r.hasHold : (r.hasHold && r.holdUntil == D(o[1])), "tenuta del ricevitore", o[1], r.hasHold ? std::to_string(r.holdUntil) : "-");
      EXPECT(o[2] == "-" ? r.rungAfter < 0 : r.rungAfter == atoi(o[2].c_str()), "gradino dopo la risposta", o[2], std::to_string(r.rungAfter));
    } else if (w[0] == "status") {
      uint8_t b[64];
      const size_t len = rx.status(b, sizeof(b));
      EXPECT(hex(b, len) == sec[1], "STATUS", sec[1], hex(b, len));
    } else if (w[0] == "probe") {
      uint8_t b[64];
      const size_t len = rx.probeReport(b, sizeof(b));
      EXPECT((len ? hex(b, len) : std::string("-")) == sec[1], "PROBE-REPORT", sec[1], len ? hex(b, len) : "-");
    } else { fail("riga sconosciuta", "frame/status/probe", L[i]); break; }
    n++;
  }
  return n;
}

// ---------------------------------------------------------------------------------------------------------------------------------- mittente
static std::string actionStr(Sender& s, const Action& a, double* waitVal) {
  *waitVal = 0;
  uint8_t b[300];
  size_t len;
  switch (a.kind) {
    case Action::Exchange: return "exchange " + hex(a.frame, a.len) + " " + std::to_string(a.expect) + " " + std::to_string(a.tries);
    case Action::Probe: case Action::Burst: {
      std::string r = a.kind == Action::Probe ? "probe " : "burst ";
      for (int i = 0; i < a.count; i++) { if (s.frameAt(a, i, b, sizeof(b), &len) != FR_OK) return r + "<errore>"; r += (i ? "," : "") + hex(b, len); }
      return r;
    }
    case Action::ModeSet: return "modeset " + hex(a.frame, a.len) + " " + std::to_string(a.target);
    case Action::Status: return "status";
    case Action::Wait: *waitVal = a.seconds; return "wait";
    case Action::Rand: return "rand";
    case Action::SetRung: return "setrung " + std::to_string(a.target);
    case Action::HoldClear: return "holdclear";
    case Action::Legacy: return "legacy";
    default: return "<nessuna>";
  }
}
static const char* failName(FailKind k) {
  switch (k) { case FAIL_HELLO: return "hello"; case FAIL_NEGOZIAZIONE: return "negoziazione"; case FAIL_OFFER: return "offer"; case FAIL_BUDGET: return "budget"; case FAIL_PROGRESSO: return "progresso";
               case FAIL_RICERCA: return "ricerca"; case FAIL_DONE: return "done"; default: return "?"; }
}
static int txReplay(const std::string& dir, const std::string& name) {
  const std::vector<std::string> L = lines(dir + "/" + name + ".tx.txt");
  std::map<std::string, std::string> h;
  for (const std::string& w : words(L[0])) { const size_t e = w.find('='); if (e != std::string::npos) h[w.substr(0, e)] = w.substr(e + 1); }
  const std::vector<uint8_t> call = unhex(h["call"]);
  const std::vector<uint8_t> obj = unhex(lines(dir + "/" + name + ".obj.txt")[0]);
  std::vector<uint16_t> ends;
  for (const std::string& e : split(h["layers"], ',')) ends.push_back(static_cast<uint16_t>(atoi(e.c_str())));
  MemSource msrc(obj.data(), obj.size());
  Sender snd(static_cast<uint16_t>(atoi(h["sess"].c_str())), call.data(), call.size(), h["sx1262"] == "1", h["tcxo"] == "1", &msrc, obj.size(), ends.data(), static_cast<int>(ends.size()),
             D(h["budget"]), atoi(h["window"].c_str()), atoi(h["probes"].c_str()));
  int n = 0;
  for (size_t i = 1; i < L.size(); i++) {
    const std::vector<std::string> w = words(L[i]);
    if (w.empty()) continue;
    if (w[0] != "resume") {
      if (w[0] == "fail" && i + 1 >= L.size()) break;      // errore del mezzo (tempo massimo): finisce qui
      fail("manca una ripresa", "resume", L[i]);
      break;
    }
    Answer ans;
    const std::string& a = w[4];
    if (a.compare(0, 6, "frame:") == 0) {
      const std::vector<uint8_t> raw = unhex(a.substr(6));
      ans.kind = Answer::FrameIn;
      if (!decode(raw.data(), raw.size(), &ans.msg)) { fail("risposta non decodificabile", a, "NONE"); break; }
    } else if (a.compare(0, 5, "rand:") == 0) { ans.kind = Answer::Rnd; ans.rnd = D(a.substr(5)); }
    else if (a.compare(0, 5, "bool:") == 0) { ans.kind = Answer::Bool; ans.b = a[5] == '1'; }
    const Action act = snd.resume(ans, D(w[1]), atoi(w[2].c_str()), w[3] == "1");
    n++;
    const std::vector<std::string> next = words(L[i + 1]);
    if (next[0] == "act") {
      double wv;
      const std::string got = actionStr(snd, act, &wv);
      std::string want = L[i + 1].substr(4);
      if (next[1] == "wait") EXPECT(got == "wait" && wv == D(next[2]), "azione", want, got + " " + std::to_string(wv));
      else EXPECT(got == want, "azione", want, got);
      i++;
    } else if (next[0] == "end") {
      EXPECT(snd.ok() && std::to_string(snd.layersDelivered()) == next[1] && std::to_string(snd.bytesDelivered()) == next[2], "fine con consegna", L[i + 1], snd.finished() ? (snd.ok() ? "end " + std::to_string(snd.layersDelivered()) + " " + std::to_string(snd.bytesDelivered()) : std::string("fail ") + failName(snd.failure())) : "non finito");
      i++;
    } else if (next[0] == "fail") {
      EXPECT(snd.finished() && !snd.ok() && next[1] == failName(snd.failure()), "fallimento", L[i + 1], snd.finished() ? (snd.ok() ? "end" : std::string("fail ") + failName(snd.failure())) : "non finito");
      i++;
    } else { fail("riga inattesa", "act/end/fail", L[i + 1]); break; }
  }
  return n;
}

int main(int argc, char** argv) {
  const std::string dir = argc > 1 ? argv[1] : "build/tracce";
  const std::vector<std::string> names = lines(dir + "/lista.txt");
  if (names.empty()) { std::printf("FALLITO: manca %s/lista.txt (genera le tracce con tools/gen_tracce_protocollo.py)\n", dir.c_str()); return 1; }
  for (const std::string& nm : names) {
    if (nm.empty()) continue;
    const int before = g_fails;
    g_ctx = nm + " link S"; const int a = linkReplay(dir + "/" + nm + ".link_S.txt");
    g_ctx = nm + " link R"; const int b = linkReplay(dir + "/" + nm + ".link_R.txt");
    g_ctx = nm + " ricevitore"; const int c = rxReplay(dir + "/" + nm + ".rx.txt");
    g_ctx = nm + " mittente"; const int d = txReplay(dir, nm);
    std::printf("%-16s collegamento %d+%d, ricevitore %d, mittente %d passi%s\n", nm.c_str(), a, b, c, d, g_fails == before ? "" : "   <-- DIVERSO");
  }
  std::printf("firmware/v3 protocollo: %d controlli, %d falliti\n", g_checks, g_fails);
  return g_fails ? 1 : 0;
}
