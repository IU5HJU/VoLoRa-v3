// Locatore Maidenhead e blocco di posizione del V3 (src/position.h): centro del quadrato, distanze note, blocco da 7 byte (tipo 0 locatore, tipo 1 GPS).
#include <cmath>
#include <cstring>

#include "../src/position.h"
#include "testing.h"

using namespace v3;

int main() {
  Position p;
  CHECK(locatorToPosition("JN53ab", p) && p.valid && !p.fromGps);
  CHECK(std::abs(p.latE7 / 1e7 - 43.0625) < 1e-6 && std::abs(p.lonE7 / 1e7 - 10.0417) < 1e-4);          // centro del quadrato JN53ab
  CHECK(locatorToPosition("jn53ab", p));                                                              // minuscole
  CHECK(locatorToPosition("JN53", p) && std::abs(p.latE7 / 1e7 - 43.5) < 1e-6 && std::abs(p.lonE7 / 1e7 - 11.0) < 1e-6);   // a 4 caratteri il centro e' 43,5 N 11 E
  CHECK(locatorToPosition("JN53ab12", p));
  CHECK(!locatorToPosition("JN5", p) && !locatorToPosition("ZZ53ab", p) && !locatorToPosition("JN53yy", p) && !locatorToPosition("JN5Xab", p) && !locatorToPosition("", p) && !locatorToPosition("JN53ab1", p));
  // angoli del mondo: AA00 e RR99
  CHECK(locatorToPosition("AA00", p) && std::abs(p.latE7 / 1e7 + 89.5) < 1e-6 && std::abs(p.lonE7 / 1e7 + 179.0) < 1e-6);
  CHECK(locatorToPosition("RR99", p) && std::abs(p.latE7 / 1e7 - 89.5) < 1e-6 && std::abs(p.lonE7 / 1e7 - 179.0) < 1e-6);
  // distanze: un grado di latitudine sono circa 111,2 km; JN53 -> JN54 e' un grado di latitudine (la prima cifra e' la longitudine, la seconda la latitudine)
  Position a, b;
  locatorToPosition("JN53", a); locatorToPosition("JN54", b);
  CHECK(std::abs(distanceKm(a, b) - 111.19) < 0.3);
  // blocco da 7 byte
  uint8_t blk[7] = {0, 'J', 'N', '5', '3', 'a', 'b'};
  Position q;
  CHECK(positionFromBlock(blk, q) && !q.fromGps && std::abs(q.latE7 / 1e7 - 43.0625) < 1e-6);
  Position g; g.valid = true; g.fromGps = true; g.latE7 = 437696000; g.lonE7 = 112558000;
  uint8_t gb[7];
  CHECK(encodePosition(g, gb) && gb[0] == 1);
  CHECK(positionFromBlock(gb, q) && q.fromGps && std::abs(q.latE7 - g.latE7) < 20000 && std::abs(q.lonE7 - g.lonE7) < 30000);
  uint8_t bad[7] = {2, 0, 0, 0, 0, 0, 0};
  CHECK(!positionFromBlock(bad, q));
  uint8_t badLoc[7] = {0, 'Z', 'Z', '5', '3', 'a', 'b'};
  CHECK(!positionFromBlock(badLoc, q));
  char t[16];
  formatDistance(t, sizeof(t), 12.34); CHECK(std::strcmp(t, "12.3km") == 0);
  TEST_MAIN_END();
}
