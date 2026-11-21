// Prove della logica del firmware di misura sul PC: make test
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>

#include "../src/misura_core.h"

using namespace misura;

static int fails = 0;
#define CHECK(c)                                                  \
  do {                                                            \
    if (!(c)) {                                                   \
      std::printf("FALLITO riga %d: %s\n", __LINE__, #c);         \
      fails++;                                                    \
    }                                                             \
  } while (0)

int main() {
  // Tempo in aria: valori dello script docs/scala-modi.md (255 byte, preambolo 8, CR 4/5, CRC, intestazione esplicita)
  // confronto in millisecondi arrotondati, come nella tabella
  auto ms = [](uint32_t us) { return (us + 500) / 1000; };
  CHECK(ms(loraToaUs(7, 250, 5, 255, 8)) == 200);
  CHECK(ms(loraToaUs(12, 125, 5, 255, 8)) == 9019);
  CHECK(ms(loraToaUs(5, 500, 5, 255, 8)) == 35);
  CHECK(ms(loraToaUs(6, 500, 5, 255, 8)) == 58);
  CHECK(fskToaUs(100.0f, 64, 16) == 6720);

  // Comandi
  Tokens t = tokenize("mode lora 250 7 5");
  CHECK(t.n == 5 && !std::strcmp(t.tok[0], "MODE") && !std::strcmp(t.tok[1], "LORA") && !std::strcmp(t.tok[2], "250"));
  t = tokenize("  call   iu5hju ");
  CHECK(t.n == 2 && !std::strcmp(t.tok[1], "IU5HJU"));
  t = tokenize("freq 433.475");
  CHECK(t.n == 2 && !std::strcmp(t.tok[1], "433.475"));
  t = tokenize("");
  CHECK(t.n == 0);
  float f = 0;
  int i = 0;
  CHECK(parseFloat("433.475", &f) && f > 433.4f && f < 433.5f);
  CHECK(!parseFloat("abc", &f) && !parseFloat("1.2x", &f) && !parseFloat("nan", &f) && !parseFloat("", &f));
  CHECK(parseInt("-5", &i) && i == -5);
  CHECK(!parseInt("5.2", &i) && !parseInt("", &i));
  CHECK(freqOk(430.0f) && freqOk(440.0f) && !freqOk(429.9f) && !freqOk(440.1f) && !freqOk(868.0f));
  CHECK(loraValid(125.0f, 12, 5) && loraValid(7.8f, 12, 8) && loraValid(500.0f, 5, 5));
  CHECK(!loraValid(100.0f, 7, 5) && !loraValid(125.0f, 4, 5) && !loraValid(125.0f, 13, 5) && !loraValid(125.0f, 7, 4));
  CHECK(fskValid(100.0f, 50.0f, 200.0f) && fskValid(300.0f, 50.0f, 467.0f));
  CHECK(fskValid(300.0f, 100.0f, 467.0f) && !fskValid(300.0f, 101.0f, 467.0f));  // dev + kbps/2 <= 250
  CHECK(!fskValid(400.0f, 10.0f, 200.0f) && !fskValid(100.0f, 0.1f, 200.0f));

  // Pacchetto: costruzione, lettura, errori
  uint8_t buf[kMaxPayload];
  CHECK(!buildPacket(buf, 25, 1, "IU5HJU") && !buildPacket(buf, 256, 1, "IU5HJU"));
  for (int len : {26, 64, 100, 255}) {
    CHECK(buildPacket(buf, len, 12345u + static_cast<uint32_t>(len), "IU5HJU"));
    Parsed p = parsePacket(buf, len);
    CHECK(p.status == PacketStatus::Ok && p.seq == 12345u + static_cast<uint32_t>(len) && p.bitErrors == 0);
  }
  CHECK(buildPacket(buf, 100, 7, "IU5HJU"));
  buf[50] ^= 0x01;  // un bit rovinato nel riempimento
  Parsed p = parsePacket(buf, 100);
  CHECK(p.status == PacketStatus::BadCrc && p.seq == 7 && p.bitErrors == 1);
  buf[50] ^= 0x01;
  buf[60] ^= 0xFF;
  buf[61] ^= 0x0F;
  p = parsePacket(buf, 100);
  CHECK(p.status == PacketStatus::BadCrc && p.bitErrors == 12);
  buf[0] = 'X';
  CHECK(parsePacket(buf, 100).status == PacketStatus::BadMagic);
  buildPacket(buf, 100, 7, "IU5HJU");
  CHECK(parsePacket(buf, 99).status == PacketStatus::BadLength);
  CHECK(parsePacket(buf, 10).status == PacketStatus::TooShort);
  // Riempimento diverso per sequenze diverse
  uint8_t a[64], b[64];
  fillPattern(a, 64, 1);
  fillPattern(b, 64, 2);
  CHECK(std::memcmp(a, b, 64) != 0);
  // CRC32 noto
  CHECK(crc32(reinterpret_cast<const uint8_t*>("123456789"), 9) == 0xCBF43926u);

  // Statistiche: 1..10 con 3 e 4 mancanti, un duplicato, un pacchetto rovinato
  Stats s;
  for (uint32_t q : {1u, 2u, 5u, 6u, 6u, 7u, 8u, 9u, 10u}) {
    buildPacket(buf, 64, q, "IU5HJU");
    s.add(parsePacket(buf, 64), false, -100.0f, 5.0f, 100.0f);
  }
  buildPacket(buf, 64, 4, "IU5HJU");
  buf[30] ^= 0x10;
  s.add(parsePacket(buf, 64), false, -100.0f, 5.0f, 100.0f);
  CHECK(s.rxOk == 9 && s.rxBad == 1 && s.dup == 1 && s.bitErrors == 1);
  CHECK(s.firstSeq == 1 && s.maxSeq == 10 && s.lost() == 2);
  CHECK(std::fabs(s.meanRssi() + 100.0) < 1e-6 && std::fabs(s.meanSnr() - 5.0) < 1e-6);
  // Errore del CRC radio: il pacchetto non conta come buono anche se il resto torna
  Stats s2;
  buildPacket(buf, 64, 1, "IU5HJU");
  s2.add(parsePacket(buf, 64), true, NAN, NAN, NAN);
  CHECK(s2.rxOk == 0 && s2.rxBad == 1 && std::isnan(s2.meanRssi()) && s2.lost() == 0);
  char line[200];
  formatSummary(line, sizeof(line), s);
  CHECK(std::strstr(line, "RXSUM ok=9 bad=1 lost=2 dup=1") == line);

  if (fails) {
    std::printf("%d prove fallite\n", fails);
    return 1;
  }
  std::printf("misura_core: tutte le prove passate\n");
  return 0;
}
