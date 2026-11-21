# Limiti delle radio SX1278 e SX1262 (fase 0)

> **Fonti, e cosa NON è stato verificato.** I datasheet Semtech non erano raggiungibili da questa sessione. I valori sotto vengono da fonti **secondarie**: il codice di RadioLib incluso nel repository [LilyGo-LoRa-Series](https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series) (i controlli sui parametri rispecchiano i limiti dei chip) e le tabelle di quel repository (`docs/en/t_beam/t_beam_hw.md`). Dove una cifra è calcolata, la formula è indicata. **Prima di fissare un'architettura vanno confermati sui datasheet Semtech** (SX1276/77/78/79 e SX1261/2): sensibilità, tabelle di RxBw, PA, correnti.

## Frequenze

| | SX1278 (T3 V1.6.1, T-Beam V1.2) | SX1262 (T-Beam V1.2 con SX1262) |
|---|---|---|
| Campo di sintonia | 137-175 MHz e 395-525 MHz (RadioLib; il datasheet dà 410-525 per la banda alta, la libreria annota che funziona fino a circa 395) | 150-960 MHz |
| **430-440 MHz** | dentro il campo | dentro il campo; l'SX1262 ricalibra l'immagine quando la frequenza cambia di una certa soglia (da documentare) |

Le **schede** hanno filtri e antenna per i 433 MHz: il rendimento a 430 e 440 MHz va misurato (punto aperto 7).

## FSK / GFSK

| | SX1278 | SX1262 |
|---|---|---|
| Bit rate | 0,5-300 kbit/s in RadioLib (datasheet: 1,2-300; la libreria annota che 0,512 funziona) | 0,6-300 kbit/s |
| Deviazione di frequenza | fino a 200 kHz, con deviazione + bit rate/2 ≤ 250 kHz | 0,6-200 kHz |
| Dimensione massima del pacchetto | **64 byte** in FSK: è il FIFO (RadioLib cita il datasheet Rev. 7, pagina 66) | 255 byte |
| Banda di ricezione (RxBw) | tabella da leggere nel datasheet | tabella da leggere nel datasheet |

Conseguenze da valutare:
- Sull'**SX1278** un pacchetto FSK più lungo di 64 byte richiede di riempire e svuotare il FIFO durante la trasmissione e la ricezione, con latenza stretta sul bus SPI: più difficile ad alto bit rate.
- Con deviazione 200 kHz e 300 kbit/s l'occupazione è dell'ordine di mezzo MHz; non c'è un limite di banda (decisione del 21/11/2026).

## LoRa

| | SX1278 | SX1262 |
|---|---|---|
| Bande | 7,8; 10,4; 15,6; 20,8; 31,25; 41,7; 62,5; 125; 250; **500 kHz** | fino a 500 kHz (RadioLib accetta 0-510 kHz) |
| Spreading factor | **6-12** | **5-12** |
| Coding rate | 4/5-4/8 | 4/5-4/8 |
| Pacchetto massimo | 255 byte | 255 byte |

**Velocità LoRa massima, calcolata** con `bit rate = SF · BW / 2^SF · 4/(4+CR)` (CR 4/5):
- SX1278, SF6, BW 500 kHz: 6 · 500000 / 64 · 0,8 = **37,5 kbit/s**.
- SX1262, SF5, BW 500 kHz: 5 · 500000 / 32 · 0,8 = **62,5 kbit/s**.

**Discrepanza:** la tabella del repository LilyGO dà 62,5 kbit/s anche per l'SX1278, ma con SF minimo 6 il massimo è 37,5 kbit/s (coerente con la tabella del datasheet citata da una copia di terzi). Per l'SX1278 si usa 37,5.

## Potenza
- SX1262: fino a +22 dBm (fonte: pagine commerciali Semtech). Per l'SX1278 la potenza (RFO e PA_BOOST) va letta nel datasheet. Nessun dato sulle schede (filtri, adattamento).

## Cosa resta da leggere nei datasheet Semtech
1. Sensibilità per bit rate e deviazione in FSK, e per SF e banda in LoRa, a 433 MHz.
2. Tabelle RxBw dell'FSK.
3. Potenza e correnti, PA dell'SX1278.
4. Tolleranza di frequenza e uso del TCXO (a banda stretta e SF alto la deriva del quarzo conta).
5. Comportamento della banda LoRa a 500 kHz alle frequenze basse (RadioLib e datasheet hanno note da confrontare).
