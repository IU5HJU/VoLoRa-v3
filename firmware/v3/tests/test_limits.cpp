// Conformita' di src/limits.h al riferimento Python (tools/limiti_chip.py): maschere dei gradini, singoli controlli e maschera comune. Uso: test_limits <cartella dei vettori>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>

#include "../src/limits.h"

using namespace v3;

int main(int argc, char** argv) {
  const std::string dir = argc > 1 ? argv[1] : "tests/vettori";
  std::ifstream f(dir + "/limits.txt");
  if (!f) { std::printf("FALLITO: manca limits.txt\n"); return 1; }
  int n = 0, ko = 0;
  for (std::string line; std::getline(f, line);) {
    std::istringstream ss(line);
    std::string op;
    ss >> op;
    bool ok = false;
    std::string d;
    if (op == "mask") {
      std::string chip; int tcxo; double khz; unsigned want;
      ss >> chip >> tcxo >> khz >> want;
      const unsigned got = rungMask(chip == "SX1262", tcxo != 0, khz);
      ok = got == want; d = "maschera " + std::to_string(got) + " invece di " + std::to_string(want);
    } else if (op == "rung") {
      int rid; std::string chip; double khz, ppm; int want;
      ss >> rid >> chip >> khz >> ppm >> want;
      const int got = rungSupported(rid, chip == "SX1262", khz, ppm) ? 1 : 0;
      ok = got == want; d = "R" + std::to_string(rid) + " " + std::to_string(got) + " invece di " + std::to_string(want);
    } else if (op == "common") {
      std::string ca, cb; unsigned ma, mb, want;
      ss >> ca >> ma >> cb >> mb >> want;
      const unsigned got = commonMask(ca == "SX1262", static_cast<uint16_t>(ma), cb == "SX1262", static_cast<uint16_t>(mb));
      ok = got == want; d = "comune " + std::to_string(got) + " invece di " + std::to_string(want);
    }
    n++;
    if (!ok && ko++ < 5) std::printf("FALLITO: %s -> %s\n", line.c_str(), d.c_str());
  }
  // le decisioni del 26/11/2026, dette in chiaro
  const bool dec = rungMask(false, false) == 0x0FFF && rungMask(true, false) == 0x0FFE && rungMask(false, true) == 0x7FFF && commonMask(false, 0x0FFF, true, 0x0FFE) == (0x0FFE & ~(1u << 3));
  if (!dec) { std::printf("FALLITO: decisioni sulle maschere (0x0FFF, 0x0FFE, 0x7FFF, R3 tolto se i chip differiscono)\n"); ko++; }
  std::printf("firmware/v3 limiti: %d controlli, %d falliti\n", n + 1, ko);
  return ko ? 1 : 0;
}
