#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

#include "Arduino.h"

class Print {                                    // come Print di Arduino per quel che serve: print/println di stringhe e write di un byte
 public:
  virtual ~Print() {}
  virtual size_t write(uint8_t) = 0;
  virtual size_t write(const uint8_t* buf, size_t n) { size_t k = 0; while (n--) k += write(*buf++); return k; }
  size_t write(const char* s) { return s ? write(reinterpret_cast<const uint8_t*>(s), std::strlen(s)) : 0; }
  size_t print(const char* s) { return write(s); }
  size_t print(char c) { return write(static_cast<uint8_t>(c)); }
  size_t println(const char* s) { const size_t n = write(s); return n + write(reinterpret_cast<const uint8_t*>("\r\n"), 2); }
  size_t println() { return write(reinterpret_cast<const uint8_t*>("\r\n"), 2); }
};
