# Confronto con i datasheet Semtech (26/11/2026)

Fonti: [SX1276/77/78/79 Rev. 4](datasheet/SX1276-77-78-79_datasheet_rev4.pdf) (l'SX1278 è la versione 137-525 MHz) e [SX1261/2 Rev. 1.2](datasheet/SX1261-2_datasheet_rev1.2.pdf). Strumento: [`tools/limiti_chip.py`](../tools/limiti_chip.py), prova [`tests/sim/test_limiti_chip.py`](../tests/sim/test_limiti_chip.py). **Provato sul PC, non su schede.** I valori del datasheet sono tipici e dati dal costruttore: le schede (filtri, adattamento, antenna) vanno comunque misurate.

## 1. Esito in breve
| | Esito |
|---|---|
| Campo di sintonia | **Corretto:** SX1278 137-175 e **410**-525 MHz (non 395: quello è RadioLib, il datasheet non lo garantisce); SX1262 150-960 MHz. I canali 433,700 / 433,850 / 433,955 e i limiti 430 e 440 MHz sono dentro per entrambi. 144,900 MHz solo SX1278. |
| Sensibilità LoRa della scala | **Confermata** entro 2 dB su 12 dei 13 punti confrontabili; **R3 (500/SF6) è ottimista di 4 dB** (stima -116, datasheet -112 dBm). |
| R0-R2 FSK | **R0 (150 kb/s) non è garantito sull'SX1262 a 433 MHz** (il bit rate massimo scala con la frequenza: circa 142 kb/s). R1 e R2 vanno su entrambi. |
| Banda di ricezione FSK | **Correzione:** il filtro dell'SX1278 è a banda laterale singola (250 kHz = 500 kHz di segnale), quello dell'SX1262 a doppia banda (467 kHz). La riga F1 (300 kb/s, deviazione 100 kHz) non andava: **cambiata in deviazione 75 kHz**. |
| R3 (LoRa 500/SF6) | **Non compatibile fra SX1278 e SX1262**: l'SF6 dell'SX1262 è diverso. Su SX1278 solo con intestazione implicita. |
| R12-R14 | La **tolleranza sul quarzo è quantificata**: con quarzi da 10 ppm R12-R14 non funzionano (serve un TCXO). |
| Canali (larghezze) | Compatibili: i gradini ammessi in ogni canale stanno nella larghezza e sono realizzabili. |
| Canale di servizio 2 m | Compatibile (FSK stretta, solo SX1278); il filtro di ricezione dev'essere da 15,6 kHz, non da 10,4. |

## 2. Gradino per gradino (433,7 MHz, due quarzi da 10 ppm)
| Gradino | SX1278 | SX1262 | Note dal datasheet |
|---|---|---|---|
| R0 FSK 150k/dev 50 | sì | **NO (150 > 142 kb/s)** | SX1262: nota 5 della Table 3-7. SX1278: oltre 64 byte il FIFO va rifornito in volo |
| R1 FSK 100k | sì | sì | |
| R2 FSK 50k | sì | sì | |
| R3 LoRa 500/SF6 | sì, implicito | sì | **SF6 diverso fra i due chip**: R3 solo fra chip della stessa famiglia |
| R4-R9 | sì | sì | SX1262 a 500 kHz: bit 2 del registro 0x0889 a 0 prima di ogni trasmissione |
| R10 (incontro, 125/SF12) | sì | sì | budget di frequenza 50 ppm totali |
| R11 62,5/SF12 | sì | sì | budget 36 ppm |
| R12 31,25/SF12 | **NO con 10 ppm** (budget 18 ppm) | idem | serve TCXO |
| R13 15,6/SF12 | **NO** (budget 9 ppm) | idem | TCXO |
| R14 7,8/SF12 | **NO** (budget 4,5 ppm) | idem | TCXO da 2 ppm per scheda al limite |

Il budget è l'errore di frequenza **totale** fra trasmettitore e ricevitore ammesso senza perdita: il più stretto fra ±25% della banda e, per SF10/11/12, ±200/100/50 ppm. Con un TCXO da 2 ppm per scheda R12-R14 tornano ammessi; con 2,5 ppm R14 no.

## 3. Dettagli per argomento
**Frequenze.** SX1278: Table 7, Band 3 137-175 MHz, Band 2 410-525 MHz. SX1262: 150-960 MHz. La calibrazione dell'immagine dell'SX1262 ha una banda predefinita **430-440 MHz** (Table 9-2: `CalibrateImage` con 0x6B e 0x6F): è proprio la nostra banda, il firmware può chiamarla una volta.

**FSK.** SX1278: bit rate 1,2-300 kb/s (RadioLib: da 0,5), deviazione 0,6-200 kHz, **FDA + BR/2 ≤ 250 kHz**, filtro di ricezione **banda laterale singola** 2,6-250 kHz, **indice di modulazione al massimo 0,5 al bit rate massimo**, il bit rate deve stare sotto il doppio del filtro. SX1262: 0,6-300 kb/s ma il massimo **scala con la frequenza** (300 a 869/915, 50 a 150 MHz: circa 142-150 a 433 MHz), deviazione 0,6-200 kHz, indice almeno 0,5, filtro a **doppia** banda 4,8-467 kHz con 2·Fdev + BR < banda e l'errore di frequenza (due volte quello del quarzo) da aggiungere.
- **Pacchetti FSK sull'SX1278:** il FIFO è di 64 byte, ma **non è un limite del chip**: il datasheet (4.2.13.5) descrive l'invio e la ricezione di pacchetti più lunghi rifornendo il FIFO mentre si trasmette. Il limite di 64 byte è della libreria RadioLib (e il test sulla T3 con 255 byte ha dato errore per questo). Si può superare scrivendo la gestione del FIFO nel firmware: decisione di progetto.
- **Sensibilità FSK reali** (SX1278, Bands 2&3, percorsi condivisi): -117 dBm a 4,8 kb/s, -107 a 38,4 kb/s (FDA 40), -95 a 250 kb/s (FDA 62,5, filtro 250). La stima dello studio per F1-F3 (-99/-102/-103) è ottimista di circa 3-5 dB agli alti bit rate; SX1262 a 250 kb/s: -104 dBm (con gain potenziato).

**LoRa.** Bande 7,8-500 kHz per entrambi; SF 6-12 (SX1278) e 5-12 (SX1262). **Velocità massima:** SX1278 37,5 kb/s (SF6, 500 kHz), SX1262 62,5 kb/s (SF5, 500 kHz): chiude la discrepanza segnalata in radio-limiti (vale 37,5 per l'SX1278). Pacchetto massimo 255 byte. SNR di demodulazione per SF: -5 (SF6) … -20 dB (SF12), **gli stessi usati dallo studio**. Sull'SX1278 a 169 MHz (Band 3) le bande 250 e 500 kHz non sono supportate (non ci riguarda: a 144,9 MHz si usa la FSK). SX1262 sotto i 400 MHz: "alcune bande potrebbero non essere disponibili"; a 433 MHz no.
- **SF6 e SF5:** SX1278 SF6 richiede intestazione implicita, `DetectionOptimize` = 0b101 e soglia 0x0C. SX1262 SF5/SF6 funzionano anche con intestazione esplicita ma con preambolo da 12 simboli consigliato, e **l'SF6 non è compatibile con quello dell'SX1276**.

**Potenza (limiti tecnici, non legali).** SX1278: +14 dBm sul pin RFO; **+17 dBm in continuo e +20 dBm con ciclo di lavoro massimo 1%** e VSWR 3:1 sul pin PA_BOOST (Table 35); corrente in trasmissione 87 mA a +17 e 120 mA a +20. SX1262: fino a +22 dBm (118 mA). Per un nodo che trasmette voce e immagini a lungo (ripetitore) sull'SX1278 il limite tecnico continuo è **+17 dBm**; a +20 dBm solo a ciclo breve. Ricezione: 12 mA (SX1278, bande 2 e 3).

## 4. Voto a 2 m (144,900 MHz)
Compatibile: l'SX1278 sintonizza 137-175 MHz (Band 3); l'SX1262 no (parte da 150 MHz), come già deciso. La FSK a **9,6 kHz di banda occupata** (per esempio 4,8 kb/s e deviazione 2,4 kHz) sta nel segmento MGM da 12 kHz. In ricezione però il filtro deve avere l'errore di frequenza di due quarzi: servono circa 15,4 kHz con 10 ppm, quindi il **filtro da 15,6 kHz di banda totale** (7,8 kHz di banda laterale singola nell'SX1278), non quello da 10,4: sensibilità un poco inferiore ai -117 dBm del datasheet. La terza armonica a 434,7 MHz resta da filtrare (già annotato).

## 5. Correzioni fatte nel repository
- `tools/canali.py` e test: SX1278 410-525 MHz (era 395).
- `tools/scala_modi.py`: F1 = 300 kb/s con deviazione **75 kHz** (450 kHz di banda, indice 0,5; ammesso da entrambi i chip).
- App di misura (`app/volora_misure/core.py`, `tools/misura.py`): per l'SX1278 il filtro FSK si passa a **banda laterale singola** (la metà della banda del segnale). Prima il comando MODE chiedeva il doppio del necessario (filtro due volte più largo, circa 3 dB di rumore in più): sulle schede vere la misura FSK dell'SX1278 sarebbe uscita peggiore del dovuto. Il firmware di misura passa il numero a RadioLib così com'è.
- `docs/radio-limiti.md`, `docs/scala-modi.md`, `docs/punti-aperti.md`: aggiornati con i valori dei datasheet.

## 6. Decisioni dell'autore (26/11/2026)
1. **R3 (LoRa 500/SF6):** vale **solo fra chip della stessa famiglia** (SX1278 con SX1278, SX1262 con SX1262). Il campo `chip` dell'HELLO delle immagini lo toglie dalla maschera comune quando i due chip differiscono; in quel caso si parte da R4.
2. **R0 (FSK 150 kb/s):** gradino **solo SX1278**; il T-Beam con SX1262 parte da R1. Nessuna modifica alla scala.
3. **R12-R14 (LoRa 31,25 / 15,6 / 7,8 kHz):** **solo con TCXO annunciato** nell'HELLO; senza TCXO non sono nella maschera. R14 resta al limite anche con 2 ppm per scheda (da misurare).
4. **FSK sull'SX1278:** **si resta a 64 byte** per frame; la gestione del FIFO oltre i 64 byte si rivaluta dopo le misure se l'FSK risulta lo strozzo.
5. **Potenza dei nodi che ritrasmettono (SX1278):** **+17 dBm in continuo**; +20 dBm solo per frame brevi (beacon, polling) entro il ciclo dell'1% del chip. Limite tecnico, non legale.
**Scritta sul PC la maschera dei gradini** (`tools/limiti_chip.py`: `rung_mask`, `common_mask`; usata dal simulatore delle immagini): ogni stazione annuncia nell'HELLO i gradini che il suo chip realizza (SX1278 senza TCXO: R0-R11 = `0x0FFF`; SX1262 senza TCXO: R1-R11 = `0x0FFE`; con TCXO anche R12-R14), la maschera comune è l'AND delle due meno R3 se i chip differiscono. Il formato dell'HELLO non cambia (la maschera era già a 16 bit). Il calendario di ricerca del collegamento perso si restringe ai gradini comuni. **Da fare:** potenza predefinita +17 dBm nel firmware e il bit TCXO letto dalla scheda vera (nel firmware non esiste ancora).

## 7. Cosa NON è stato confrontato
- I valori di sensibilità a 433 MHz dell'SX1278: il datasheet li dà a 169 MHz (Band 3) e a 868 MHz (Band 1), non a 433 (Band 2): si è usata la colonna Band 3, che è la più vicina.
- R12 e R13 (31,25 e 15,6 kHz): nessun valore di datasheet.
- La sensibilità FSK del gradino R0-R2 con i filtri esatti: i valori del datasheet sono per filtri e deviazioni diversi.
- Tutto ciò che dipende dalla scheda (filtri a 433 MHz, antenna, quarzo reale): misure della fase 1.
