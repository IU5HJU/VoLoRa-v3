// Minimo di Arduino per compilare Adafruit_GFX (la libreria VERA) sul PC: tests/test_oled_real.cpp. Non e' Arduino: solo i tipi e le macro che servono al disegno.
#pragma once
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <algorithm>
#include <cmath>

using std::sin;
using std::cos;
#ifndef radians
#define radians(deg) ((deg) * 0.017453292519943295)
#endif

#define PROGMEM
#define pgm_read_byte(addr) (*(const unsigned char *)(addr))
#define pgm_read_word(addr) (*(const unsigned short *)(addr))
#define pgm_read_dword(addr) (*(const unsigned long *)(addr))
#define pgm_read_pointer(addr) ((void *)*(const uintptr_t *)(addr))
#ifndef min
#define min(a, b) ((a) < (b) ? (a) : (b))
#define max(a, b) ((a) > (b) ? (a) : (b))
#endif
class __FlashStringHelper;
#define F(s) (reinterpret_cast<const __FlashStringHelper *>(s))
class String {                                   // solo per le firme di getTextBounds
 public:
  String(const char* s = "") : s_(s) {}
  const char* c_str() const { return s_; }
  size_t length() const { return std::strlen(s_); }
 private:
  const char* s_;
};
