// Frame del protocollo immagini V3 (docs/protocollo-immagini.md): codifica e decodifica in C++, senza memoria dinamica e senza dipendenze dalla scheda.
// Porta di tools/sim_immagini.py (enc_* e decode); provata contro il riferimento Python (tests/test_frames.cpp con tests/vettori/frames_*.txt).
// Differenze volute dal Python: il nominativo e' al massimo di 31 byte; i livelli dell'OFFER sono al massimo 16 (il Python ne accetta di piu'): un frame fuori da questi limiti e' "non valido".
// STUDIO: non e' stato mai eseguito su una scheda.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace v3 {
namespace img {

constexpr uint8_t kVersion = 3;
enum Type : uint8_t { HELLO = 0, PROBE = 1, PROBE_REPORT = 2, MODE_SET = 3, MODE_ACK = 4, OFFER = 5, ACCEPT = 6, DATA = 7, STATUS = 8, PARITY = 9, DONE = 10, ABORT = 11, ID = 12, TEST = 15 };
constexpr uint8_t F_REPLY = 1, F_MEASURE = 2, F_POS = 16, F_OPT = 128;        // HELLO (OFFER: solo F_POS e F_OPT)
constexpr uint8_t F_LAST_WINDOW = 1, F_RETX = 2, F_LAST_OBJECT = 4, F_LAYER_END = 8;   // DATA
constexpr uint8_t F_RELAYED = 16, kHopShift = 5;                              // DATA: bit 4 ritrasmesso da un ripetitore, bit 5-7 numero di salti
constexpr int kMaxCall = 31, kMaxLayers = 16;

struct Msg {
  uint8_t type = 0;
  uint16_t sess = 0;
  uint8_t flags = 0;
  size_t len = 0;
  // HELLO, OFFER, DONE
  uint8_t call[kMaxCall + 1];
  uint8_t callLen = 0;
  // HELLO
  uint8_t chip = 0;                 // 0 SX1278, 1 SX1262
  uint16_t rungMask = 0;
  uint8_t maxFrame = 0;
  uint16_t memKb = 0;
  bool reply = false, hasMeasure = false;
  int8_t rssi = 0, snr = 0;
  // posizione e opzioni TLV (HELLO e OFFER): puntano nel frame decodificato
  bool hasPos = false;
  uint8_t pos[7];
  bool hasOpts = false;
  const uint8_t* opts = nullptr;
  size_t optsLen = 0;
  // PROBE, PROBE_REPORT, MODE_SET, MODE_ACK
  uint8_t rung = 0, idx = 0, count = 0, expected = 0, received = 0, k = 0, repeat = 0;
  // OFFER
  uint8_t objType = 0, piece = 0, nl = 0;
  uint32_t size = 0, crc = 0;
  uint16_t nPieces = 0, w = 0, h = 0;
  uint16_t layerEnds[kMaxLayers];
  // ACCEPT
  uint8_t layers = 0, window = 0;
  // DATA
  uint16_t offset = 0;
  const uint8_t* payload = nullptr;
  size_t payloadLen = 0;
  // STATUS
  uint16_t base = 0;
  uint64_t bitmap = 0;
  uint8_t lossPct = 0, layersDone = 0;
  // DONE
  uint32_t nbytes = 0;
  // ABORT
  uint8_t reason = 0;
};

namespace detail {
inline uint32_t rd(const uint8_t* b, int n) { uint32_t v = 0; for (int i = 0; i < n; i++) v = (v << 8) | b[i]; return v; }
inline bool utf8Valid(const uint8_t* s, size_t n) {
  size_t i = 0;
  while (i < n) {
    const uint8_t c = s[i];
    size_t len; uint32_t cp;
    if (c < 0x80) { i++; continue; }
    if ((c & 0xE0) == 0xC0) { len = 2; cp = c & 0x1F; } else if ((c & 0xF0) == 0xE0) { len = 3; cp = c & 0x0F; } else if ((c & 0xF8) == 0xF0) { len = 4; cp = c & 0x07; } else return false;
    if (i + len > n) return false;
    for (size_t k = 1; k < len; k++) { if ((s[i + k] & 0xC0) != 0x80) return false; cp = (cp << 6) | (s[i + k] & 0x3F); }
    if ((len == 2 && cp < 0x80) || (len == 3 && cp < 0x800) || (len == 4 && cp < 0x10000) || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) return false;
    i += len;
  }
  return true;
}
// posizione di 7 byte: tipo 0 = locatore (6 caratteri ASCII), tipo 1 = GPS assoluta
inline bool posValid(const uint8_t* p) {
  if (p[0] == 1) return true;
  if (p[0] != 0) return false;
  for (int i = 1; i < 7; i++) if (p[i] >= 0x80) return false;
  return true;
}
// opzioni TLV: tipo, lunghezza, valore, fino alla fine; troncate = non valide
inline bool optsValid(const uint8_t* o, size_t n) {
  size_t i = 0;
  while (i < n) {
    if (i + 2 > n || i + 2 + o[i + 1] > n) return false;
    i += 2 + o[i + 1];
  }
  return true;
}
struct Writer {
  uint8_t* p; size_t cap, n; bool ok;
  Writer(uint8_t* b, size_t c) : p(b), cap(c), n(0), ok(true) {}
  void u8(uint32_t v) { if (n < cap) p[n++] = static_cast<uint8_t>(v); else ok = false; }
  void u16(uint32_t v) { u8(v >> 8); u8(v); }
  void u24(uint32_t v) { u8(v >> 16); u8(v >> 8); u8(v); }
  void u32(uint32_t v) { u16(v >> 16); u16(v); }
  void u64(uint64_t v) { u32(static_cast<uint32_t>(v >> 32)); u32(static_cast<uint32_t>(v)); }
  void s8(int v) { u8(static_cast<uint8_t>(v < -128 ? -128 : v > 127 ? 127 : v)); }
  void bytes(const uint8_t* d, size_t k) { for (size_t i = 0; i < k; i++) u8(d[i]); }
  void hdr(uint8_t type, uint16_t sess, uint8_t flags) { u8((kVersion << 4) | type); u16(sess); u8(flags); }
  size_t done() const { return ok ? n : 0; }
};
}  // namespace detail

// ------------------------------------------------------------------------------------------------------------ codifica: ritornano la lunghezza (0 = non entra)
inline size_t encHello(uint8_t* out, size_t cap, uint16_t sess, const uint8_t* call, size_t callLen, bool sx1262, uint16_t rungMask, uint8_t maxFrame, uint16_t memKb, bool reply,
                       const int* rssi, const int* snr, const uint8_t* pos7, const uint8_t* opts, size_t optsLen) {
  detail::Writer w(out, cap);
  const bool meas = rssi != nullptr && snr != nullptr;
  w.hdr(HELLO, sess, static_cast<uint8_t>((reply ? F_REPLY : 0) | (meas ? F_MEASURE : 0) | (pos7 ? F_POS : 0) | (optsLen ? F_OPT : 0)));
  w.u8(static_cast<uint8_t>(callLen)); w.bytes(call, callLen); w.u8(sx1262 ? 1 : 0); w.u16(rungMask); w.u8(maxFrame); w.u16(memKb);
  if (meas) { w.s8(*rssi); w.s8(*snr); }
  if (pos7) w.bytes(pos7, 7);
  if (optsLen) w.bytes(opts, optsLen);
  return w.done();
}
inline size_t encProbe(uint8_t* out, size_t cap, uint16_t sess, uint8_t rung, uint8_t idx, uint8_t count, size_t filler) {
  detail::Writer w(out, cap); w.hdr(PROBE, sess, 0); w.u8(rung); w.u8(idx); w.u8(count); for (size_t i = 0; i < filler; i++) w.u8(0); return w.done();
}
inline size_t encProbeReport(uint8_t* out, size_t cap, uint16_t sess, uint8_t rung, uint8_t expected, uint8_t received, int rssi, int snr) {
  detail::Writer w(out, cap); w.hdr(PROBE_REPORT, sess, 0); w.u8(rung); w.u8(expected); w.u8(received); w.s8(rssi); w.s8(snr); return w.done();
}
inline size_t encModeSet(uint8_t* out, size_t cap, uint16_t sess, uint8_t rung, uint8_t k, uint8_t repeat) {
  detail::Writer w(out, cap); w.hdr(MODE_SET, sess, 0); w.u8(rung); w.u8(k); w.u8(repeat); return w.done();
}
inline size_t encModeAck(uint8_t* out, size_t cap, uint16_t sess, uint8_t rung) { detail::Writer w(out, cap); w.hdr(MODE_ACK, sess, 0); w.u8(rung); return w.done(); }
inline size_t encOffer(uint8_t* out, size_t cap, uint16_t sess, const uint8_t* call, size_t callLen, uint8_t objType, uint32_t size, uint8_t piece, uint16_t nPieces, uint16_t wd, uint16_t ht,
                       const uint16_t* layerEnds, size_t nl, uint32_t crc, const uint8_t* pos7, const uint8_t* opts, size_t optsLen) {
  detail::Writer w(out, cap);
  w.hdr(OFFER, sess, static_cast<uint8_t>((pos7 ? F_POS : 0) | (optsLen ? F_OPT : 0)));
  w.u8(static_cast<uint8_t>(callLen)); w.bytes(call, callLen); w.u8(objType); w.u24(size); w.u8(piece); w.u16(nPieces); w.u16(wd); w.u16(ht);
  w.u8(static_cast<uint8_t>(nl)); for (size_t i = 0; i < nl; i++) w.u16(layerEnds[i]);
  w.u32(crc);
  if (pos7) w.bytes(pos7, 7);
  if (optsLen) w.bytes(opts, optsLen);
  return w.done();
}
inline size_t encAccept(uint8_t* out, size_t cap, uint16_t sess, uint8_t layers, uint8_t window, uint8_t k) {
  detail::Writer w(out, cap); w.hdr(ACCEPT, sess, 0); w.u8(layers); w.u8(window); w.u8(k); return w.done();
}
inline size_t encData(uint8_t* out, size_t cap, uint16_t sess, uint16_t offset, const uint8_t* payload, size_t n, uint8_t flags) {
  detail::Writer w(out, cap); w.hdr(DATA, sess, flags); w.u16(offset); w.bytes(payload, n); return w.done();
}
inline size_t encStatus(uint8_t* out, size_t cap, uint16_t sess, uint16_t base, uint64_t bitmap, int rssi, int snr, int lossPct, uint8_t layersDone, uint8_t flags) {
  detail::Writer w(out, cap); w.hdr(STATUS, sess, flags); w.u16(base); w.u64(bitmap); w.s8(rssi); w.s8(snr); w.u8(lossPct > 100 ? 100 : lossPct); w.u8(layersDone); return w.done();
}
inline size_t encDone(uint8_t* out, size_t cap, uint16_t sess, const uint8_t* call, size_t callLen, uint8_t layers, uint32_t nbytes, uint32_t crcPrefix) {
  detail::Writer w(out, cap); w.hdr(DONE, sess, 0); w.u8(static_cast<uint8_t>(callLen)); w.bytes(call, callLen); w.u8(layers); w.u24(nbytes); w.u32(crcPrefix); return w.done();
}
inline size_t encAbort(uint8_t* out, size_t cap, uint16_t sess, uint8_t reason) { detail::Writer w(out, cap); w.hdr(ABORT, sess, 0); w.u8(reason); return w.done(); }

// ------------------------------------------------------------------------------------------------------------ decodifica
// false se non e' un frame V3 valido. I puntatori (opts, payload) puntano dentro `b`.
inline bool decode(const uint8_t* b, size_t n, Msg* m) {
  using detail::rd;
  if (n < 4 || (b[0] >> 4) != kVersion) return false;
  *m = Msg();
  m->type = b[0] & 0x0F; m->sess = static_cast<uint16_t>(rd(b + 1, 2)); m->flags = b[3]; m->len = n;
  const uint8_t* d = b + 4;
  const size_t bn = n - 4;
  auto callAt = [&](size_t at, size_t* end) -> bool {              // lunghezza + byte UTF-8 validi
    if (at >= bn) return false;
    const size_t cl = d[at];
    if (cl > static_cast<size_t>(kMaxCall) || at + 1 + cl > bn || !detail::utf8Valid(d + at + 1, cl)) return false;
    memcpy(m->call, d + at + 1, cl); m->callLen = static_cast<uint8_t>(cl); *end = at + 1 + cl;
    return true;
  };
  switch (m->type) {
    case HELLO: {
      size_t o;
      if (!callAt(0, &o) || bn < o + 6) return false;
      m->chip = d[o] ? 1 : 0; m->rungMask = static_cast<uint16_t>(rd(d + o + 1, 2)); m->maxFrame = d[o + 3]; m->memKb = static_cast<uint16_t>(rd(d + o + 4, 2));
      m->reply = (m->flags & F_REPLY) != 0;
      o += 6;
      if (m->flags & F_MEASURE) { if (bn < o + 2) return false; m->hasMeasure = true; m->rssi = static_cast<int8_t>(d[o]); m->snr = static_cast<int8_t>(d[o + 1]); o += 2; }
      if (m->flags & F_POS) { if (bn < o + 7 || !detail::posValid(d + o)) return false; m->hasPos = true; memcpy(m->pos, d + o, 7); o += 7; }
      if (m->flags & F_OPT) { if (!detail::optsValid(d + o, bn - o)) return false; m->hasOpts = true; m->opts = d + o; m->optsLen = bn - o; }
      return true;
    }
    case PROBE: if (bn < 3) return false; m->rung = d[0]; m->idx = d[1]; m->count = d[2]; return true;
    case PROBE_REPORT: if (bn < 5) return false; m->rung = d[0]; m->expected = d[1]; m->received = d[2]; m->rssi = static_cast<int8_t>(d[3]); m->snr = static_cast<int8_t>(d[4]); return true;
    case MODE_SET: if (bn < 3) return false; m->rung = d[0]; m->k = d[1]; m->repeat = d[2]; return true;
    case MODE_ACK: if (bn < 1) return false; m->rung = d[0]; return true;
    case OFFER: {
      size_t o;
      if (!callAt(0, &o) || bn < o + 12) return false;
      m->objType = d[o]; m->size = rd(d + o + 1, 3); m->piece = d[o + 4]; m->nPieces = static_cast<uint16_t>(rd(d + o + 5, 2)); m->w = static_cast<uint16_t>(rd(d + o + 7, 2)); m->h = static_cast<uint16_t>(rd(d + o + 9, 2));
      m->nl = d[o + 11];
      if (m->nl > kMaxLayers || bn < o + 12 + 2 * static_cast<size_t>(m->nl) + 4) return false;
      for (int i = 0; i < m->nl; i++) m->layerEnds[i] = static_cast<uint16_t>(rd(d + o + 12 + 2 * i, 2));
      m->crc = rd(d + o + 12 + 2 * m->nl, 4);
      size_t e = o + 16 + 2 * static_cast<size_t>(m->nl);
      if (m->flags & F_POS) { if (bn < e + 7 || !detail::posValid(d + e)) return false; m->hasPos = true; memcpy(m->pos, d + e, 7); e += 7; }
      if (m->flags & F_OPT) { if (!detail::optsValid(d + e, bn - e)) return false; m->hasOpts = true; m->opts = d + e; m->optsLen = bn - e; }
      return true;
    }
    case ACCEPT: if (bn < 3) return false; m->layers = d[0]; m->window = d[1]; m->k = d[2]; return true;
    case DATA: if (bn < 2) return false; m->offset = static_cast<uint16_t>(rd(d, 2)); m->payload = d + 2; m->payloadLen = bn - 2; return true;
    case STATUS:
      if (bn < 14) return false;
      m->base = static_cast<uint16_t>(rd(d, 2)); m->bitmap = (static_cast<uint64_t>(rd(d + 2, 4)) << 32) | rd(d + 6, 4);
      m->rssi = static_cast<int8_t>(d[10]); m->snr = static_cast<int8_t>(d[11]); m->lossPct = d[12]; m->layersDone = d[13];
      return true;
    case DONE: {
      size_t o;
      if (!callAt(0, &o) || bn < o + 8) return false;
      m->layers = d[o]; m->nbytes = rd(d + o + 1, 3); m->crc = rd(d + o + 4, 4);
      return true;
    }
    case ABORT: if (bn < 1) return false; m->reason = d[0]; return true;
    default: return true;           // PARITY, ID, TEST e altri tipi: nessun campo da leggere qui
  }
}

}  // namespace img
}  // namespace v3
