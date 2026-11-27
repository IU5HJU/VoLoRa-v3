// Pin delle radio, ripresi dalla v2 (VoLoRa v0.1.0-rc.1: src/board_pins_t3_v161.h e src/board_pins_tbeam_v12.h),
// a loro volta dal repository ufficiale LILYGO. Nel firmware di misura la microSD e l'audio non sono usati.
#pragma once

namespace pins {
constexpr int kRadioSclk = 5;
constexpr int kRadioMiso = 19;
constexpr int kRadioMosi = 27;
constexpr int kRadioCs = 18;
constexpr int kRadioDio0 = 26;  // SX1278: TxDone / RxDone (anche per l'oscilloscopio)
constexpr int kRadioRst = 23;
constexpr int kRadioDio1 = 33;  // SX1262: interrupt (TxDone / RxDone)
constexpr int kRadioDio2 = 32;
constexpr int kRadioBusy = kRadioDio2;  // SX1262: BUSY (come nella v2)
constexpr int kOledSda = 21;            // OLED SSD1306 (T3: a bordo; T-Beam: esterno facoltativo) e PMU AXP2101 della T-Beam
constexpr int kOledScl = 22;
constexpr int kGpsRx = 34;              // T-Beam V1.2: ingresso dell'ESP32 (TX del GPS u-blox)
constexpr int kGpsTx = 12;              // T-Beam V1.2: uscita dell'ESP32 (RX del GPS); sulla T3 non c'e' il GPS
// Tasti, come la v2 (board_pins_*.h): PTT = T3 GPIO0 (BOOT) / T-Beam GPIO38 (tasto utente, pull-up sulla scheda); volume = pulsante esterno facoltativo fra GPIO15 e massa (pull-up interno).
#if defined(BOARD_TBEAM_V12)
constexpr int kPtt = 38;
constexpr bool kPttHasInternalPullup = false;
#else
constexpr int kPtt = 0;
constexpr bool kPttHasInternalPullup = true;
#endif
constexpr int kVolume = 15;             // GPIO15 e' un pin di strapping: come nella v2, se il pulsante non c'e' resta alto e non fa nulla
constexpr int kBatteryAdc = 35;         // T3: tensione della batteria (partitore 100k/100k); sulla T-Beam e' l'interrupt del PMU e la batteria si legge dall'AXP2101
}  // namespace pins

// Tensione del TCXO sul DIO3 dell'SX1262 (come la v2: 1,6 V; se la radio non parte con un errore, provare 0 con -DMISURA_TCXO_V=0)
#ifndef MISURA_TCXO_V
#define MISURA_TCXO_V 1.6f
#endif
// Parola di sincronismo LoRa: diversa da quella della v2, per non disturbare ne' farsi disturbare da stazioni VoLoRa v2 vicine.
#define MISURA_SYNC 0x5D
