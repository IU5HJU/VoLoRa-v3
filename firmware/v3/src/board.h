// Pin delle radio, ripresi dalla v2 (VoLoRa v0.1.0-rc.1: src/board_pins_t3_v161.h e src/board_pins_tbeam_v12.h),
// a loro volta dal repository ufficiale LILYGO. Nel firmware di misura la microSD e l'audio non sono usati.
#pragma once

namespace pins {
#if defined(BOARD_HELTEC_V3)
// Heltec WiFi LoRa 32 V3 (ESP32-S3 + SX1262, OLED 0,96" 128x64). Pin dal repository Heltec-Aaron-Lee/WiFi_Kit_series, variants/heltec_wifi_lora_32_V3/pins_arduino.h:
// SS 8, SCK 9, MOSI 10, MISO 11, RST_LoRa 12, BUSY_LoRa 13, DIO1 14 (nel file "DIO0"), Vext 36, OLED SDA 17 / SCL 18 / RST 21. STUDIO: mai provato su una scheda.
constexpr int kRadioSclk = 9;
constexpr int kRadioMiso = 11;
constexpr int kRadioMosi = 10;
constexpr int kRadioCs = 8;
constexpr int kRadioDio0 = -1;          // nessun SX1278 su questa scheda
constexpr int kRadioRst = 12;
constexpr int kRadioDio1 = 14;          // SX1262: interrupt (TxDone / RxDone)
constexpr int kRadioDio2 = -1;
constexpr int kRadioBusy = 13;          // SX1262: BUSY
constexpr int kOledSda = 17;
constexpr int kOledScl = 18;
constexpr int kOledRst = 21;            // reset dell'OLED: impulso basso all'avvio (pmu.h)
constexpr int kVext = 36;               // alimentazione dell'OLED e del 3V3 esterno: attiva a livello BASSO (pmu.h)
constexpr int kGpsRx = -1;              // nessun GPS a bordo
constexpr int kGpsTx = -1;
#else
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
#endif
// Tasti, come la v2 (board_pins_*.h): PTT = T3 GPIO0 (BOOT) / T-Beam GPIO38 (tasto utente, pull-up sulla scheda); volume = pulsante esterno facoltativo fra GPIO15 e massa (pull-up interno).
#if defined(BOARD_HELTEC_V3)
constexpr int kPtt = 0;                 // tasto PRG (GPIO0), come il BOOT della T3
constexpr bool kPttHasInternalPullup = true;
#elif defined(BOARD_TBEAM_V12)
constexpr int kPtt = 38;
constexpr bool kPttHasInternalPullup = false;
#else
constexpr int kPtt = 0;
constexpr bool kPttHasInternalPullup = true;
#endif
#if defined(BOARD_HELTEC_V3)
constexpr int kVolume = 2;              // pulsante esterno facoltativo fra GPIO2 (piedino del connettore, nessuna funzione a bordo) e massa: scelta di lavoro, da confermare
#else
constexpr int kVolume = 15;             // GPIO15 e' un pin di strapping: come nella v2, se il pulsante non c'e' resta alto e non fa nulla
#endif
#if defined(BOARD_HELTEC_V3)
// Batteria: ADC su GPIO1 con partitore 390k/100k (fattore 4,9) abilitato dal GPIO37 a livello BASSO. VALORI DA CONFERMARE sullo schema della scheda: non sono nel repository Heltec letto; se la tensione mostrata e' sbagliata si correggono qui.
constexpr int kBatteryAdc = 1;
constexpr int kBatteryCtrl = 37;
constexpr float kBatteryDivider = 4.9f;
#else
constexpr int kBatteryAdc = 35;         // T3: tensione della batteria (partitore 100k/100k); sulla T-Beam e' l'interrupt del PMU e la batteria si legge dall'AXP2101
constexpr int kBatteryCtrl = -1;
constexpr float kBatteryDivider = 2.0f;
#endif
}  // namespace pins

// Tensione del TCXO sul DIO3 dell'SX1262 (come la v2: 1,6 V; se la radio non parte con un errore, provare 0 con -DMISURA_TCXO_V=0).
// Heltec WiFi LoRa 32 V3: 1,8 V (valore usato dai progetti che la supportano, non nel repository Heltec letto: DA CONFERMARE sulla scheda).
#ifndef MISURA_TCXO_V
#if defined(BOARD_HELTEC_V3)
#define MISURA_TCXO_V 1.8f
#else
#define MISURA_TCXO_V 1.6f
#endif
#endif
// DIO2 comanda l'interruttore d'antenna dell'SX1262 (Heltec V3: si'; T-Beam: no, ha i suoi pin)
#if defined(BOARD_HELTEC_V3)
#define VL3_DIO2_RF_SWITCH 1
#endif
// Parola di sincronismo LoRa: diversa da quella della v2, per non disturbare ne' farsi disturbare da stazioni VoLoRa v2 vicine.
#define MISURA_SYNC 0x5D
