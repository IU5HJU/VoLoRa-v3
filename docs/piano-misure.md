# Piano di misura della fase 1 (bozza)

Scopo: sostituire le stime di [scala-modi.md](scala-modi.md) con misure. Cosa si usa della v2 (solo dal repository VoLoRa): schede T3 e T-Beam, ricevitore SDR (`tools/sdr`, GNU Radio con `gr-lora_sdr`, vedi la sua `docs/sdr.md`), la prova di collegamento e il registro seriale.

> **Regola ferma (dalla v2):** antenna o carico fittizio collegati **prima** dell'USB, mai trasmettere senza. Trasmetti solo con il tuo nominativo.

## 1. Attrezzatura

| Cosa | A cosa serve |
|---|---|
| 2 T3 V1.6.1 (SX1278), possibilmente una con TCXO | coppia principale |
| 2 T-Beam V1.2 con SX1262 | coppia per SF5 e per il confronto SX1262 |
| Attenuatori SMA fissi (per esempio 10, 20, 30 dB) con carichi da 50 Ω | portare la potenza ricevuta in zona di sensibilità senza irradiare. **Da procurare.** |
| Cavi SMA corti e connettori | collegamento via cavo, schede **nello schermo di una scatola metallica** |
| Chiavetta SDR (NESDR) | verifica indipendente di frequenza, banda occupata e struttura dei pacchetti (non per la sensibilità: la sua è peggiore) |
| Misuratore di potenza o analizzatore | taratura dell'uscita, se disponibile (altrimenti si usa il valore dichiarato dal chip) |
| PC con porta seriale e script di registrazione | registro di ogni prova su file |

## 2. Metodo di base: collegamento via cavo con attenuazione nota
1. Le due schede si collegano **via cavo e attenuatori**, non in aria: la perdita è nota e ripetibile e non si disturba nessuno.
2. La potenza di trasmissione è nota (parametro del chip) e la potenza ricevuta si calcola: `P_rx = P_tx - attenuazione`. Lo si confronta con l'RSSI letto dalla scheda ricevente.
3. Per ogni modo si **aumenta l'attenuazione a passi di 2 dB** finché la perdita di pacchetti supera una soglia: **sensibilità = ultima potenza con meno del 10 % di pacchetti persi** (soglia da fissare, tipica per LoRa).
4. Ogni punto: almeno 200 pacchetti da 255 byte (meno per i modi lunghi, ma mai meno di 30).
5. Il **tempo in aria misurato** (da inizio a fine pacchetto) si confronta con la formula.

Limite del metodo: sotto circa -100 dBm di potenza ricevuta la perdita per accoppiamento diretto (schede vicine, senza schermo) può falsare la misura: per questo la scatola metallica e i cavi.

## 3. Misure, in ordine

| # | Misura | Come | Esito |
|---|---|---|---|
| M1 | Tempo in aria e velocità vera di ogni gradino LoRa (L1-L13 di [scala-modi.md](scala-modi.md)) | pacchetti da 255 byte, tempo dal registro e dall'SDR | tabella: formula contro misura |
| M2 | **Sensibilità LoRa** di ogni gradino | metodo del punto 2, T3 e T-Beam SX1262 | tabella: sensibilità vera, Δ rispetto alla stima |
| M3 | SF5 su SX1262 e **SF6 su SX1278** | come M2 | conferma dei limiti di [radio-limiti.md](radio-limiti.md) |
| M4 | **FSK**: bit rate x deviazione x banda di ricezione | prima con pacchetti corti (≤ 64 byte), poi lunghi con FIFO | sensibilità e perdite per ogni combinazione |
| M5 | Limite del **FIFO da 64 byte** dell'SX1278 in FSK | pacchetti da 100-255 byte a 100, 150 e 300 kbit/s | massimo bit rate senza errori di FIFO; confronto con SX1262 |
| M6 | **Deriva del quarzo** alle bande strette (L10-L13) | scarto di frequenza fra le due schede, anche con la scheda calda e fredda; T3 con e senza TCXO | si usa o no la banda < 31 kHz |
| M7 | **Banda occupata** e spettro | SDR, FSK a 300 kbit/s e deviazione 100 kHz, LoRa a 500 kHz | larghezza effettiva |
| M8 | Rendimento agli estremi della gamma | stessa misura M2 su un gradino a 430,0 / 433,5 / 440,0 MHz | calo di sensibilità e di potenza ai bordi |
| M9 | **Microsd** (solo T3 senza audio) | scrittura a blocchi durante la ricezione, corrente, effetto sulla sensibilità | vedi [scheda-sd.md](scheda-sd.md) |
| M10 | Coesistenza con la **voce v2** | un nodo V3 e un nodo v2 sulla stessa frequenza in modo Standard e Messaggio | la voce v2 passa; i pacchetti V3 non la disturbano oltre il previsto |

## 4. Cosa registrare per ogni punto
Data, schede e versione del firmware, frequenza, modo (BW, SF, CR oppure bit rate, deviazione, RxBw), potenza di trasmissione, attenuazione totale, pacchetti inviati e ricevuti, RSSI e SNR medi, tempo in aria misurato, temperatura approssimativa, file di registro. Gli esiti vanno in `docs/misure/` con una tabella per misura.

## 5. Software di prova (da scrivere, nella fase 2)
- Firmware di misura minimo: un unico firmware con comandi seriali per impostare modo, frequenza e potenza, inviare N pacchetti e contare quelli ricevuti.
- Script sul PC che esegue la scala dei modi e le attenuazioni e scrive i risultati in un file.
- Questo firmware non è il V3 e non va confuso con esso.

## 6. Rischi
- **Perdita di pacchetti per accoppiamento diretto:** si risolve con scatola metallica e cavi.
- **Sensibilità dell'SDR** peggiore di quella delle schede: lo si usa solo come verifica.
- **Misure falsate dalla temperatura** sulle bande strette: annotare e ripetere.
- Alcune misure (M6, M8) hanno bisogno di strumenti che potrebbero mancare: vanno decisi prima.

## 7. Domande aperte
1. Quali strumenti hai già (misuratore di potenza, attenuatori, analizzatore)?
2. Hai una T3 con TCXO?
3. Le schede possono stare in una scatola metallica?
