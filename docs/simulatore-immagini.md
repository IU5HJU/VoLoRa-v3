# Simulatore del protocollo immagini (bozza)

Programma da riga di comando che **esegue il protocollo** di [protocollo-immagini.md](protocollo-immagini.md) con **mittente e ricevitore** separati, **frame codificati e decodificati con i formati veri** e un **canale con perdite**, in tempo simulato. Serve a trovare i difetti della bozza prima di scrivere il firmware e a ritarare le regole quando arrivano le misure. È [`tools/sim_immagini.py`](../tools/sim_immagini.py); le prove sono in [`tests/sim/`](../tests/sim).

> **Stato (21/11/2026): scritto e provato sul PC. Il modello del canale è un'ipotesi**: usa le **sensibilità stimate** di [scala-modi.md](scala-modi.md), non misure. I numeri dei risultati dicono come si comporta il *protocollo*, non quanto va lontano la radio.

## Uso
```bash
python3 tools/sim_immagini.py --size 20000 --layers 3 --prx -110 --trace      # una prova, con il registro degli eventi
python3 tools/sim_immagini.py --prx -126 --scenario gradino --extra 9 --when 100 --size 6000 --budget 7200
python3 tools/sim_immagini.py --sweep --size 5000 --runs 8                    # tabella al variare della potenza ricevuta
python3 -I tests/sim/test_sim_immagini.py                                     # prove automatiche
```
Opzioni: `--prx` potenza ricevuta di partenza (dBm), `--scenario` `costante` | `degrada` (rampa) | `gradino` (salto) | `oscilla`, `--extra` dB della variazione, `--budget` secondi per oggetto, `--chip` `SX1278` | `SX1262`, `--seed`.

## Cosa simula
- **Fasi del protocollo:** incontro (HELLO a R10 con attesa crescente), misura e scelta del gradino (PROBE, MODE-SET, MODE-ACK, verifica), OFFER e ACCEPT, trasferimento a finestre con STATUS e ritrasmissione dei soli blocchi mancanti, salita e discesa di gradino, **budget di tempo** con livelli, DONE con CRC del prefisso consegnato.
- **Disallineamenti:** ogni stazione ha il **proprio gradino**; un frame si sente solo se i due gradini coincidono. Un MODE-ACK perso lascia le stazioni su gradini diversi: si vede l'attesa del fallback a R10.
- **Canale:** un frame arriva con probabilità logistica attorno alla sensibilità stimata del gradino, elevata a (byte / 64) (più lungo è, più si perde), con un affievolimento casuale di 1,5 dB per frame e uno scenario che cambia la potenza nel tempo.
- **Tempi:** tempo in aria vero di ogni frame (formule di `tools/protocollo_immagini.py`), 0,15 s di commutazione a ogni cambio di verso. Mezzo duplex.

**Non simula:** collisioni con altre stazioni, il CAD, gli errori sui bit (un frame arriva intero o si perde), la deriva del quarzo, la parità XOR, l'identificazione periodica, i tempi reali del FIFO e dell'SPI.

## Risultati (canale costante, 8 prove per riga)
Oggetto da **5 kB**, 3 livelli, budget 60 minuti:

| P rx dBm | riuscite | livelli (mediana) | tempo mediano | di cui trasferimento | ritrasmessi | fallback medi |
|---|---|---|---|---|---|---|
| -80 | 8/8 | 3 | 24 s | 3 s | 0 % | 0.0 |
| -90 | 8/8 | 3 | 24 s | 3 s | 0 % | 0.0 |
| -100 | 8/8 | 3 | 25 s | 3 s | 0 % | 0.0 |
| -110 | 8/8 | 3 | 24 s | 2 s | 3 % | 0.0 |
| -115 | 8/8 | 3 | 27 s | 5 s | 2 % | 0.0 |
| -120 | 8/8 | 3 | 37 s | 14 s | 2 % | 0.0 |
| -125 | 8/8 | 3 | 74 s | 48 s | 2 % | 0.0 |
| -130 | 8/8 | 3 | 4 min | 4 min | 0 % | 0.0 |
| -135 | 8/8 | 3 | 8 min | 8 min | 15 % | 0.1 |
| -138 | 7/8 | 3 | 20 min | 18 min | 21 % | 0.2 |

Oggetto da **20 kB**, 3 livelli, **budget 10 minuti**:

| P rx dBm | riuscite | livelli (mediana) | tempo mediano | di cui trasferimento | ritrasmessi | fallback medi |
|---|---|---|---|---|---|---|
| -80 | 8/8 | 3 | 31 s | 10 s | 0 % | 0.0 |
| -90 | 8/8 | 3 | 31 s | 10 s | 0 % | 0.0 |
| -100 | 8/8 | 3 | 34 s | 13 s | 0 % | 0.0 |
| -110 | 8/8 | 3 | 28 s | 7 s | 1 % | 0.0 |
| -115 | 8/8 | 3 | 40 s | 19 s | 1 % | 0.0 |
| -120 | 8/8 | 3 | 77 s | 54 s | 1 % | 0.0 |
| -125 | 8/8 | 3 | 4 min | 3 min | 1 % | 0.0 |
| -130 | 8/8 | 1 | 6 min | 5 min | 0 % | 0.0 |
| -135 | 8/8 | 1 | 12 min | 12 min | 12 % | 0.1 |
| -138 | 7/8 | 1 | 26 min | 24 min | 18 % | 0.2 |

Lettura: con segnale forte un oggetto da 5 kB arriva in circa 25 s, **ma solo 3 s sono trasferimento**; il resto è l'incontro. Da -125 dBm in giù il tempo cresce in fretta; con il budget di 10 minuti, a -130 dBm e oltre arriva **solo il primo livello** (il primo livello è obbligatorio e può superare il budget). A -138 dBm, al limite di R10, una prova su otto fallisce.

## Cosa ha trovato (e cosa è stato corretto nella bozza)
1. **Il conto dello STATUS era sbagliato:** 19 byte e non 18 (un byte riservato di troppo). Corretto.
2. **L'indirizzamento non reggeva il cambio di gradino:** una mappa con un bit per pezzo non va bene quando i frame cambiano dimensione. Soluzione: pezzi da **16 byte**, il frame DATA porta **k pezzi**, la mappa dello STATUS ha **un bit per blocco** (k pezzi al gradino attuale) e il ricevitore tiene la mappa a livello di pezzo. Corretto nel documento.
3. **Il CRC dell'oggetto intero non serve se si consegnano solo alcuni livelli:** il DONE porta il **CRC del prefisso consegnato**. Corretto.
4. **Il timer di fallback scattava sul mittente mentre trasmetteva** una finestra lunga (31 s di "silenzio" ai gradini lenti): ora **conta solo il tempo in ascolto**. Corretto.
5. **R11-R14 non erano raggiungibili dall'incontro: corretto con la ricerca a calendario** (vedi sotto). Aiuta molto, ma nei casi estremi resta una consegna su due.
6. **L'incontro costava circa 21 s: corretto** con la misura dentro la risposta all'HELLO (circa 5 s, vedi sotto).
7. **Aperto: il gradino FSK a 50 kbit/s (R2) non conviene:** velocità netta di circa 38 kbit/s, come LoRa 500/SF6 (R3) ma con 10 dB in meno di sensibilità stimata.

## La ricerca a calendario: prima e dopo
Problema: dopo un lungo silenzio le due stazioni tornavano a R10, ma se il segnale era sceso sotto R10 non si ritrovavano più. **Correzione provata sul simulatore:** dopo un silenzio in ascolto di 30 s o più, **entrambe seguono lo stesso calendario di gradini in funzione del tempo** (R10, R11, R10, R12, R10, R13, R10, R14 e di nuovo da capo; da 120 s a ogni gradino), e il mittente manda HELLO al gradino in cui si trova. Per non sfasarsi servono quattro regole, trovate una alla volta con il simulatore:
- il ricevitore **esce dalla ricerca solo se sente un frame diverso da HELLO**: se la risposta a un HELLO si perde, il suo calendario non si azzera;
- il mittente, dopo la risposta all'HELLO, **tiene il gradino**, ma se la prova non riesce **riprende lo stesso calendario** (non ne comincia uno nuovo);
- il ricevitore, dopo aver risposto a un HELLO, **resta al gradino per 12 frame** (almeno 60 s) per dare tempo alle prove, poi riprende il calendario che dipende solo dal tempo;
- **dopo il ritrovamento non si rifà la raffica di PROBE**: lo scambio di HELLO ha già provato il collegamento, e a gradini lenti la raffica durava più della sosta. Il trasferimento riprende dal punto in cui era (il ricevitore conserva la mappa).
Inoltre il report delle PROBE parte **a timer** dopo la raffica (non solo se arriva l'ultima), e se nessun gradino ha il margine richiesto si sceglie il più veloce con 3 dB, altrimenti il più lento.

Confronto con il solo ritorno a R10, 16 prove per riga (riuscite), con l'incontro a misura nell'HELLO (punto successivo):

| Scenario | solo R10 | calendario |
|---|---|---|
| rampa da -128 a -140 dBm in 300 s, 6 kB | 16/16 | 16/16 |
| rampa da -130 a -144 dBm in 200 s, 3 kB | 6/16 | 16/16 |
| rampa da -134 a -142 dBm in 150 s, 3 kB | 16/16 | 16/16 |
| salto da -132 a -141 dBm a 60 s, 2 kB | 15/16 | 15/16 |
| onda fra -132 e -146 dBm (600 s), 2 kB | 15/16 | 16/16 |
| salto da -136 a -147 dBm a 60 s, 1 kB | 1/16 | 11/16 |
| salto da -134 a -148 dBm a 60 s, 1 kB | 6/16 | 11/16 |

Il calendario è **sempre uguale o migliore** del solo R10, e il guadagno è netto dove R10 non si sente più (1 su 16 contro 11 su 16). **Attenzione a come leggere questi numeri:** nel modello i frame corti hanno più probabilità di arrivare (probabilità elevata a byte/64): HELLO e MODE-SET (7-17 byte) si sentono anche qualche dB sotto la sensibilità di R10, per questo il solo ritorno a R10 non va a zero nei casi intermedi. Quanto pesi davvero la lunghezza del frame lo dirà la misura (fase 1).

**Perché R10 compare a ogni secondo turno.** Con il calendario semplice (R10, R11, R12, R13, R14) la stazione lasciava R10 anche quando il collegamento stava per tornare, e con un'onda fra -132 e -146 dBm riusciva 7 volte su 16 contro le 15 del solo R10. Interlacciando R10 con i gradini lenti il caso diventa 16 su 16 e i casi difficili migliorano (da 9 a 11 e da 13 a 16 su 16).

## L'incontro più corto: la misura dentro la risposta all'HELLO
Problema (punto 6): con la raffica di 8 PROBE a R10 (circa 2 s l'una) l'incontro costava circa 21 s. **Correzione provata sul simulatore:** il ricevitore mette nella **risposta all'HELLO** l'RSSI e l'SNR dell'HELLO appena sentito (due byte, flag 2); il mittente sceglie il gradino da quella misura senza raffica, poi verifica con una raffica breve **al nuovo gradino** (dove i frame sono brevissimi). Confronto su un oggetto da 5 kB, 16 prove per riga (riuscite, tempo mediano):

| P rx dBm | 8 PROBE (vecchio) | 3 PROBE | misura nell'HELLO |
|---|---|---|---|
| -80 | 16/16, 24 s | 16/16, 15 s | 16/16, **8 s** |
| -100 | 16/16, 25 s | 16/16, 16 s | 16/16, **9 s** |
| -115 | 16/16, 27 s | 16/16, 18 s | 16/16, **11 s** |
| -125 | 16/16, 74 s | 16/16, 63 s | 16/16, 59 s |
| -130 | 16/16, 4 min | 16/16, 4 min | 16/16, 4 min |
| -135 | 16/16, 9 min | 16/16, 8 min | 16/16, 8 min |

Con segnale forte l'incontro passa da circa 21 s a circa 5 s, senza perdere affidabilità (a -136, -138 dBm, con l'onda e con il salto di -10 dB le riuscite sono uguali). Costo: **una misura sola è rumorosa** (affievolimento di 1,5 dB nel modello): in un caso il primo livello veniva respinto per budget perché la misura era 2 dB più bassa del vero. Per questo il mittente respinge il primo livello solo se **non entra nel budget neppure al gradino migliore che la misura lascia sperare (margine 3 dB)**; poi, dopo le prime finestre, può salire di gradino con le STATUS.

## Prove automatiche (`tests/sim/test_sim_immagini.py`)
Codifica e decodifica di tutti i frame (dimensioni: DATA con intestazione di 6 byte, STATUS di 18, PROBE di 32), frame con versione 2 scartati, **determinismo** (stesso seme, stesso risultato), consegna con CRC giusto a -100, -118 e -128 dBm, tempo crescente al calare del segnale, **budget** (livelli che non entrano non partono, primo livello obbligatorio, rinuncia se non entra), **assenza di collegamento** (13 HELLO, rinuncia dopo circa 10 minuti), **ricerca a calendario** contro solo R10 (8 semi, scenario senza R10), **MODE-ACK perso** (disallineamento e recupero), **STATUS persi**, **gradino di -9 dB** a metà trasferimento, segnale ondulato con ritrasmissioni, confronto con la stima della tabella (a -100 dBm 20 kB: 13 s simulati e 13 s stimati).

## Prossimi passi
Ritarare il canale con le misure della fase 1 (sensibilità vere e lunghezza dei frame); aggiungere errori sui bit, la parità XOR e collisioni; capire perché nei casi estremi (solo R13-R14) la consegna riesce solo 11 volte su 16; provare la scelta del gradino con più misure (media) e la parità XOR; decidere se R2 si toglie.
