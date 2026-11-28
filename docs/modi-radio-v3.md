# I modi radio di VoLoRa V3: guida per tutti

> **Stato (28/11/2026): sono stime di studio, non misure.** Le sensibilità sono calcolate con le formule Semtech e confrontate con i datasheet (scarto entro 2 dB, [confronto-datasheet.md](confronto-datasheet.md)); i tempi sono calcolati da `tools/protocollo_immagini.py`. Su una scheda vera finora si sono provati il gradino di incontro e lo scambio di testi e di qualche immagine, senza registrare i gradini: **le misure vere sono la fase 1 dello studio**. Questo documento è generato da `tools/gen_doc_modi.py`: non si modificano le tabelle a mano.

## In breve
- Il protocollo V3 ha **15 modi radio, chiamati gradini (R0 … R14)**: 12 LoRa (R3 … R14) e 3 FSK (R0 … R2).
- **Più stretta è la banda e più alto è il fattore SF, più lontano arriva il segnale ma meno dati passano.** I due estremi sono lontanissimi: R14 manda circa 8 bit al secondo, R3 circa 34 000.
- Le due stazioni si incontrano sempre sul **gradino di incontro R10** (LoRa 125 kHz / SF12) e poi **salgono al gradino più veloce che il collegamento regge**, o scendono se peggiora.
- Con **10 minuti** per oggetto, i gradini lenti portano solo cose piccolissime; i veloci portano immagini intere in pochi secondi.

## 1. Che cos'è un "modo"
Un modo è il **modo di modulare il segnale**: quanto è larga la banda occupata, quanto lentamente si trasmettono i simboli, quanta correzione d'errore c'è. In VoLoRa i modi sono di due famiglie.

- **LoRa** (spettro espanso): robusto, riceve segnali molto deboli, anche sotto il rumore. Ha tre manopole:
  - **Banda (BW):** 7,8 … 500 kHz. Dimezzare la banda dimezza la velocità e guadagna circa **3 dB** di sensibilità (cioè circa il 41% di portata in più in spazio libero).
  - **Fattore di espansione (SF):** 6 … 12. Un SF in più dimezza la velocità e guadagna circa **2,5 dB**.
  - **Codifica (CR):** fissa a 4/5 in tutti i gradini.
- **FSK** (frequenza a due toni): più semplice e molto più veloce, ma **riceve segnali molto più forti**: serve per i collegamenti forti, per esempio due schede vicine o in vista.

Il guadagno di sensibilità si paga in **tempo in aria**: un frame che a R3 dura 0,06 secondi a R14 dura 32 secondi.

## 2. La scala dei 15 gradini
Ordinati **dal più stretto di banda al più largo** (prima i LoRa, poi i FSK). "Velocità nominale" è quella della modulazione; "velocità utile" è quella dei byte di dati dell'oggetto, senza risposte né ritrasmissioni; "5 kB" e "20 kB" sono i tempi stimati **con** ritrasmissioni (5% di perdita), le risposte STATUS e le pause; "byte in 10 minuti" è il più grande oggetto che sta nel tempo massimo del protocollo.

| Gradino | Modo | Velocità nominale | Sensibilità | Portata rispetto a R5 | Dati per frame (byte) | Frame in aria | Velocità utile | 5 kB | 20 kB | Byte in 10 minuti |
|---|---|---|---|---|---|---|---|---|---|---|
| **R14** | LoRa 7,8 / SF12 | 18 bit/s | -149,1 dBm | ×23,9 | 32 | 31,64 s | 8 bit/s | 1,5 h | 6,0 h | 512 B |
| **R13** | LoRa 15,6 / SF12 | 37 bit/s | -146,1 dBm | ×16,9 | 32 | 15,82 s | 16 bit/s | 45 min | 3,0 h | 1,1 kB |
| **R12** | LoRa 31,25 / SF12 | 73 bit/s | -143,1 dBm | ×11,9 | 32 | 7,90 s | 32 bit/s | 23 min | 1,5 h | 2,2 kB |
| **R11** | LoRa 62,5 / SF12 | 146 bit/s | -140,0 dBm | ×8,4 | 32 | 3,95 s | 65 bit/s | 11 min | 45 min | 4,4 kB |
| **R10** (incontro) | LoRa 125 / SF12 | 293 bit/s | -137,0 dBm | ×6,0 | 64 | 2,96 s | 173 bit/s | 4 min | 17 min | 12 kB |
| **R9** | LoRa 125 / SF10 | 977 bit/s | -132,0 dBm | ×3,4 | 240 | 2,21 s | 867 bit/s | 50 s | 3 min | 61 kB |
| **R8** | LoRa 125 / SF9 | 1,8 kbit/s | -129,5 dBm | ×2,5 | 240 | 1,21 s | 1,6 kbit/s | 28 s | 2 min | 110 kB |
| **R7** | LoRa 250 / SF9 | 3,5 kbit/s | -126,5 dBm | ×1,8 | 240 | 0,60 s | 3,2 kbit/s | 14 s | 56 s | 218 kB |
| **R6** | LoRa 250 / SF8 | 6,2 kbit/s | -124,0 dBm | ×1,3 | 240 | 0,34 s | 5,7 kbit/s | 8 s | 32 s | 381 kB |
| **R5** | LoRa 250 / SF7 | 11 kbit/s | -121,5 dBm | = (riferimento) | 240 | 0,19 s | 10,0 kbit/s | 5 s | 19 s | 647 kB |
| **R4** | LoRa 500 / SF7 | 22 kbit/s | -118,5 dBm | ×0,7 | 240 | 0,10 s | 20 kbit/s | 3 s | 10 s | 1,2 MB |
| **R3** | LoRa 500 / SF6 | 38 kbit/s | -116,0 dBm | ×0,5 | 240 | 0,06 s | 34 kbit/s | 2 s | 7 s | 1,8 MB |
| **R2** | FSK 50k | 50 kbit/s | -106,0 dBm | ×0,2 | 48 | 0,01 s | 38 kbit/s | 3 s | 13 s | 972 kB |
| **R1** | FSK 100k | 100 kbit/s | -103,0 dBm | ×0,1 | 48 | 0,01 s | 76 kbit/s | 3 s | 10 s | 1,2 MB |
| **R0** | FSK 150k | 150 kbit/s | -102,0 dBm | ×0,1 | 48 | 0,00 s | 114 kbit/s | 2 s | 10 s | 1,3 MB |

**Come leggere la tabella**
- **R5** (LoRa 250 kHz / SF7) è come il profilo **Standard** della v2 e **R6** come il **Range**; **R10** (125 kHz / SF12) è come il profilo **Messaggio** della v2: il gradino di incontro.
- **La portata** è relativa a R5: ×6,0 per R10 significa che, a parità di potenza, R10 arriva 6,0 volte più lontano in spazio libero. È un **confronto**, non una distanza (vedi sotto).
- **I frame dei gradini lenti sono piccoli** (32 o 64 byte di dati, più 6 di intestazione): il protocollo non fa durare un frame in aria più di circa 3 secondi, per non perdere troppo se un frame va male.

### I tre gradini FSK, per chip
L'SX1278 (T3, T-Beam con modulo SX1278) ha un FIFO FSK di 64 byte, e l'SX1262 (T-Beam con modulo SX1262) di 255:

| Gradino | Modo | Banda occupata | Sensibilità | SX1278: dati per frame | SX1278: velocità utile | SX1262: dati per frame | SX1262: velocità utile |
|---|---|---|---|---|---|---|---|
| **R0** | FSK 150 kbit/s, deviazione 50 kHz | 250 kHz | -102,0 dBm | 48 B | 114 kbit/s | 240 B | 141 kbit/s |
| **R1** | FSK 100 kbit/s, deviazione 50 kHz | 200 kHz | -103,0 dBm | 48 B | 76 kbit/s | 240 B | 94 kbit/s |
| **R2** | FSK 50 kbit/s, deviazione 25 kHz | 100 kHz | -106,0 dBm | 48 B | 38 kbit/s | 240 B | 47 kbit/s |

## 3. La portata
**Quanto lontano arriva un modo** dipende da due cose: la **sensibilità** del ricevitore (il segnale più debole che sa decodificare) e la **potenza** trasmessa. La differenza è il **margine di collegamento**. A +17 dBm (la potenza normale delle schede) il margine va da 133 dB a R3 a 166 dB a R14.

Ogni **6 dB** in più di margine raddoppiano la distanza in spazio libero, ma lo spazio libero esiste solo in teoria. Esempi con +17 dBm e antenne ideali a 0 dBi, a 433,7 MHz:

| Gradino | Sensibilità | Margine con +17 dBm | Spazio libero ideale | Con le antenne a 10 m (orizzonte radio 26 km) |
|---|---|---|---|---|
| R14 (LoRa 7,8/SF12) | -149,1 dBm | 166,1 dB | 11086 km |
| R10 (LoRa 125/SF12) | -137,0 dBm | 154,0 dB | 2769 km |
| R5 (LoRa 250/SF7) | -121,5 dBm | 138,5 dB | 464 km |
| R3 (LoRa 500/SF6) | -116,0 dBm | 133,0 dB | 246 km |

- In **spazio libero** le distanze vengono migliaia di chilometri: non sono realistiche, **la Terra è curva**. Due antenne a 10 m si vedono fino a circa 26 km, a 100 m fino a circa 82 km.
- Perciò il vantaggio dei gradini lenti **non** è "arrivare più lontano di quello che permette l'orizzonte", ma **passare attraverso ostacoli**, alberi, edifici, colline e zone deboli: ogni dB di margine in più è un ostacolo in più che il segnale sopporta. R10 ha circa **16 dB** in più di R5, R14 circa **28 dB**.
- **Lo stesso vale al contrario:** con due schede vicine un modo lento non serve a niente, è solo lento. Il protocollo sale da solo al gradino più veloce.

## 4. Cosa si può scambiare in ogni modo
Con il tempo massimo di **10 minuti** per oggetto (budget del protocollo), il gradino più lento che ci sta è:

| Cosa si manda | Dimensione | Gradino più lento che ci sta in 10 minuti | Con quel gradino |
|---|---|---|---|
| un messaggio di testo | 1,0 kB | **R13** (LoRa 15,6/SF12) | 9 min |
| una miniatura | 2,0 kB | **R12** (LoRa 31,25/SF12) | 9 min |
| un'immagine piccola | 5,0 kB | **R10** (LoRa 125/SF12) | 4 min |
| un'immagine media | 10 kB | **R10** (LoRa 125/SF12) | 8 min |
| un'immagine grande | 20 kB | **R9** (LoRa 125/SF10) | 3 min |
| il massimo del protocollo | 66 kB | **R8** (LoRa 125/SF9) | 6 min |

- Il protocollo manda le immagini **a livelli** (JPEG progressivo, tre livelli): il primo livello è circa un terzo dei byte ed è già un'immagine intera, ma sfocata. Se il tempo non basta, **arriva solo il primo livello** invece di niente.
- **Il testo** (fino a 1 kB) passa in pochi secondi anche ai gradini più lenti, a parte i tempi di incontro.
- **Un'immagine da 10 kB** richiede un gradino da 125 kHz / SF10 (R9) o più veloce; sotto, si consegnano solo i primi livelli.
- I tempi **non** includono il tempo per trovare l'altra stazione (l'HELLO a R10) né i cambi di gradino.

## 5. Come il protocollo sceglie il gradino
1. Le due stazioni si incontrano a **R10** (LoRa 125 kHz / SF12), il gradino che "arriva dappertutto" fra quelli senza problemi di quarzo. Chi vuole inviare manda un **HELLO**; l'altra risponde con il livello che ha sentito (RSSI e SNR).
2. Dalla misura si sceglie il **gradino più veloce con almeno 6 dB di margine** fra quelli che entrambe le stazioni sanno fare.
3. Durante il trasferimento, a ogni finestra di 16 frame il ricevitore risponde con quanto ha sentito: se **più del 20%** dei frame va perso si **scende** di un gradino; se **meno del 2%** si va avanti per tre finestre di fila e c'è margine, si **sale**.
4. Se il collegamento si perde, **si torna a R10** e lo si ritrova lì.

## 6. Limiti e condizioni
- **R12, R13, R14** (banda 31,25 kHz o meno) richiedono un **TCXO**: la deriva di un quarzo normale (circa 10 ppm per scheda) può superare la banda. Senza TCXO non sono annunciati e non si usano. Il TCXO oggi non si legge dalla scheda.
- **R3** (SF6) richiede, sull'SX1278, l'intestazione implicita: il driver non la fa, quindi **R3 non si usa sull'SX1278**. L'SF6 dell'SX1278 e quello dell'SX1262 non sono comunque compatibili fra loro.
- **R0** (FSK 150 kbit/s) è realizzabile solo sull'SX1278; sull'SX1262 il bit rate massimo scala con la frequenza (circa 142 kbit/s a 433,7 MHz), quindi R0 **non è garantito** sull'SX1262 (la tabella FSK dà la cifra teorica a 150 kbit/s).
- **Potenza:** normale +17 dBm (il massimo in continuo dell'SX1278); `POWER` la abbassa per le prove con attenuatori; **BOOST** a +20 dBm e **IOF MODE** a +22 dBm (solo SX1262) sono modalità estreme con rischio tecnico (calore, corrente, saturazione dei ricevitori vicini, spurie). Non ci sono limiti di potenza "legali" nel progetto.
- **Saturazione:** con le schede vicine il ricevitore si satura; per le prove servono attenuatori (60-100 dB in tutto, [prove-laboratorio-v3.md](prove-laboratorio-v3.md)).
- **Le cifre sono stime:** i tempi veri saranno più alti, perché mancano le commutazioni trasmissione/ricezione di ogni frame, i tempi del FIFO e le pause di ascolto.

## 7. Glossario
- **Gradino (rung):** uno dei 15 modi della scala, R0 … R14.
- **BW:** banda occupata dal segnale (kHz). **SF:** fattore di espansione LoRa (6-12). **CR:** codifica di correzione d'errore (qui sempre 4/5).
- **FSK:** modulazione di frequenza a due toni.
- **Sensibilità:** il segnale più debole (in dBm) che il ricevitore decodifica. Più è negativa, meglio è.
- **dBm / dB:** potenza assoluta / rapporto di potenza. +3 dB = il doppio della potenza; +6 dB = il doppio della distanza in spazio libero.
- **RSSI / SNR:** livello e rapporto segnale-rumore misurati dal ricevitore.
- **Tempo in aria:** quanto dura la trasmissione di un frame.
- **TCXO:** quarzo compensato in temperatura, molto più stabile.
- **STATUS:** la risposta del ricevitore ogni 16 frame con la mappa di quello che ha ricevuto: si ritrasmette solo il mancante.

## Fonti nel progetto
[scala-modi.md](scala-modi.md) (scala e sensibilità), [protocollo-immagini.md](protocollo-immagini.md) (protocollo e gradini), [confronto-datasheet.md](confronto-datasheet.md) (limiti dei chip), [prove-laboratorio-v3.md](prove-laboratorio-v3.md) (come provare), `tools/protocollo_immagini.py` (i numeri). **PDF da allegare:** [pdf/modi-e-negoziazione-v3.pdf](pdf/modi-e-negoziazione-v3.pdf) (i modi e la logica di negoziazione fra le schede, 7 pagine).
