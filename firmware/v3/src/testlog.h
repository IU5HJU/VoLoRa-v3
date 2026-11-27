// Registro delle prove sulla scheda: un anello di righe di testo con il tempo, leggibile dalla pagina del telefono (/log), dalla seriale (LOG) e salvabile come file.
// Serve a rifare le prove in laboratorio senza copiare righe a mano: chi prova manda il file. Nessuna memoria dinamica. Provato sul PC (tests/test_testlog.cpp).
// STUDIO: mai provato su una scheda.
#pragma once
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace v3 {

class TestLog {
 public:
  static constexpr size_t kBytes = 6144;             // circa 60 righe
  // aggiunge una riga "[ 123.4 s] testo"; quando l'anello e' pieno si perdono le righe piu' vecchie
  void add(double tSec, const char* text) {
    char line[160];
    const int n = std::snprintf(line, sizeof(line), "[%7.1f s] %s\n", tSec, text);
    if (n <= 0) return;
    size_t len = static_cast<size_t>(n) < sizeof(line) ? static_cast<size_t>(n) : sizeof(line) - 1;
    line[len - 1] = '\n';
    for (size_t i = 0; i < len; i++) put(line[i]);
    lines_++;
  }
  void addf(double tSec, const char* fmt, ...) {
    char b[140];
    va_list ap; va_start(ap, fmt);
    std::vsnprintf(b, sizeof(b), fmt, ap);
    va_end(ap);
    add(tSec, b);
  }
  // copia nel buffer, dalla riga piu' vecchia ancora intera. Ritorna i byte scritti (sempre terminato da 0).
  size_t dump(char* out, size_t cap) const {
    if (cap == 0) return 0;
    size_t start = full_ ? head_ : 0;
    const size_t total = full_ ? kBytes : head_;
    size_t skip = 0;
    if (full_) { while (skip < total && buf_[(start + skip) % kBytes] != '\n') skip++; skip++; }     // si salta la riga rimasta a meta'
    size_t n = 0;
    for (size_t i = skip; i < total && n + 1 < cap; i++) out[n++] = buf_[(start + i) % kBytes];
    out[n] = 0;
    return n;
  }
  uint32_t lines() const { return lines_; }
  void clear() { head_ = 0; full_ = false; lines_ = 0; }

 private:
  void put(char c) { buf_[head_] = c; head_ = (head_ + 1) % kBytes; if (head_ == 0) full_ = true; }
  char buf_[kBytes];
  size_t head_ = 0;
  bool full_ = false;
  uint32_t lines_ = 0;
};

}  // namespace v3
