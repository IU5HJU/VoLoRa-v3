# Scala dei modi (bozza, fase 1)

> **Stato: bozza calcolata, nessuna misura.** Le cifre di LoRa vengono dalle formule Semtech (tempo in aria) e dai valori di SNR di demodulazione per SF ricordati dal datasheet, **da verificare** (vedi [radio-limiti.md](radio-limiti.md)). Quelle dell'FSK sono **orientative** (regola grossolana, vedi sotto). Il programma che le calcola è [`tools/scala_modi.py`](../tools/scala_modi.py). Cifra di rumore del ricevitore ipotizzata: 6 dB. La fase 1 serve a **sostituire queste stime con misure**.

## LoRa (CR 4/5, pacchetti da 255 byte, preambolo 8, CRC)

Colonna "Δ" = sensibilità stimata rispetto a BW 250 kHz / SF7 (negativo = riceve più debole). "20 kB" = tempo per 20 000 byte di dati utili, senza conferme né ritrasmissioni.

| # | BW kHz | SF | bit rate | pacchetto 255 B | sensibilità | Δ | 20 kB |
|---|---|---|---|---|---|---|---|
| L1 | 500 | 5 (solo SX1262) | 62,50 kbit/s | 35 ms | -114 dBm | +8,0 dB | 3 s |
| L2 | 500 | 6 | 37,50 kbit/s | 58 ms | -116 dBm | +5,5 dB | 5 s |
| L3 | 500 | 7 | 21,88 kbit/s | 100 ms | -119 dBm | +3,0 dB | 8 s |
| L4 | 250 | 7 | 10,94 kbit/s | 200 ms | -122 dBm | 0 | 16 s |
| L5 | 250 | 8 | 6,25 kbit/s | 354 ms | -124 dBm | -2,5 dB | 28 s |
| L6 | 250 | 9 | 3,52 kbit/s | 625 ms | -127 dBm | -5,0 dB | 49 s |
| L7 | 125 | 9 | 1,76 kbit/s | 1,25 s | -130 dBm | -8,0 dB | 98 s |
| L8 | 125 | 10 | 0,98 kbit/s | 2,3 s | -132 dBm | -10,5 dB | 3 min |
| L9 | 125 | 12 | 0,29 kbit/s | 9,0 s | -137 dBm | -15,5 dB | 12 min |
| L10 | 62,5 | 12 | 0,15 kbit/s | 18 s | -140 dBm | -18,5 dB | 24 min |
| L11 | 31,25 | 12 | 0,07 kbit/s | 36 s | -143 dBm | -21,5 dB | 47 min |
| L12 | 15,6 | 12 | 0,04 kbit/s | 72 s | -146 dBm | -24,5 dB | 94 min |
| L13 | 7,8 | 12 | 0,02 kbit/s | 145 s | -149 dBm | -27,6 dB | 3,1 h |

Controllo di coerenza con la v2: il passo da L4 (SF7/BW250, profilo **Standard** della v2) a L5 (SF8/BW250, **Range**) dà 2,5 dB, come scritto nella documentazione della v2; L9 (SF12/BW125) è il profilo **Messaggio** della v2.

## FSK (orientativo)

Regola usata: banda di ricezione = bit rate + 2 × deviazione, SNR richiesto 12 dB, cifra di rumore 6 dB. È solo un ordine di grandezza: la sensibilità vera dipende dalla tabella RxBw e dall'indice di modulazione del chip. Tempi "solo dati", senza intestazioni, conferme né FIFO.

| # | bit rate | deviazione | RxBw | sensibilità | 20 kB |
|---|---|---|---|---|---|
| F1 | 300 kbit/s | 100 kHz | 500 kHz | circa -99 dBm | 1 s |
| F2 | 150 kbit/s | 50 kHz | 250 kHz | circa -102 dBm | 1 s |
| F3 | 100 kbit/s | 50 kHz | 200 kHz | circa -103 dBm | 2 s |
| F4 | 50 kbit/s | 25 kHz | 100 kHz | circa -106 dBm | 3 s |
| F5 | 19,2 kbit/s | 10 kHz | 39 kHz | circa -110 dBm | 8 s |
| F6 | 4,8 kbit/s | 5 kHz | 15 kHz | circa -114 dBm | 33 s |

**Avvertenza sulla banda di ricezione (da RadioLib):** l'SX1278 arriva a 250 kHz di banda di ricezione in FSK, l'SX1262 a 467 kHz. Con banda necessaria = bit rate + 2 × deviazione, F1 (circa 500 kHz) **non entra** nemmeno nell'SX1262 e F2/F3 stanno al limite dell'SX1278. La riga F1 va rivista con deviazioni più strette.

## Cosa suggerisce la bozza (da confermare con le misure)
1. **Le due famiglie si incrociano.** In FSK la sensibilità scende sotto -106 dBm solo a velocità basse, mentre LoRa a 500 kHz (L2, 37,5 kbit/s) stimata a -116 dBm è sia più veloce di F4 sia più sensibile. Quindi **FSK serve solo per il gradino più alto** (F1-F3, da 100 a 300 kbit/s, collegamenti forti); **da L3 in giù conviene LoRa**.
2. **Scala operativa proposta** (sei gradini di partenza, tutti da misurare):

| Gradino | Modo | Uso |
|---|---|---|
| 0 | F1 (FSK 300 kbit/s) | collegamento fortissimo, immagini in pochi secondi |
| 1 | F3 (FSK 100 kbit/s) | collegamento forte |
| 2 | L2 (LoRa BW500 SF6) | passaggio da FSK a LoRa |
| 3 | L4 (LoRa BW250 SF7) | come lo Standard della v2 |
| 4 | L7 (LoRa BW125 SF9) | collegamenti deboli |
| 5 | L9 (LoRa BW125 SF12) | **modo di incontro**, come il Messaggio della v2 |
| 6+ | L10-L13 | casi estremi, con immagine ridotta (vedi sotto) |

3. **Modo di incontro:** L9 come primo contatto, perché è il profilo Messaggio già noto e il più robusto fra quelli senza problemi di quarzo.
4. **Immagine ridimensionata per budget di tempo.** Con un tempo massimo per immagine (esempio: 10 minuti) i byte utili sono circa: L9 ~ 22 kB lordi di prestazione (0,29 kbit/s × 600 s ≈ 21 kB), L10 ~ 11 kB, L11 ~ 5 kB, L12 ~ 2,6 kB, L13 ~ 1,3 kB. Sotto L10 l'immagine deve diventare una miniatura molto piccola, e l'ultimo gradino ha senso solo con un'immagine di pochi kB.
5. **Sotto i 31 kHz di banda** serve un quarzo molto stabile (TCXO): la deriva può superare la banda. Le T3 normali non lo hanno (esiste una variante T3 con TCXO nel repository LilyGO): da misurare prima di contare su L10-L13.
6. **Tempi in aria lunghi** (decine di secondi per pacchetto da L10): niente conferma per pacchetto; servono conferme cumulative o correzione d'errore (fase 3).

## Cosa deve misurare la fase 1
- Per ogni gradino: bit rate reale (con preambolo e intestazioni), perdita pacchetti in funzione dell'attenuazione, sensibilità vera con attenuatore fisso.
- FSK: sensibilità reale per ogni coppia bit rate / deviazione / RxBw, e se l'SX1278 regge i 300 kbit/s con il FIFO da 64 byte.
- Deriva del quarzo alle bande strette, con e senza TCXO.
- Rendimento delle schede a 430 e 440 MHz.
