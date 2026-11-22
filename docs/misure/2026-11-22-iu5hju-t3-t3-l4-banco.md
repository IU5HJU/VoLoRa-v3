# Prima prova a due schede (22/11/2026, IU5HJU)

Due LILYGO LoRa32 T3 V1.6.1 (SX1278), firmware di misura 0.1.0, collegate allo stesso computer (applicazione, scheda Misure). Schede a 1-2 m, antenne a 433 MHz, **nessun attenuatore** (attenuazione 0 dB), modo **L4** (LoRa BW 250 kHz, SF7, CR 4/5), 433,475 MHz, +2 dBm, pacchetti da 255 byte, 200 pacchetti ogni 300 ms.
Dati ricavati dagli screenshot dell'operatore (il CSV `2026-11-22-IU5HJU.csv` è sul suo computer).

| Verso | Inviati | Ricevuti | Rovinati | Perdita | RSSI | SNR | Errore di frequenza | Tempo in aria misurato / calcolato |
|---|---|---|---|---|---|---|---|---|
| A → B | 200 | 200 | 0 | 0 % | -47,2 dBm | 10,0 dB | **+1595 Hz** | 202 180 µs / 199 808 µs |
| B → A | 200 | 199 | 1 | 0,5 % | -42,4 dBm | 10,2 dB | **-1514 Hz** | 202 187 µs / 199 808 µs |

## Cosa dicono
1. **Il collegamento fra due schede vere funziona** nei due versi, con tutta la catena (firmware, applicazione, monitor, tabella e CSV).
2. **Il tempo in aria calcolato è confermato:** misurato +1,2 % sul calcolato in entrambe le prove (circa 2,4 ms di sovraccarico dal caricamento del FIFO via SPI). La formula di `docs/scala-modi.md` è corretta per L4.
3. **Errore di frequenza fra le due schede: circa 1,55 kHz, cioè 3,6 ppm.** Il segno si inverte con il verso (+1595 Hz con A che trasmette, -1514 Hz con B che trasmette), come deve succedere per un offset fisso fra i due quarzi. È il primo dato per la misura M6 (deriva del quarzo). Rispetto alla banda LoRa, 1,55 kHz è l'1,2 % di 125 kHz, il 5 % di 31,25 kHz, il **20 % di 7,8 kHz**: i gradini più stretti del protocollo immagini (R13-R14) richiederanno la correzione automatica della frequenza, usando l'errore misurato sul primo pacchetto.
4. **Un pacchetto su 200 rovinato nel verso B → A** (bad=1, ricevuto con il controllo CRC della radio in errore), con segnale molto forte (-42 dBm, il più forte dei due). **Ipotesi da verificare:** saturazione del ricevitore, o un disturbo. Da ripetere con 20-30 dB di attenuazione.
5. **SNR di circa 10 dB** in entrambe: con un segnale di -42 / -47 dBm l'SNR vero sarebbe molto più alto; sembra che la lettura dell'SX1278 non salga oltre una decina di dB (da verificare aumentando l'attenuazione).
6. L'RSSI è diverso di 5 dB fra i due versi (-47,2 e -42,4 dBm): antenne, cavi e posizione, non indagato.

## Da fare
- Ripetere B → A con 20-30 dB di attenuazione (la perdita scompare?).
- Ripetere più volte per vedere se la perdita dello 0,5 % è casuale.
- Modo L2 (SF6) sulla T3, un modo FSK (con la nota sul pacchetto a 64 byte) e la portante CW.
