#include <cstring>
#include <string>

#include "../src/testlog.h"
#include "testing.h"

using namespace v3;

int main() {
  static TestLog log;
  static char out[TestLog::kBytes + 8];
  log.add(1.5, "inizio");
  log.addf(12.25, "gradino R%d", 7);
  size_t n = log.dump(out, sizeof(out));
  CHECK(n == std::strlen(out) && (std::string(out) == "[    1.5 s] inizio\n[   12.2 s] gradino R7\n" || std::string(out) == "[    1.5 s] inizio\n[   12.3 s] gradino R7\n"));
  CHECK(log.lines() == 2);
  // anello: tante righe, resta la coda con righe intere e la piu' recente
  for (int i = 0; i < 400; i++) log.addf(100.0 + i, "riga numero %d con un po' di testo per riempire", i);
  n = log.dump(out, sizeof(out));
  CHECK(n > 4000 && n < TestLog::kBytes);
  CHECK(std::strstr(out, "riga numero 399") != nullptr);
  CHECK(std::strstr(out, "riga numero 0 ") == nullptr);
  CHECK(out[0] == '[');                                       // comincia da una riga intera
  CHECK(out[n - 1] == '\n');
  // buffer piccolo: non scrive oltre
  char small[32];
  n = log.dump(small, sizeof(small));
  CHECK(n == 31 && small[31] == 0);
  // righe troppo lunghe: tagliate, mai oltre
  std::string big(500, 'x');
  log.clear();
  log.add(0, big.c_str());
  n = log.dump(out, sizeof(out));
  CHECK(n < 170 && out[n - 1] == '\n' && log.lines() == 1);
  TEST_MAIN_END();
}
