// Posizione geografica: blocco di 7 byte nel pacchetto START (protocollo v2) e distanza tra due posizioni.
//
// Blocco sul canale (flag kFlagPosition, dopo il nominativo):
//   byte 0      stato: bit 0 = 1 se la posizione viene da un GPS, 0 se e' una posizione fissa impostata a mano;
//               gli altri bit sono riservati (zero in trasmissione, ignorati in ricezione)
//   byte 1-3    latitudine, 24 bit senza segno big endian: (lat + 90) / 180 * 2^24  (passo circa 1,2 m)
//   byte 4-6    longitudine, 24 bit senza segno big endian: (lon + 180) / 360 * 2^24 (passo circa 2,4 m all'equatore)
//
// In memoria le coordinate sono in decimilionesimi di grado (come i GPS u-blox): 43.7696 gradi = 437696000.
// Porta di lib/voicecore/position.{h,cpp} della v2 (stesso formato di 7 byte, stessa distanza), header-only; in piu' il locatore Maidenhead. Provato sul PC (tests/test_position.cpp).
#pragma once

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>

namespace v3 {

constexpr size_t kPositionBytes = 7;
constexpr int32_t kMaxLatE7 = 900000000;
constexpr int32_t kMaxLonE7 = 1800000000;

struct Position {
  bool valid = false;    // false: nessuna posizione
  bool fromGps = false;  // true GPS, false posizione fissa impostata dall'operatore
  int32_t latE7 = 0;     // -900000000..900000000
  int32_t lonE7 = 0;     // -1800000000..1800000000
};

// Coordinate nei limiti?
bool isValidCoordinate(int32_t latE7, int32_t lonE7);

// Scrive il blocco (kPositionBytes byte). false se la posizione non e' valida.
bool encodePosition(const Position& p, uint8_t* out);
// Legge il blocco. Le coordinate tornano arrotondate al passo del formato (circa 1-2 m).
void decodePosition(const uint8_t* in, Position& out);

// Distanza sulla sfera terrestre (formula dell'emisenoverso), in chilometri. 0 se una delle due posizioni non e' valida.
double distanceKm(const Position& a, const Position& b);

// Testo breve della distanza per il display: "0.4km", "12.3km" (sotto i 100 km un decimale), "123km", "<0.1km". Ritorna i caratteri scritti.
size_t formatDistance(char* out, size_t cap, double km);



inline bool isValidCoordinate(int32_t latE7, int32_t lonE7) {
  return latE7 >= -kMaxLatE7 && latE7 <= kMaxLatE7 && lonE7 >= -kMaxLonE7 && lonE7 <= kMaxLonE7;
}

namespace detail_pos {
constexpr int64_t kSteps = int64_t{1} << 24;

inline uint32_t quantize(int32_t valueE7, int32_t maxE7) {
  // (v + max) / (2 max) * 2^24, arrotondato; 180 gradi esatti cadrebbero su 2^24: si limita all'ultimo passo.
  const int64_t num = (static_cast<int64_t>(valueE7) + maxE7) * kSteps;
  int64_t q = (num + maxE7) / (2 * static_cast<int64_t>(maxE7));
  if (q >= kSteps) q = kSteps - 1;
  if (q < 0) q = 0;
  return static_cast<uint32_t>(q);
}

inline int32_t dequantize(uint32_t q, int32_t maxE7) {
  return static_cast<int32_t>((static_cast<int64_t>(q) * 2 * maxE7 + kSteps / 2) / kSteps - maxE7);
}
}  // namespace detail_pos

inline bool encodePosition(const Position& p, uint8_t* out) {
  if (!p.valid || !isValidCoordinate(p.latE7, p.lonE7)) return false;
  const uint32_t la = detail_pos::quantize(p.latE7, kMaxLatE7);
  const uint32_t lo = detail_pos::quantize(p.lonE7, kMaxLonE7);
  out[0] = p.fromGps ? 1 : 0;
  out[1] = static_cast<uint8_t>(la >> 16);
  out[2] = static_cast<uint8_t>(la >> 8);
  out[3] = static_cast<uint8_t>(la);
  out[4] = static_cast<uint8_t>(lo >> 16);
  out[5] = static_cast<uint8_t>(lo >> 8);
  out[6] = static_cast<uint8_t>(lo);
  return true;
}

inline void decodePosition(const uint8_t* in, Position& out) {
  const uint32_t la = (static_cast<uint32_t>(in[1]) << 16) | (static_cast<uint32_t>(in[2]) << 8) | in[3];
  const uint32_t lo = (static_cast<uint32_t>(in[4]) << 16) | (static_cast<uint32_t>(in[5]) << 8) | in[6];
  out.valid = true;
  out.fromGps = (in[0] & 1) != 0;
  out.latE7 = detail_pos::dequantize(la, kMaxLatE7);
  out.lonE7 = detail_pos::dequantize(lo, kMaxLonE7);
}

inline double distanceKm(const Position& a, const Position& b) {
  if (!a.valid || !b.valid) return 0.0;
  constexpr double kDeg = 3.14159265358979323846 / 180.0 * 1e-7;
  constexpr double kEarthKm = 6371.0;
  const double la1 = a.latE7 * kDeg, la2 = b.latE7 * kDeg;
  const double dla = la2 - la1;
  // La differenza in 64 bit (due longitudini opposte la farebbero uscire dai 32 bit); il seno al quadrato e' periodico, quindi
  // anche l'antimeridiano (179,5 E - 179,5 O) da il risultato giusto.
  const double dlo = static_cast<double>(static_cast<int64_t>(b.lonE7) - a.lonE7) * kDeg;
  const double s1 = std::sin(dla / 2), s2 = std::sin(dlo / 2);
  double h = s1 * s1 + std::cos(la1) * std::cos(la2) * s2 * s2;
  if (h > 1.0) h = 1.0;
  return 2.0 * kEarthKm * std::asin(std::sqrt(h));
}

inline size_t formatDistance(char* out, size_t cap, double km) {
  if (!out || cap == 0) return 0;
  int n;
  if (km < 0.1) n = snprintf(out, cap, "<0.1km");
  else if (km < 100.0) n = snprintf(out, cap, "%.1fkm", km);
  else n = snprintf(out, cap, "%.0fkm", km);
  return n < 0 ? 0 : (static_cast<size_t>(n) < cap ? static_cast<size_t>(n) : cap - 1);
}


// ---- locatore Maidenhead (4 o 6 caratteri, per esempio JN53 o JN53ab) -> centro del quadrato in decimilionesimi di grado ----
// Serve a calcolare la distanza da una stazione che dichiara solo il locatore (come fa il telefono senza GPS). false se il locatore non e' valido.
inline bool locatorToPosition(const char* loc, Position& out) {
  size_t n = 0;
  while (loc[n]) n++;
  if (n != 4 && n != 6 && n != 8) return false;
  auto up = [](char c) { return (c >= 'a' && c <= 'z') ? static_cast<char>(c - 32) : c; };
  const char a = up(loc[0]), b = up(loc[1]);
  if (a < 'A' || a > 'R' || b < 'A' || b > 'R' || loc[2] < '0' || loc[2] > '9' || loc[3] < '0' || loc[3] > '9') return false;
  double lon = (a - 'A') * 20.0 - 180.0 + (loc[2] - '0') * 2.0;
  double lat = (b - 'A') * 10.0 - 90.0 + (loc[3] - '0') * 1.0;
  double wLon = 2.0, wLat = 1.0;
  if (n >= 6) {
    const char c = up(loc[4]), d = up(loc[5]);
    if (c < 'A' || c > 'X' || d < 'A' || d > 'X') return false;
    wLon = 2.0 / 24.0; wLat = 1.0 / 24.0;
    lon += (c - 'A') * wLon; lat += (d - 'A') * wLat;
  }
  if (n == 8) {
    if (loc[6] < '0' || loc[6] > '9' || loc[7] < '0' || loc[7] > '9') return false;
    const double sLon = wLon / 10.0, sLat = wLat / 10.0;
    lon += (loc[6] - '0') * sLon; lat += (loc[7] - '0') * sLat;
    wLon = sLon; wLat = sLat;
  }
  lon += wLon / 2.0; lat += wLat / 2.0;                       // il centro del quadrato
  out.valid = true;
  out.fromGps = false;
  out.latE7 = static_cast<int32_t>(std::lround(lat * 1e7));
  out.lonE7 = static_cast<int32_t>(std::lround(lon * 1e7));
  return true;
}

// Blocco di 7 byte del V3 (OFFER, BLE POSITION): tipo 0 = locatore (byte 1-6 ASCII), tipo 1 = GPS assoluto (byte 1-3 latitudine, 4-6 longitudine a 24 bit, come la v2).
// Ricava la posizione da qualunque dei due. false se non e' valido.
inline bool positionFromBlock(const uint8_t* b, Position& out) {
  if (b[0] == 1) { decodePosition(b, out); out.fromGps = true; return true; }
  if (b[0] != 0) return false;
  char loc[7];
  for (int i = 0; i < 6; i++) loc[i] = static_cast<char>(b[1 + i]);
  loc[6] = 0;
  return locatorToPosition(loc, out);
}

}  // namespace v3
