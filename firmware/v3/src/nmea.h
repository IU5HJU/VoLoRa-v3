// Lettura del GPS: interprete delle frasi NMEA (GGA e RMC) e scelta della posizione da usare (GPS o posizione fissa).
// Porta di lib/voicecore/nmea.{h,cpp} della v2, header-only, provata sul PC (tests/test_nmea.cpp). La seriale e l'alimentazione del GPS sono in gps_board.h.
//
// Il GPS (u-blox sulla T-Beam) manda per default a 9600 baud, una volta al secondo, frasi come
//   $GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
//   $GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A
// L'interprete le legge un carattere alla volta, controlla il checksum e ignora tutto il resto.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>

#include "position.h"

namespace v3 {

struct GpsFix {
  bool valid = false;  // posizione valida (GGA con qualita' > 0, RMC con stato A)
  int32_t latE7 = 0;   // decimilionesimi di grado
  int32_t lonE7 = 0;
  uint8_t sats = 0;    // satelliti in uso (dalla frase GGA)
};

class NmeaParser {
 public:
  // Un carattere dalla seriale. Ritorna true quando una frase GGA o RMC valida ha appena aggiornato fix().
  bool feed(char c);

  const GpsFix& fix() const { return fix_; }
  uint32_t sentences() const { return sentences_; }        // frasi con checksum corretto (di qualsiasi tipo)
  uint32_t checksumErrors() const { return badChecksum_; }  // frasi scartate per checksum errato o formato non valido

 private:
  bool handle(char* body);  // body senza '$', '*' e checksum

  static constexpr size_t kMaxSentence = 100;
  char buf_[kMaxSentence + 1];
  size_t len_ = 0;
  bool inSentence_ = false;
  bool overflow_ = false;
  GpsFix fix_;
  uint32_t sentences_ = 0;
  uint32_t badChecksum_ = 0;
};

// Una posizione del GPS piu' vecchia di questo non si usa piu' (il GPS manda una posizione al secondo).
constexpr uint32_t kGpsMaxAgeMs = 15000;

// Posizione da usare ora: quella del GPS se e' valida e recente, altrimenti la posizione fissa (QTH), altrimenti nessuna.
// fixAgeMs: millisecondi dall'ultimo aggiornamento valido del GPS.
Position choosePosition(const GpsFix& fix, uint32_t fixAgeMs, const Position& qth);

namespace detail_nmea {

inline int hexVal(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}

// Spezza body in campi separati da virgole (sostituisce le virgole con 0). Ritorna il numero di campi.
inline size_t splitFields(char* body, char** fields, size_t cap) {
  size_t n = 0;
  char* p = body;
  while (n < cap) {
    fields[n++] = p;
    char* comma = strchr(p, ',');
    if (!comma) break;
    *comma = 0;
    p = comma + 1;
  }
  return n;
}

// "ddmm.mmmm" (latitudine, 2 cifre di gradi) o "dddmm.mmmm" (longitudine, 3 cifre) -> decimilionesimi di grado.
inline bool parseCoord(const char* s, size_t degDigits, char hemi, int32_t& e7) {
  const size_t n = strlen(s);
  if (n < degDigits + 3) return false;  // almeno gradi, due cifre di minuti e il punto
  int64_t deg = 0;
  for (size_t i = 0; i < degDigits; i++) {
    if (s[i] < '0' || s[i] > '9') return false;
    deg = deg * 10 + (s[i] - '0');
  }
  const char* m = s + degDigits;
  if (m[0] < '0' || m[0] > '9' || m[1] < '0' || m[1] > '9') return false;
  int64_t minE6 = ((m[0] - '0') * 10 + (m[1] - '0')) * 1000000LL;
  if (m[2] == '.') {
    int64_t scale = 100000;
    for (const char* f = m + 3; *f; f++) {
      if (*f < '0' || *f > '9') return false;
      minE6 += (*f - '0') * scale;
      scale /= 10;
      if (scale == 0) break;
    }
  } else if (m[2] != 0) {
    return false;
  }
  if (minE6 >= 60 * 1000000LL) return false;
  int64_t v = deg * 10000000LL + (minE6 + 3) / 6;  // minuti (1e-6) / 6 = decimilionesimi di grado, arrotondato
  if (hemi == 'S' || hemi == 'W') v = -v;
  else if (hemi != 'N' && hemi != 'E') return false;
  e7 = static_cast<int32_t>(v);
  return true;
}

inline int parseUint(const char* s) {
  if (!*s) return -1;
  int v = 0;
  for (; *s; s++) {
    if (*s < '0' || *s > '9') return -1;
    v = v * 10 + (*s - '0');
    if (v > 1000) return -1;
  }
  return v;
}

}  // namespace detail_nmea

inline bool NmeaParser::feed(char c) {
  if (c == '$') {  // inizio frase (anche se la precedente non era finita)
    inSentence_ = true;
    overflow_ = false;
    len_ = 0;
    return false;
  }
  if (!inSentence_) return false;
  if (c == '\r' || c == '\n') {
    inSentence_ = false;
    if (overflow_ || len_ < 4) {
      if (len_ > 0 || overflow_) badChecksum_++;
      len_ = 0;
      return false;
    }
    buf_[len_] = 0;
    // body*HH
    char* star = strrchr(buf_, '*');
    if (!star || strlen(star) != 3) {
      badChecksum_++;
      return false;
    }
    const int h1 = detail_nmea::hexVal(star[1]), h2 = detail_nmea::hexVal(star[2]);
    if (h1 < 0 || h2 < 0) {
      badChecksum_++;
      return false;
    }
    uint8_t x = 0;
    for (const char* p = buf_; p < star; p++) x ^= static_cast<uint8_t>(*p);
    if (x != static_cast<uint8_t>(h1 * 16 + h2)) {
      badChecksum_++;
      return false;
    }
    *star = 0;
    sentences_++;
    return handle(buf_);
  }
  if (len_ >= kMaxSentence) {
    overflow_ = true;
    return false;
  }
  buf_[len_++] = c;
  return false;
}

inline bool NmeaParser::handle(char* body) {
  char* f[16];
  const size_t n = detail_nmea::splitFields(body, f, 16);
  if (n < 1 || strlen(f[0]) != 5) return false;
  const char* type = f[0] + 2;  // dopo la sigla del sistema (GP, GN, GL...)

  if (strcmp(type, "GGA") == 0) {
    // 0 tipo, 1 ora, 2 lat, 3 N/S, 4 lon, 5 E/W, 6 qualita', 7 satelliti
    if (n < 8) return false;
    const int quality = detail_nmea::parseUint(f[6]);
    const int sats = detail_nmea::parseUint(f[7]);
    if (quality <= 0) {  // 0 = nessun fix; ogni altro caso non valido e' trattato come nessun fix
      fix_.valid = false;
      fix_.sats = sats > 0 && sats < 100 ? static_cast<uint8_t>(sats) : 0;
      return true;
    }
    int32_t la, lo;
    if (f[3][0] == 0 || f[5][0] == 0 || !detail_nmea::parseCoord(f[2], 2, f[3][0], la) || !detail_nmea::parseCoord(f[4], 3, f[5][0], lo)) return false;
    if (!isValidCoordinate(la, lo)) return false;
    fix_.valid = true;
    fix_.latE7 = la;
    fix_.lonE7 = lo;
    fix_.sats = sats > 0 && sats < 100 ? static_cast<uint8_t>(sats) : 0;
    return true;
  }
  if (strcmp(type, "RMC") == 0) {
    // 0 tipo, 1 ora, 2 stato (A valido, V non valido), 3 lat, 4 N/S, 5 lon, 6 E/W
    if (n < 7) return false;
    if (f[2][0] != 'A') {
      fix_.valid = false;
      return true;
    }
    int32_t la, lo;
    if (f[4][0] == 0 || f[6][0] == 0 || !detail_nmea::parseCoord(f[3], 2, f[4][0], la) || !detail_nmea::parseCoord(f[5], 3, f[6][0], lo)) return false;
    if (!isValidCoordinate(la, lo)) return false;
    fix_.valid = true;
    fix_.latE7 = la;
    fix_.lonE7 = lo;
    return true;
  }
  return false;
}

inline Position choosePosition(const GpsFix& fix, uint32_t fixAgeMs, const Position& qth) {
  if (fix.valid && fixAgeMs <= kGpsMaxAgeMs) {
    Position p;
    p.valid = true;
    p.fromGps = true;
    p.latE7 = fix.latE7;
    p.lonE7 = fix.lonE7;
    return p;
  }
  return qth;  // posizione fissa, o non valida se non impostata
}


}  // namespace v3
