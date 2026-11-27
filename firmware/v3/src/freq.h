// Frequenza configurabile (nota dell'autore del 26/11/2026, docs/regole-radioamatoriali.md): la frequenza del canale di T3 e T-Beam e' liberamente configurabile;
// si controlla SOLO che stia nel campo di sintonia del chip (SX1278: 137-175 e 410-525 MHz; SX1262: 150-960 MHz, datasheet). Nessun altro limite e nessuna avvertenza.
// Il valore di partenza e' 433,700 MHz (docs/band-plan.md). Due stazioni si incontrano solo sulla stessa frequenza: si imposta su tutte e due.
// Nucleo senza dipendenze dalla scheda, provato sul PC (tests/test_freq.cpp).
#pragma once
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <strings.h>

#include "limits.h"

namespace v3 {

enum class FreqCmd { NotFreq, Invalid, Set, Show };
struct FreqParse { FreqCmd cmd = FreqCmd::NotFreq; double khz = 0; const char* why = ""; };

// "FREQ" (mostra) | "FREQ 433.700" | "FREQ 433,7" | "freq 868.0": in MHz con al massimo 3 decimali (risoluzione di 1 kHz; il passo di sintesi dei chip e' circa 61 Hz).
// Se il numero e' sensato ma fuori dal campo del chip il comando e' Invalid con la ragione.
inline FreqParse parseFreq(const char* line, bool sx1262) {
  FreqParse r;
  const char* p = line;
  while (*p == ' ' || *p == '\t') p++;
  if (strncasecmp(p, "FREQ", 4) != 0) return r;
  p += 4;
  if (*p && *p != ' ' && *p != '\t') return r;                      // un'altra parola ("FREQUENZA...")
  while (*p == ' ' || *p == '\t') p++;
  if (!*p) { r.cmd = FreqCmd::Show; return r; }
  // numero: cifre, un solo separatore (punto o virgola), al massimo 3 decimali
  int ip = 0, dp = 0, nd = 0;
  long whole = 0, frac = 0;
  bool sep = false;
  const char* q = p;
  for (; *q && *q != ' ' && *q != '\t'; q++) {
    if (*q >= '0' && *q <= '9') {
      if (!sep) { if (++ip > 4) { r.cmd = FreqCmd::Invalid; r.why = "numero troppo grande"; return r; } whole = whole * 10 + (*q - '0'); }
      else { if (++dp > 3) { r.cmd = FreqCmd::Invalid; r.why = "al massimo 3 decimali (1 kHz)"; return r; } frac = frac * 10 + (*q - '0'); }
      nd++;
    } else if ((*q == '.' || *q == ',') && !sep) sep = true;
    else { r.cmd = FreqCmd::Invalid; r.why = "scrivi la frequenza in MHz, per esempio FREQ 433.700"; return r; }
  }
  while (*q == ' ' || *q == '\t') q++;
  if (*q || ip == 0) { r.cmd = FreqCmd::Invalid; r.why = "scrivi la frequenza in MHz, per esempio FREQ 433.700"; return r; }
  for (int i = dp; i < 3; i++) frac *= 10;
  r.khz = static_cast<double>(whole) * 1000.0 + static_cast<double>(frac);
  if (!inTuning(sx1262, r.khz)) {
    r.cmd = FreqCmd::Invalid;
    r.why = sx1262 ? "fuori dal campo dell'SX1262: 150-960 MHz" : "fuori dal campo dell'SX1278: 137-175 oppure 410-525 MHz";
    return r;
  }
  r.cmd = FreqCmd::Set;
  return r;
}

}  // namespace v3
