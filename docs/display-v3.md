# Display OLED della scheda mobile V3

**Stato:** modello delle schermate **provato sul PC** (`firmware/v3/tests/test_display.cpp`, 61 controlli); disegno su OLED (`display_oled.h`) **compilato dalla CI, mai visto su uno schermo vero**. Le schermate qui sotto sono il testo prodotto dalla prova, non foto.

Il display è quello della **v2** ([docs/display.md della v2](../third_party/VoLoRa-v2/docs/display.md), `src/ui.cpp`), con le stesse regole: SSD1306 128×64 (T3: a bordo, SDA 21 / SCL 22, indirizzo 0x3C poi 0x3D; T-Beam: esterno e facoltativo, se non c'è tutto resta muto), riga 1 con nominativo e frequenza, linea a y=10, **riga grande a y=16** (10 caratteri, oltre passa al testo piccolo), **righe piccole a y=38 e y=47** (21 caratteri, mai a capo), ultima riga a y=56 con **la batteria a destra** nel formato `(Batt=4.12V)` e in negativo sotto 3,40 V, barra di avanzamento sulla riga 47, avviso a tempo sulla riga 38, schermata di avvio con `fw <versione>`.

## Cosa cambia rispetto alla v2
- **Niente PTT, niente volume:** la scheda V3 si comanda dal telefono. L'ultima riga a sinistra dice **gradino e potenza** (`R10 17dBm`) invece di `Vol 7/10`.
- **Lettera in alto a destra:** non è il profilo (S/R/M/D/T) ma il **livello di potenza**: **V** normale (+17 dBm), **B** BOOST (+20 dBm), **I** IOF MODE (+22 dBm, dedicato a IZ5IOF Andrea). Come la **T** della v2 durante MeshCom, serve a vedere a colpo d'occhio che si sta usando una modalità a rischio.
- **Schermata di collegamento:** senza telefono collegato la scheda non può né mandare né accettare oggetti, quindi mostra come collegarlo: con il **Wi-Fi della scheda** (firmware `mobile_*`) la rete `WiFi VoLoRa-<NOMINATIVO>`, la **password a 8 cifre in carattere doppio e in grassetto** (come la schermata Wi-Fi della v2) e l'indirizzo `http://192.168.4.1`; con il Bluetooth il **codice a 6 cifre** e il nome `VoLoRa-V3 <NOMINATIVO>`. Non serve più il computer per leggere la password o il codice.
- **Avvisi a tempo (4 s):** `CONSEGNATO`, `INVIO FALLITO`, `ANNULLATO`, `MANCA LA POSIZIONE`, `IMPOSTA NOMINATIVO`, `OCCUPATO`.
- **Comando seriale** `DISPLAY 0` / `DISPLAY 1`: lo spegne e lo riaccende (disegnare costa circa 25 ms; durante una prova radio serrata conviene spegnerlo).
- Il ridisegno avviene solo se la schermata cambia, al massimo 10 volte al secondo, a 4 Hz durante un invio o una ricezione (come la v2).

## Le schermate
```
Avvio (1,8 s)                  A riposo                        Senza telefono
| IU5HJU                |      | IU5HJU 433.700MHz     |V      | IU5HJU 433.700MHz     |V
| AVVIO       (grande)  |      | ASCOLTO     (grande)  |       | Collega il telefono   |
| fw v0.1.0-rc.1        |      | Telefono collegato    |       | [917558]   (doppio)   |
                               | Pos JN53ab            |       | VoLoRa-V3 IU5HJU      |
                               | R10 17dBm (Batt=4.12V)|       | R10 17dBm (Batt=4.12V)|

Invio dal telefono             Ricezione dalla radio           Ultimo ricevuto (20 s)
| IU5HJU 433.700MHz     |V     | IU5HJU 433.700MHz     |V      | IU5HJU 433.700MHz     |V
| INVIO       (grande)  |      | RX IZ5FSN   (grande)  |       | ASCOLTO     (grande)  |
| Invio immagine 40%    |      | Ricevo messaggio 63%  |       | Ultimo IZ5FSN         |
| [barra ######      ]  |      | RSSI -97  SNR 7.5     |       | 5000 byte CRC ok      |
| R7 17dBm  (Batt=4.12V)|      | R7 17dBm  (Batt=4.12V)|       | R7 17dBm  (Batt=4.12V)|
```
Altre: `SOLO RX / Imposta il nominativo` (senza nominativo, con il codice Bluetooth sulla riga 47), `ERRORE / radio` (la radio non parte), `Cerco il collegamento` (collegamento perso durante l'invio), nominativo di 8 caratteri (`RX IU5HJU/P`: la riga grande scende al testo piccolo, come la v2).

## Come affiancare gli elementi della v2 e quelli del V3: esempi (da scegliere con l'autore)
Il V3 mobile non ha PTT né volume, quindi due elementi della v2 non hanno più il loro significato: la **lettera del profilo** (S/R/M/D/T) e **`Vol 7/10`**. Al loro posto ho messo **la lettera V/B/I** (potenza normale, BOOST, IOF MODE) e **gradino e potenza** (`R10 17dBm`). L'autore ha chiesto (27/11/2026) di **aggiungere gli elementi V3 a quelli della v2** e, se serve spazio, di vedere degli esempi: ![esempi](images/display-v3-esempi.png)
Tre varianti sullo stesso schermo (a riposo, invio, ricezione): **A** come adesso; **B** la v2 intatta (lettera S e `Vol 7/10`) con il V3 sulla riga libera, che a riposo basta ma durante l'invio con la barra non c'è più posto (il gradino non si vede); **C** senza lettera e senza `Vol`. Nota: con `R10 17dBm` (9 caratteri) e la batteria (12) la riga è piena e le due scritte si toccano. È un **mockup** disegnato con le coordinate della v2 (`tools/render_display_v3.py`, che usa lo stesso modello di Adafruit_GFX della v2), non una foto.

## GPS e distanza (T-Beam)
Come la v2: a riposo la riga 47 dice `GPS fix, 8 satelliti` oppure `GPS cerco satelliti` (con il GPS acceso, `GPS ON` sulla seriale); durante la ricezione `12.3km  RSSI -97`; dopo `Ultimo IZ5FSN 12.3km` (la distanza si aggiunge solo se la riga resta nei 21 caratteri). Vedi [firmware-v3.md](firmware-v3.md).

## Batteria
Come la v2 (`src/battery.cpp`), lettura non bloccante: **T-Beam** dal chip AXP2101 ogni 2 s (`(Batt=--)` se la batteria non c'è); **T3** ADC su GPIO35 con partitore 100k/100k, calibrazione del chip, media di 16 letture (una ogni 50 ms) e media lenta di circa 2,5 s (senza batteria e con USB si legge la linea del caricatore, che oscilla).

## Versione del firmware
All'accensione `fw <versione>` come la v2: viene da `git describe --tags --always --dirty` (script `firmware/v3/tools/git_version.py`, copia di quello della v2); se è più lunga di 18 caratteri si mostra la coda, che ha il codice del commit. Sulla pagina di installazione compare la stessa versione.

## Dove sta nel codice
| Cosa | File |
|---|---|
| Modello delle schermate (testi, regole dei 21 e 10 caratteri, lettere, glifi) | `firmware/v3/src/display_model.h` |
| Disegno sull'OLED (Adafruit SSD1306, stesse coordinate della v2) | `firmware/v3/src/display_oled.h` |
| Batteria: formato, soglia, medie | `firmware/v3/src/battery_info.h`, `battery_board.h`, `pmu.h` |
| Collegamento allo stato della scheda | `firmware/v3/src/main_mobile.cpp` (`updateDisplay`) |
| Prove | `firmware/v3/tests/test_display.cpp` |

## Cosa NON è fatto
- **Non visto su un OLED vero:** coordinate e testi vengono dalla v2, ma nessuno ha ancora guardato una schermata V3 su uno schermo. Il costo di ridisegno (25 ms) con la radio in ricezione serrata va misurato.
- Il display non c'è nel firmware **a banco** (`bench_*`) e nel **ponte simulato** (`ble_sim_*`).
- Niente schermate di menu né di MeshCom, Wi-Fi, prova di potenza, casella messaggi: nel V3 mobile non esistono ancora le funzioni (vedi il confronto con la v2 in [firmware-v3.md](firmware-v3.md)).
