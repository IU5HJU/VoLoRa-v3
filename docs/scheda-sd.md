# La microSD della T3

> Fonte: solo la documentazione del repository VoLoRa (v2), `docs/pinout.md`, `docs/firmware.md`, `platformio.ini`. Il resto è ragionamento da verificare sulla scheda.

## Cosa dice la v2
- La **T3 V1.6.1** (ESP32-PICO-D4) ha **4 MB di flash e nessuna PSRAM**. Il firmware v2 usa la tabella `min_spiffs` (programma fino a 1,875 MB).
- Lo slot microSD usa questi pin: **CS 13, MOSI 15, MISO 2, SCK 14**.
- Nella v2 quei pin sono già occupati o riservati:

| Pin | Slot microSD | Uso nella v2 |
|---|---|---|
| IO13 | CS | WS dell'I2S (microfono e amplificatore) |
| IO14 | SCK | BCLK dell'I2S (microfono e amplificatore) |
| IO15 | MOSI | pulsante del volume (opzionale) |
| IO2 | MISO | seriale TX verso la RX/TX del ripetitore |

- Per questo la v2 dice di **togliere la microSD** per caricare il firmware e per le prove: lo slot funziona solo se quei pin sono liberi.
- La **T-Beam V1.2** non ha lo slot microSD nei documenti della v2 (ha 8 MB di PSRAM, non usata).
- Nella v2 il messaggio vocale ricevuto sta in RAM, **uno solo alla volta**.

## Perché nella V3 può convenire
Con **firmware specializzati** la collisione dei pin sparisce nei ruoli che non usano l'audio:

| Ruolo V3 | Pin IO13, IO14, IO15, IO2 | SD utilizzabile? |
|---|---|---|
| Nodo immagini (T3) | nessun audio, nessun pulsante del volume | **sì** |
| Nodo Internet | nessun audio | **sì**, per registro e coda |
| Nodo voce/testo | IO13 e IO14 servono all'I2S | **no** (come nella v2) |
| Ripetitore RX/TX | IO2 serve alla seriale RX-TX | **no**, se si tiene il cablaggio v2 |

Utilità per il **nodo immagini** (la T3 non ha PSRAM, quindi la RAM è poca):
1. **Immagini ricevute e frammenti:** un'immagine a livelli e a pacchetti numerati si assembla su file, e un trasferimento interrotto si riprende dopo uno spegnimento.
2. **Coda di invio:** immagini pronte, scelte dal PC o da altri dispositivi.
3. **Archivio** delle immagini ricevute con nominativo, ora, modo radio, RSSI e SNR.
4. **Registro delle prove:** invece della seriale, per le misure di campo (fase 5).
5. **Più livelli di una stessa immagine** già preparati a risoluzioni diverse, da cui la negoziazione sceglie in base al modo concordato.

## Cautele da verificare
- **Caricamento del firmware:** la v2 chiede di togliere la microSD. Con l'SD usata, serve verificare se il caricamento da cavo e l'aggiornamento dalla pagina funzionano con la scheda inserita (strapping di IO2 e pin dello slot).
- **Alimentazione e corrente:** la scrittura sulla microSD assorbe corrente mentre la radio trasmette; da misurare.
- **Rumore:** SPI della scheda vicino al modulo LoRa e al GPS/antenna; da verificare con la sensibilità in ricezione.
- **Velocità reale:** a 300 kbit/s in FSK il flusso verso la scheda è basso (circa 37 kbyte/s), ma le scritture a blocchi su SD possono bloccare per decine di ms: serve un buffer in RAM.
- **Scheda assente:** il firmware deve funzionare lo stesso senza microSD (immagini solo in RAM, più piccole).
- **T-Beam:** senza slot, il nodo immagini su T-Beam deve fare a meno della SD (ha PSRAM, che nella v2 non è usata).

## Decisione proposta
La SD è **opzionale** nel nodo immagini della T3: se c'è si usa per frammenti, coda e archivio; se manca si lavora in RAM con immagini più piccole. Nei ruoli con audio o con il filo seriale del ripetitore **non si usa**.
