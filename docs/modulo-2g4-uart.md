# Il modulo a 2,4 GHz con interfaccia seriale (Ebyte E28-2G4T27SX)

> **Principio (24/11/2026): si usa quello che si ha.** I moduli a 2,4 GHz che l'autore ha a disposizione sono gli **Ebyte E28-2G4T27SX** su scheda di prova USB (UART, 27 dBm). Il progetto li usa **così come sono**, in spirito radioamatoriale.
>
> **Stato: manuale letto (v1.0 del 19/08/2020, 20 pagine); strumenti scritti e provati sul PC con moduli finti. Nessuna prova con moduli veri.** Le cifre del manuale sono quelle del costruttore; il manuale ha **incongruenze** (punto 6). Tutto ciò che è marcato "da misurare" va provato.

## 1. Cosa dice il manuale
| Voce | Valore |
|---|---|
| Interfaccia | UART TTL a 3,3 V (per 5 V TTL "rischio di bruciarlo"), trasmissione trasparente, firmware interno |
| Chip | **SX1281** nell'introduzione, **SX1280** sulla copertina e nelle prodotti correlati |
| Modulazioni | **GFSK, FLRC, LoRa** |
| Frequenza | 2400-2500 MHz |
| Velocità d'aria | 1 kbps … 2 Mbps (1k, 5k, 10k, 50k, 100k, **1M FLRC**, **2M FSK**, più "autoadattiva" in trasmissione continua) |
| Potenza | **27 dBm** (26,5-27,5), regolabile: 27, 23, 20, 17 dBm |
| Sensibilità | **−130 / −132 / −134 dBm** (min/tip/max) a 115,2 kbps (nota del manuale) |
| Distanza | 5 km in condizioni ideali (antenna 5 dBi, altezza 2,5 m, 1 kbps) |
| Alimentazione | 2,3-5,5 V; **tipico 5,0 V, ≥ 5,0 V per la potenza piena** |
| Correnti | **TX 500 mA** (istantanea), RX 27 mA, spento 10 µA |
| **Pacchetto** | **121 byte** al massimo per pacchetto (modo a sotto-pacchetti); **221 byte** in trasmissione continua; buffer di **2048 byte** |
| **Potenza massima in ingresso (blocking)** | **10 dBm** (rischio di bruciare il ricevitore, raro a breve distanza) |
| Indirizzo e canale | Indirizzo a 16 bit; modo broadcast (0xFFFF o 0x0000) e monitor; trasmissione fissa (i primi 3 byte dei dati sono indirizzo alto, basso e canale) |
| LBT | **Ascolto prima di trasmettere** a scelta (bit di OPTION) |
| Misura distanza | "Ranging" **riservato**, non disponibile |

**Moduli fratelli con interfaccia SPI** (tabella dei prodotti correlati del manuale): E28-2G4M27S (27 dBm, 8 km), E28-2G4M20S (20 dBm, 6 km), E28-2G4M12S (12,5 dBm, 3 km), tutti indicati con SX1280. Sono la strada per il profilo 1 (radio controllata dal firmware con RadioLib) se un giorno servirà.

**Piedini:** 11 VCC, 12 AUX, 13 TXD, 14 RXD, 15 M1, 16 M0, 17 M2, 19 ANT, massa su 1, 8, 10, 18, 20, 21.

## 2. Modi di funzionamento (M2 M1 M0)
| Modo | M2 M1 M0 | Cosa fa |
|---|---|---|
| 0 Trasmissione | 1 0 0 | seriale e radio attive, trasmissione trasparente continua |
| 1 RSSI | 1 0 1 | come il modo 0 più **l'RSSI del canale ogni 100 ms** sulla seriale (il manuale scrive "formato HEX complement": da capire con una lettura vera): è la qualità del **canale**, non del singolo pacchetto |
| 2 Ranging | 1 1 0 | riservato |
| 3 Configurazione | 1 1 1 | radio spenta, **seriale fissa 9600 8N1** |
| 4 Basso consumo | 0 x x | consumo minimo |

Il cambio di modo vale solo con **AUX alto**; ci sono 2 ms di attesa dopo il fronte di salita di AUX.

## 3. Configurazione: i 6 byte `C0 ADDH ADDL SPED CHAN OPTION`
Esempio del manuale: `C0 00 00 13 18 04` = indirizzo 0000, 9600 8N1, 10 kbps d'aria, **canale 0x18 = 24 → 2424 MHz**, 27 dBm. I valori di fabbrica sono questi (la tabella dei valori di fabbrica del manuale scrive "canale 0x13" per errore: 0x13 è il byte SPED).

- **SPED:** bit 7-6 parità (8N1, 8O1, 8E1), bit 5-3 baud (1200, 4800, **9600**, 19200, 57600, 115200, 460800, 921600), bit 2-0 velocità d'aria (0 autoadattiva, 1 1k, 2 5k, **3 10k**, 4 50k, 5 100k, 6 1M FLRC, 7 2M FSK).
- **CHAN:** frequenza = 2400 + CHAN × passo; passo 1 MHz a 1k/5k/10k, **2 MHz a 50k/100k**, **3 MHz a 1M**, **5 MHz a 2M**. (In trasmissione continua il passo dipende dal baud: 2, 4 o 5 MHz.)
- **OPTION:** bit 7 trasmissione fissa, bit 3 **LBT**, bit 2 uscite push-pull, bit 1-0 potenza (27, 23, 20, 17 dBm).
- **Comandi in modo configurazione:** `C0…` scrive e salva, `C2…` scrive senza salvare, `C1 C1 C1` legge i parametri, `C3 C3 C3` legge la versione, `C4 C4 C4` riavvia.
- **Cambio di parametri senza ponticelli (pag. 11):** in trasmissione trasparente, tre byte `E2 E2 E2` (o `E3 E3 E3`) **aprono una finestra di 10 secondi** in cui un comando `C0…` cambia i parametri; **dopo 10 secondi** il modulo lavora con i nuovi. Questo permette di riconfigurare il modulo **dal computer o dall'ESP32 senza toccare M0/M1**, ma costa almeno **10 s**.

Tutto questo è codificato in [`tools/ebyte_e28.py`](../tools/ebyte_e28.py) e provato con l'esempio del manuale.

## 4. Cosa ne segue per il V3
**Profilo 2, "tubo opaco"** ([protocollo-immagini.md](protocollo-immagini.md), punto 7b). Nel BAND-SET: `profilo` = 2, `canale` = CHAN, `gradino` = il codice della velocità d'aria (1-7), `k` = pezzi per frame.

1. **Limite di 121 byte per pacchetto d'aria** (da misurare). Con l'incapsulamento di 5 byte il payload massimo è **116 byte** e il DATA porta **al massimo 6 pezzi** (6 + 96 byte): `k ≤ 6` sul profilo 2. Un frame più lungo verrebbe spezzato dal modulo.
2. **Trappola nei dati:** `E2 E2 E2` e `E3 E3 E3` aprirebbero la finestra di configurazione. L'incapsulamento ([`tools/uart_frame.py`](../tools/uart_frame.py)) usa un byte di **seme** che mescola i dati finché quelle sequenze non compaiono sul filo; provato su 3000 payload ricchi di E2 e E3.
3. **Cambio di canale o di velocità durante il trasferimento:** richiede la finestra E2 e **almeno 10 s**: il BAND-SET va mandato con ora UTC di partenza (`BAND_AT_UTC`) **almeno 15 s** dopo. Una riconfigurazione a ogni raffica non è praticabile: **un solo canale e una sola velocità per trasferimento**.
4. **Velocità reale:** il baud limita: a 115200 baud la seriale porta al massimo circa **92 kbit/s** (10 bit per byte), a 921600 circa 737 kbit/s; il manuale dice che in trasmissione continua il baud va da 1200 a 115200. La velocità d'aria va da 1 kbps a 2 Mbps: **da misurare** quanto si ottiene davvero.
5. **Qualità del collegamento:** il modulo **non dà l'RSSI di ogni pacchetto**. Nel modo 1 dà l'**RSSI del canale ogni 100 ms**: utile per **scegliere il canale meno occupato** dal Wi-Fi (scansione), da fare prima del BAND-SET. La soglia `M_banda` si valuta sul collegamento a 433 MHz, non sul modulo.
6. **LBT:** il modulo può ascoltare prima di trasmettere (bit di OPTION); da attivare per i trasferimenti, da verificare l'effetto sulla velocità (il manuale avverte che può disturbare la trasmissione continua).

## 5. L'applicazione: scheda "Modulo 2,4 GHz (UART)"
- **Configurazione del modulo:** metti il modulo in **modo 3** (M2 M1 M0 = 1 1 1), scegli la porta, **Leggi parametri** (`C1 C1 C1`) e **Scrivi parametri** (`C0…`, poi rilegge). Imposta lo **stesso canale e la stessa velocità d'aria** sui due moduli. Il canale mostra la frequenza in MHz.
- **Prova di collegamento:** rimetti il modulo in **modo 0** (M2 M1 M0 = 1 0 0), seriale con baud e parità scelti (9600 8N1 di fabbrica), due moduli su questo computer: **Prova A→B**. In alternativa **Solo invio** / **Solo ascolto** su due computer. La riga `UARTSUM` dà inviati, ricevuti, scartati dal CRC, perdita, kbit/s e latenza.
- Tutto provato **con moduli finti**; con i moduli veri vanno controllate l'attesa dopo il cambio di modo (AUX) e i tempi di risposta.

## 6. Incongruenze del manuale (da tenere presenti)
- Chip: SX1281 (introduzione) contro SX1280 (copertina, tabella dei prodotti correlati).
- La tabella dei prodotti correlati dà per questo modulo **12,5 dBm e 3 km** (riga copiata da un altro modello); la pagina dei parametri dà 27 dBm e 5 km.
- Le domande frequenti (FAQ) parlano di alimentazione "2,0-3,6 V; sopra 3,6 V danneggia": è in contrasto con i 2,3-5,5 V dei parametri. **Con la scheda di prova USB (5 V) vale la scheda tecnica dei parametri**; verifica sulla scheda di prova.
- Il comando di lettura versione cita "M0=0, M1=0, M2=0" invece del modo configurazione: usare il modo 3.
- La nota "sensibilità a 115,2 kbps" è probabilmente la velocità del baud, non dell'aria.

## 7. Prudenze di laboratorio (limiti tecnici, non di normativa)
- **Blocking 10 dBm:** a 27 dBm il trasmettitore può danneggiare il ricevitore dell'altro modulo se sono vicini. A banco: **attenuatore di almeno 20-30 dB in serie** e/o potenza ridotta (17 dBm) e modulo separato.
- **Corrente di TX 500 mA** istantanei: l'USB di un computer può non bastare; usare un alimentatore o un hub alimentato (alimentazione stabile, ≥ 5,0 V).
- **Antenna sempre collegata** prima di trasmettere.
- Frequenza e potenza: vale la nota in [regole-radioamatoriali.md](regole-radioamatoriali.md).

## 8. Da fare con i moduli veri
1. Leggere la configurazione di fabbrica (`C1 C1 C1`) e confrontarla con il manuale.
2. Prova A→B a 10 kbps (valore di fabbrica), poi a 100k, 1M, 2M: **kbit/s, perdita, latenza**, con 20-30 dB di attenuazione.
3. Verificare il **pacchetto massimo** (121 byte) e cosa succede con frame più lunghi.
4. Provare la **finestra E2**: durata, effetto del cambio di canale, e se i dati con E2 E2 E2 la attivano davvero.
5. **Scansione RSSI** (modo 1) a casa tua: quanto è occupata la banda dal Wi-Fi.
6. **Portata** e perdita contro distanza.
7. Tempo di cambio di modo con AUX.
