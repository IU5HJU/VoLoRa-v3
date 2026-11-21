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
5. **Aperto: R11-R14 non sono raggiungibili dall'incontro.** Se il segnale scende sotto la sensibilità di R10 mentre si lavora a gradini più lenti, il ritorno a R10 non basta (esempio: `--prx -128 --scenario degrada --extra 12 --span 300`, con i semi da 1 a 6 una prova su sei fallisce con "negoziazione non riuscita"). Serve un gradino di rifugio più lento o una scansione.
6. **Aperto: l'incontro costa circa 21 s** a R10, che per immagini piccole è quasi tutto il tempo. Da ridurre.
7. **Aperto: il gradino FSK a 50 kbit/s (R2) non conviene:** velocità netta di circa 38 kbit/s, come LoRa 500/SF6 (R3) ma con 10 dB in meno di sensibilità stimata.

## Prove automatiche (`tests/sim/test_sim_immagini.py`)
Codifica e decodifica di tutti i frame (dimensioni: DATA con intestazione di 6 byte, STATUS di 18, PROBE di 32), frame con versione 2 scartati, **determinismo** (stesso seme, stesso risultato), consegna con CRC giusto a -100, -118 e -128 dBm, tempo crescente al calare del segnale, **budget** (livelli che non entrano non partono, primo livello obbligatorio, rinuncia se non entra), **assenza di collegamento** (13 HELLO, rinuncia dopo circa 10 minuti), **MODE-ACK perso** (disallineamento e recupero), **STATUS persi**, **gradino di -9 dB** a metà trasferimento, segnale ondulato con ritrasmissioni, confronto con la stima della tabella (a -100 dBm 20 kB: 13 s simulati e 13 s stimati).

## Prossimi passi
Ritarare il canale con le misure della fase 1 (sensibilità vere e lunghezza dei frame); aggiungere errori sui bit, la parità XOR e collisioni; provare le correzioni ai punti aperti 5-7 con il simulatore prima di scrivere il firmware.
