# Protocollo immagini V3 (bozza v0.1)

> **Stato: bozza di progetto, nessuna implementazione.** Le cifre di sensibilità sono le **stime** di [scala-modi.md](scala-modi.md), non misure; i tempi sono calcolati da [`tools/protocollo_immagini.py`](../tools/protocollo_immagini.py). Le decisioni da prendere dopo le misure della fase 1 sono elencate al punto 12. Il lavoro sulla v2 non cambia: i frame V3 sono scartati dalle stazioni v2 (punto 2).

## 1. Scopo e principi
Trasferire **immagini** fra due stazioni con le massime prestazioni della radio (LoRa e FSK), **negoziando** modi più lenti e robusti quando il collegamento peggiora, fino ai casi estremi, e **riducendo l'immagine** quando il tempo non basta.

1. **Il nodo trasporta byte, non conosce l'immagine.** La codifica (livelli, ridimensionamento, qualità) si fa **sul PC o sul telefono**; l'ESP32 riceve e manda un oggetto fatto di *pezzi* numerati. Così il firmware resta piccolo (la T3 ha 520 KB di RAM e nessuna PSRAM) e il codec si cambia senza toccare la radio.
2. **L'oggetto è a livelli.** Il primo livello è una versione piccola e già utile, ogni livello successivo la migliora. L'immagine si può interrompere a un confine di livello e restare visibile.
3. **Il collegamento è sempre recuperabile.** Ogni stazione che perde il filo torna al **gradino di incontro** (R10, LoRa 125 kHz / SF12) dove si trovano anche i casi peggiori.
4. **Ritrasmissione selettiva.** Si mandano finestre di pezzi, il ricevitore risponde con una mappa dei pezzi mancanti, si ripetono solo quelli.
5. **Voce e testo restano nel protocollo v2**; questo protocollo è separato e non li sostituisce.

## 2. Compatibilità con la v2
La v2 apre ogni pacchetto con un byte il cui nibble alto è la **versione** (2) e il basso il **modo** (1-7, 15) (`docs/protocollo.md` della v2). Il ricevitore v2 scarta ogni pacchetto con versione diversa da 2 (`lib/voicecore/packet.cpp`, riga 108). **I frame V3 usano versione 3**: `byte0 = 0x30 | tipo`. Una stazione v2 non li decodifica e non ne è disturbata, a parte l'occupazione del canale (che si evita con un canale proprio e con il CAD prima di trasmettere, come nella v2). Nelle fasi di prova i frame di test `tipo 15` servono al firmware di misura.

## 3. La scala dei gradini
Quindici gradini, dal più veloce al più robusto (R0-R14). I modi sono quelli di [scala-modi.md](scala-modi.md); R3-R14 sono LoRa CR 4/5, R0-R2 FSK.

| Gradino | Modo | Note |
|---|---|---|
| R0-R2 | FSK 150, 100, 50 kbit/s (deviazione 50, 50, 25 kHz) | per collegamenti forti; banda di ricezione entro 250 kHz (SX1278), oltre solo SX1262 |
| R3 | LoRa BW 500 kHz / SF6 | l'SX1278 usa l'intestazione implicita (lunghezza fissa); frame di lunghezza fissa solo per R3 su SX1278 |
| R4-R7 | LoRa 500/SF7, 250/SF7, 250/SF8, 250/SF9 | R5 è come lo Standard della v2, R6 come il Range |
| R8-R9 | LoRa 125/SF9, 125/SF10 | |
| **R10** | **LoRa 125/SF12** | **gradino di incontro**: come il profilo Messaggio della v2; l'ultimo senza dubbi sul quarzo |
| R11-R14 | LoRa 62,5/SF12, 31,25/SF12, 15,6/SF12, 7,8/SF12 | casi estremi; richiedono la misura M6 (deriva del quarzo) e probabilmente un TCXO |
| (R15) | riservato | |

LoRa SF5 (BW 500) esiste solo sull'SX1262: lo si tratta come estensione facoltativa, da annunciare in HELLO.

## 4. Formato dei frame
Tutti i numeri sono *big endian*. Il byte 0 è `0x30 | tipo`.

| Tipo | Nome | Contenuto |
|---|---|---|
| 0 | HELLO | incontro e capacità |
| 1 | PROBE | raffica di prova a un gradino candidato |
| 2 | PROBE-REPORT | esito della raffica |
| 3 | MODE-SET | proposta di cambio di gradino |
| 4 | MODE-ACK | conferma |
| 5 | OFFER | proposta di un oggetto |
| 6 | ACCEPT | accettazione, con i livelli voluti |
| 7 | DATA | un pezzo dell'oggetto |
| 8 | STATUS | mappa dei pezzi ricevuti e qualità del collegamento |
| 9 | PARITY | parità XOR facoltativa su un gruppo di pezzi |
| 10 | DONE | oggetto completo, con CRC |
| 11 | ABORT | interruzione |
| 12 | ID | identificazione periodica |
| 15 | TEST | frame di misura (firmware di misura) |

**Intestazione comune dei frame di sessione:** `byte0 (versione, tipo)`, `sessione (2)`, `flag (1)`. La **sessione** è casuale per ogni oggetto (come nella v2). Il **nominativo** compare in HELLO, OFFER, DONE e ID (lunghezza + ASCII, come nella v2) e **non in ogni frame DATA**: i pezzi usano la sessione, che HELLO e OFFER hanno legato al nominativo.

**DATA** (intestazione 6 byte): `0x37`, sessione (2), flag (1), **indice del pezzo (2)**, dati. Flag: `1` ultimo pezzo della finestra, `2` ritrasmissione, `4` ultimo pezzo dell'oggetto, `8` ultimo pezzo del livello.

**STATUS** (18 byte): `0x38`, sessione (2), flag (1), **base (2)** = primo pezzo mancante, **mappa (8 byte)** = i 64 pezzi dopo la base (1 = ricevuto), RSSI (1), SNR (1), perdita % nell'ultima finestra (1), livelli completati (1), riservato (1). La finestra massima è quindi 64 pezzi.

**OFFER:** `0x35`, sessione, flag, nominativo, **tipo di oggetto** (1), **dimensione (3)**, **dimensione del pezzo (1)**, **numero di pezzi (2)**, larghezza e altezza (2+2), **numero di livelli (1)** e per ognuno **l'indice dell'ultimo pezzo del livello (2)**, **CRC32 dell'oggetto (4)**. Tipi di oggetto: `0` blocco di prova (byte pseudocasuali), `1` JPEG progressivo (i livelli sono le scansioni), `2` scala di JPEG a risoluzioni diverse; il resto è riservato.

**HELLO:** `0x30`, nonce (2), flag (bit 0 `RISPOSTA`), nominativo, chip (SX1278/SX1262), maschera dei gradini supportati (2), frame massimo (1), memoria disponibile in kB (2), presenza di microSD. Serve a sapere che gradini sono ammessi (per esempio R0-R2 con la banda di ricezione dell'SX1278, SF5 solo SX1262).

## 5. Dimensione dei pezzi per gradino
Il **tempo in aria di un frame non deve superare circa 3 s** (perdite e tempi di ritorno), con un **minimo di 32 byte di dati**. Sull'SX1278 il frame FSK massimo è **64 byte** (FIFO, da confermare con la misura M5): 58 byte di dati. Sull'SX1262 si arriva a 249.

Con questa regola, tempo stimato per trasferire un oggetto (perdita media 5 %, una STATUS ogni 16 pezzi, 0,15 s di commutazione), **coppia SX1278 con SX1278**:

| R | Gradino | pezzo | frame | velocità netta | sens. stimata | 2 kB | 5 kB | 20 kB | 50 kB |
|---|---|---|---|---|---|---|---|---|---|
| R0 | FSK 150k | 58 B | 4 ms | 119.18 kbit/s | -102 dBm | 1 s | 2 s | 8 s | 20 s |
| R1 | FSK 100k | 58 B | 6 ms | 79.45 kbit/s | -103 dBm | 1 s | 2 s | 9 s | 22 s |
| R2 | FSK 50k | 58 B | 12 ms | 39.73 kbit/s | -106 dBm | 1 s | 3 s | 11 s | 27 s |
| R3 | LoRa 500/SF6 | 249 B | 58 ms | 34.41 kbit/s | -116 dBm | 1 s | 2 s | 7 s | 16 s |
| R4 | LoRa 500/SF7 | 249 B | 100 ms | 19.94 kbit/s | -119 dBm | 1 s | 3 s | 10 s | 25 s |
| R5 | LoRa 250/SF7 | 249 B | 0.20 s | 9.97 kbit/s | -122 dBm | 2 s | 5 s | 19 s | 47 s |
| R6 | LoRa 250/SF8 | 249 B | 0.35 s | 5.63 kbit/s | -124 dBm | 4 s | 9 s | 32 s | 79 s |
| R7 | LoRa 250/SF9 | 249 B | 0.63 s | 3.19 kbit/s | -127 dBm | 6 s | 15 s | 56 s | 2 min |
| R8 | LoRa 125/SF9 | 249 B | 1.25 s | 1.59 kbit/s | -130 dBm | 12 s | 29 s | 2 min | 5 min |
| R9 | LoRa 125/SF10 | 249 B | 2.30 s | 0.87 kbit/s | -132 dBm | 22 s | 52 s | 3 min | 8 min |
| R10 | LoRa 125/SF12 | 64 B | 2.96 s | 0.17 kbit/s | -137 dBm | 2 min | 4 min | 17 min | 42 min |
| R11 | LoRa 62,5/SF12 | 32 B | 3.95 s | 0.06 kbit/s | -140 dBm | 5 min | 11 min | 45 min | 1.9 h |
| R12 | LoRa 31,25/SF12 | 32 B | 7.90 s | 0.03 kbit/s | -143 dBm | 9 min | 23 min | 1.5 h | 3.8 h |
| R13 | LoRa 15,6/SF12 | 32 B | 15.82 s | 0.02 kbit/s | -146 dBm | 18 min | 45 min | 3.0 h | 7.5 h |
| R14 | LoRa 7,8/SF12 | 32 B | 31.64 s | 0.01 kbit/s | -149 dBm | 36 min | 1.5 h | 6.0 h | 15.0 h |

**Coppia SX1262 con SX1262**, solo i tre gradini FSK (il resto non cambia):

| R0 | FSK 150k | 249 B | 14 ms | 141.48 kbit/s | -102 dBm | 0 s | 1 s | 3 s | 7 s |
| R1 | FSK 100k | 249 B | 21 ms | 94.32 kbit/s | -103 dBm | 1 s | 1 s | 4 s | 8 s |
| R2 | FSK 50k | 249 B | 42 ms | 47.16 kbit/s | -106 dBm | 1 s | 2 s | 5 s | 13 s |

Il tempo reale sarà più alto, perché la stima non include la commutazione trasmissione-ricezione di ogni frame, i tempi del FIFO e le pause per il CAD. I tempi sotto R10 mostrano che il **modo estremo regge solo immagini minuscole**: a R12 e R13 anche solo 2 kB richiedono circa 9-18 minuti.

## 6. Incontro e capacità
1. Entrambe le stazioni ascoltano sul **gradino di incontro (R10)**. Chi vuole inviare manda **HELLO** (dopo il CAD); l'altro risponde con HELLO a bit `RISPOSTA`.
2. Dalle capacità si ricava l'insieme dei gradini ammessi.
3. Se nessuno risponde, si ripete HELLO con intervalli crescenti (da 5 a 60 s, con un po' di casualità) e per un massimo di tempo: **un nodo non trasmette all'infinito**.

## 7. Scelta e cambio del gradino
**Misura del collegamento.** Il ricevitore misura RSSI e SNR e li manda nei **STATUS**. Per un gradino LoRa si usa il **margine** `margine = SNR - SNR_richiesto(SF)`, dove l'SNR del gradino candidato si ricava da quello misurato come `SNR' = SNR + 10 log10(BW / BW')` (stessa potenza, rumore proporzionale alla banda). Per un gradino FSK si usa `margine = RSSI - sensibilità(gradino)`.

**Salita.** Dopo il primo STATUS a R10 si sceglie il gradino più veloce con **margine ≥ 6 dB** fra quelli ammessi e lo si conferma con una **raffica di PROBE** (8 frame, 4 ai gradini lenti). Se il ricevitore ne riceve almeno il **90 %**, il **MODE-SET** si accetta. In trasferimento si sale di un gradino dopo **3 finestre di fila** con perdita sotto il 2 % e margine ≥ 6 dB sul gradino successivo.

**Discesa.** Si scende di un gradino **subito** se in una finestra la perdita supera il **20 %** o se due STATUS di fila mancano. La discesa non richiede conferma: chi non sente più il mittente passa da solo a R10 dopo il **tempo di fallback** (il maggiore fra 30 s e 4 finestre).

**Cambio di gradino.** `MODE-SET` (gradino, ripetuto 3 volte) → `MODE-ACK` nel gradino attuale → **entrambe** le stazioni passano al nuovo gradino **alla fine del MODE-ACK**. Se la prima PROBE sul nuovo gradino non ottiene risposta entro il fallback, **si torna a R10** e si riparte da HELLO.

## 8. Trasferimento a finestre
1. **OFFER** → **ACCEPT** (livelli voluti, finestra `W` da 1 a 64, di base 16).
2. Il mittente manda `W` pezzi di fila (CAD prima della finestra), l'ultimo con il flag `1`.
3. Il ricevitore risponde con **STATUS** dopo il pezzo con il flag `1` o, se non è arrivato, dopo `W × tempo_pezzo + 0,15 s`.
4. Il mittente ritrasmette **solo i pezzi mancanti** con il flag `2` e prosegue con altri, a finestre di `W` frame in tutto.
5. Se manca lo STATUS, il mittente ripete l'ultimo pezzo (con flag `1`) fino a 3 volte, poi **scende di un gradino**.
6. Fine: **DONE** con il CRC32 dell'oggetto; il ricevitore lo conferma con un STATUS completo.
7. **PARITY** (facoltativa): un frame di parità XOR ogni `G` pezzi (come la v2) recupera una perdita per gruppo senza aspettare lo STATUS. Si usa dai gradini lenti, dove un giro di ritrasmissione costa molto; il valore di `G` si decide con le misure.

## 9. Ridimensionare l'immagine
Il **budget di tempo** per oggetto è un parametro (di base **10 minuti**). Prima di ogni livello il mittente stima il tempo del resto con il gradino attuale (`estimate_seconds` nello script, che dà le stesse cifre di questa pagina):

- se il livello **entra** nel tempo che resta, lo manda;
- se **non entra**, si ferma al confine del livello già completo e invia **DONE** con i livelli consegnati: l'immagine è utile ma meno dettagliata;
- se **neanche il primo livello entra** al gradino migliore possibile, **non parte**: l'OFFER propone una versione più piccola (un altro oggetto con meno pixel), oppure rinuncia.
Il ricevitore può rifiutare in ACCEPT i livelli sopra una certa dimensione (memoria o tempo).
La **preparazione dei livelli** si fa fuori dal firmware, dall'applicazione ([app/](../app/)): per esempio **JPEG progressivo** con scansioni a risoluzione crescente, oppure una **scala di JPEG** a dimensioni 1/8, 1/4, 1/2 e piena. **Va deciso con le prove** quale dà il miglior risultato a parità di byte.

## 10. Identificazione, sicurezza, memoria
- **Identificazione.** Il nominativo è in HELLO, OFFER, DONE e nei frame `ID`, che nei trasferimenti lunghi si mandano **a intervalli regolari**; l'intervallo si fissa con la normativa (la v2 manda il nominativo ogni circa 5 secondi in voce). Il canale non è cifrato (come la v2).
- **Integrità.** CRC radio su ogni frame e CRC32 dell'oggetto in OFFER e DONE; nessuna autenticazione: chiunque può inviare. Si decide in seguito se aggiungere una firma (nei nodi Internet la v2 usa HMAC).
- **Memoria.** La T3 non ha PSRAM: un oggetto fino a circa 100 kB sta in RAM; oltre serve la **microSD** ([scheda-sd.md](scheda-sd.md)), solo nel nodo immagini. La dimensione massima dichiarata in HELLO dice quanto si può offrire.

## 11. Immagini fittizie per le prove
Le prove cominciano **senza un codec**: l'oggetto di tipo `0` è un blocco di byte pseudocasuali di dimensione scelta (2, 5, 20, 50 kB…) con CRC32. L'applicazione ([app/](../app/), scheda "Immagini") li genera e mostra il tempo stimato per ogni gradino. Poi si passa ad **immagini di prova** (schemi di taratura a dimensione variabile) e a **foto vere** quando il trasporto è affidabile.

## 12. Da decidere dopo le misure
1. **Sensibilità vere** di ogni gradino (misure M2, M4): spostano le soglie di margine del punto 7.
2. **FIFO da 64 byte dell'SX1278** in FSK (M5): decide la dimensione del pezzo FSK, e se R0-R2 hanno senso sulla T3.
3. **Deriva del quarzo** (M6): decide se R11-R14 sono utilizzabili senza TCXO.
4. **Tempo di commutazione trasmissione-ricezione e del CAD** (oscilloscopio): decide la durata di `guard` e la dimensione della finestra.
5. **Codifica dell'immagine:** JPEG progressivo o scala di JPEG; confronto con le prove.
6. **Parità XOR** sì o no, e con che gruppo.
7. **Canale delle immagini:** una frequenza diversa da quella della voce (v2: 433,475 MHz di base) per non occupare il canale della voce; negoziabile o fisso?
8. **Intervallo di identificazione** dei trasferimenti lunghi.
9. **Immagini via ripetitore e reflector:** sì o no ([punti-aperti.md](punti-aperti.md)).

## 13. Piano di prova
1. **Sul PC:** un simulatore con perdite e rumore verifica gli algoritmi del punto 7 e 8 (da scrivere).
2. **A banco:** blocchi di prova di 2, 5, 20 kB a ogni gradino con le attenuazioni delle misure, con il firmware di misura esteso ai tipi 0-12.
3. **Sul campo:** [prove-sul-campo.md](prove-sul-campo.md), con le immagini vere.
