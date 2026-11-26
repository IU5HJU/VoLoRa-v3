// Stime di tempo del protocollo immagini V3 (porta in C++ di tools/protocollo_immagini.py e scala_modi.lora_toa). Nessuna dipendenza dalla scheda: gira sul PC.
// Provata contro i valori del riferimento Python (tests/test_conformance.cpp con tests/vettori/estimate.txt). Stime dello studio, NON misure.
#pragma once
#include <cmath>
#include <cstdint>

namespace v3 {

struct Rung {
  bool lora;
  double a;   // LoRa: banda in kHz; FSK: bit rate in kbit/s
  double b;   // LoRa: spreading factor; FSK: deviazione in kHz
};
constexpr int kRungCount = 15;
// R0-R2 FSK, R3-R14 LoRa (docs/protocollo-immagini.md, punto 3)
constexpr Rung kRungs[kRungCount] = {{false, 150.0, 50.0}, {false, 100.0, 50.0}, {false, 50.0, 25.0}, {true, 500.0, 6}, {true, 500.0, 7}, {true, 250.0, 7}, {true, 250.0, 8}, {true, 250.0, 9},
                                     {true, 125.0, 9},     {true, 125.0, 10},    {true, 125.0, 12},   {true, 62.5, 12}, {true, 31.25, 12}, {true, 15.6, 12}, {true, 7.8, 12}};
constexpr int kRendezvous = 10;      // gradino di incontro: LoRa 125 kHz / SF12

constexpr int kDataHeader = 6, kStatusBytes = 18, kFskPhyBytes = 9, kSx1278FskFrameMax = 64, kFrameMax = 255, kMinChunk = 32, kPiece = 16;
constexpr double kChunkAirtimeTarget = 3.0;

// Tempo in aria LoRa in secondi (formula Semtech, CR 4/5, intestazione esplicita, CRC, preambolo 8).
inline double loraToa(int sf, double bwKhz, int payload, int preamble = 8) {
  const double ts = std::pow(2.0, sf) / (bwKhz * 1000.0);
  const int de = ts > 0.016 ? 1 : 0;
  double n = std::ceil((8.0 * payload - 4.0 * sf + 28.0 + 16.0) / (4.0 * (sf - 2 * de))) * 5.0;
  if (n < 0) n = 0;
  n += 8.0;
  return (preamble + (sf < 7 ? 6.25 : 4.25)) * ts + n * ts;
}

inline double frameAirtimeS(int rung, int frameBytes) {
  const Rung& r = kRungs[rung];
  if (r.lora) return loraToa(static_cast<int>(r.b), r.a, frameBytes);
  return (kFskPhyBytes + frameBytes) * 8.0 / (r.a * 1000.0);
}

inline int maxFrame(int rung, bool sx1262) { return (!kRungs[rung].lora && !sx1262) ? kSx1278FskFrameMax : kFrameMax; }

inline int chunkSize(int rung, bool sx1262) {
  const int top = (maxFrame(rung, sx1262) - kDataHeader) / kPiece * kPiece;
  for (int c = top; c >= kMinChunk; c -= kPiece)
    if (frameAirtimeS(rung, c + kDataHeader) <= kChunkAirtimeTarget) return c;
  return top < kMinChunk ? top : kMinChunk;
}

// Sensibilita' stimata dello studio (docs/scala-modi.md): LoRa dalle formule Semtech, FSK con banda = bit rate + 2 x deviazione e SNR 12 dB; cifra di rumore 6 dB.
inline double sensitivityDbm(int rung) {
  const Rung& r = kRungs[rung];
  static const double snr[13] = {0, 0, 0, 0, 0, -2.5, -5.0, -7.5, -10.0, -12.5, -15.0, -17.5, -20.0};
  if (r.lora) return -174 + 10 * std::log10(r.a * 1000) + 6.0 + snr[static_cast<int>(r.b)];
  return -174 + 10 * std::log10((r.a + 2 * r.b) * 1000) + 6.0 + 12;
}
inline int piecesPerFrame(int rung, bool sx1262) { return chunkSize(rung, sx1262) / kPiece; }

// Tempo stimato per trasferire nbytes: frame, ritrasmissioni (perdita media), una STATUS per finestra e i tempi di commutazione.
inline double estimateSeconds(uint32_t nbytes, int rung, bool sx1262, double loss = 0.05, int window = 16, double guardS = 0.15) {
  const int c = chunkSize(rung, sx1262);
  const double frames = std::ceil(static_cast<double>(nbytes) / c);
  const double tx = frames * frameAirtimeS(rung, c + kDataHeader) / (1.0 - loss);
  const double windows = std::ceil(frames / window);
  const double status = windows * (frameAirtimeS(rung, kStatusBytes) + 2 * guardS);
  return tx + status;
}

}  // namespace v3
