# Immagine a livelli: JPEG progressivo (26/11/2026)

**Decisione dell'autore (26/11/2026):** il formato dell'immagine è il **JPEG progressivo**, preparato sul telefono o sul PC; la scheda trasporta byte e non decodifica. Questa pagina descrive la parte **da PC**, scritta e provata sul PC. **Non provato su schede né su telefoni.** La parte da telefono è in JavaScript (vedi «Sul telefono»).

## Idea
Un JPEG progressivo è una sequenza di **scansioni**: le prime danno l'immagine intera ma grossolana, le altre la rifiniscono. Se si taglia il file dopo una scansione e si aggiunge la fine del file (`EOI`), **qualunque decodificatore** mostra una immagine meno dettagliata ma completa. È esattamente ciò che chiede il protocollo ([protocollo-immagini.md](protocollo-immagini.md), principio 2): "il primo livello è una versione piccola e già utile, ogni livello successivo la migliora; l'immagine si può interrompere a un confine di livello e restare visibile". Nessun formato nostro, nessun decodificatore da scrivere, e il file finale è un JPEG normale.

## Tre livelli
Il codificatore di libjpeg (Pillow) scrive per un'immagine a colori **dieci scansioni** (sei in bianco e nero). Le raggruppiamo in tre **livelli**:

| Livello | Scansioni | Cosa si vede | Peso tipico | PSNR (immagine di prova 320×240) |
|---|---|---|---|---|
| 1 | la componente continua (DC) di tutto e le prime 5 frequenze della luminanza | immagine intera, sfocata, senza dettagli | circa **29%** | 28,5 dB |
| 2 | fino alla rifinitura a metà precisione della luminanza (colore e dettaglio medio) | immagine buona | circa **53%** cumulato | 38,9 dB |
| 3 | tutto | l'immagine completa | 100% | identica |

Nel simulatore con un budget breve su un canale debole arrivano solo i **2784 byte del primo livello** (il 29%) e l'immagine si decodifica con PSNR 28,5 dB.

**Confini su pezzo.** Il protocollo lavora a pezzi da 16 byte e il campo `layer_ends` dell'OFFER conta pezzi. Il codificatore **allinea** la fine di ogni livello a un multiplo di 16 inserendo un segmento **COM** (commento JPEG, ignorato dai decodificatori) dopo l'ultima scansione del livello: al massimo 19 byte per livello; in prova costa meno di 40 byte e **non cambia un pixel**. Così il ricevitore che ha `n` livelli ha esattamente i byte del livello e non l'inizio di una scansione successiva.

## Il programma
[`tools/immagine_livelli.py`](../tools/immagine_livelli.py) (serve Pillow e numpy):
```bash
python3 tools/immagine_livelli.py foto.png --max-bytes 10000 -o foto.jpg
```
Cerca il lato e la qualità migliori che stanno nel limite (lati da 320 a 32 pixel, qualità da 85 a 15), scrive il JPEG progressivo e stampa, per ogni livello, byte, PSNR e **tempo di radio stimato** a R4, R5, R8 e R10. Funzioni: `codifica`, `livelli`, `allinea`, `prefisso` (il file con i primi `n` livelli), `pezzi` (`layer_ends` dell'OFFER), `tempi`, `livelli_nel_budget`.

Esempio (immagine sintetica 320×240, 9577 byte): R5 consegna il livello 1 in 3 s, il 2 in 5 s, tutto in 9 s; a R10 (il gradino di incontro) i tre livelli richiedono circa 2, 4 e 8 minuti.

## Come si usa nel protocollo
- Il mittente calcola il JPEG e i livelli (PC oggi, telefono domani), poi manda l'oggetto con `BEGIN` (ponte BLE, fine dei livelli in **byte**) e la scheda lo trasforma nell'`OFFER` radio (fine dei livelli in **pezzi**).
- **Budget di tempo** (di base 10 minuti): prima di ogni livello il mittente stima il tempo che resta; se il livello non entra si ferma al confine e manda `DONE` con i livelli consegnati. Provato nel simulatore con l'oggetto vero (`Simulator(..., data=jpeg, layer_pieces=pezzi)`).
- Il ricevitore prende i byte consegnati, aggiunge `EOI` e decodifica: a metà trasferimento già c'è una immagine.

## Provato (sul PC, 35 controlli in `tests/sim/test_immagine_livelli.py`)
JPEG progressivo valido a dieci scansioni; tre livelli con pesi 29% e 53%; ogni livello si decodifica alla stessa dimensione e la qualità cresce a ogni livello (28,5 → 38,9 dB → identico); il primo livello è vicino all'originale (PSNR oltre 18 dB); il riempimento non cambia i pixel; limiti da 2 a 40 kB rispettati e limite impossibile senza errore; bianco e nero a sei scansioni; JPEG normale = un solo livello; dati non JPEG rifiutati; OFFER e BEGIN con i livelli veri; tempi e budget; consegna nel simulatore del protocollo, completa e interrotta a un confine di livello.

## Sul telefono: trasformazione senza perdite in JavaScript (fatta il 26/11/2026)
La canvas del browser scrive solo JPEG normali (baseline). Si è scelta la via della **trasformazione senza perdite** (come `jpegtran -progressive`), scritta in JavaScript: [`site/jpeg_prog.js`](../site/jpeg_prog.js), circa 250 righe, nessuna libreria esterna e nessun file da scaricare. La pagina del telefono ([ble-telefono.md](ble-telefono.md)) fa così: la canvas scrive il JPEG normale, `JpegProg.transcode` lo legge, ne prende i **coefficienti DCT** (decodifica di Huffman) e li **riscrive** con lo script di scansioni di libjpeg (10 scansioni a colori, 6 in bianco e nero) e **tabelle di Huffman ottimizzate** (Annex K.2); poi raggruppa le scansioni nei tre livelli e allinea i confini ai pezzi con il segmento COM. **Nessun pixel cambia.** Il limite di dimensione si controlla sul file già trasformato (che pesa circa il 10% in meno del normale).

**Provato (`tests/sim/test_jpeg_prog_js.py`, contro libjpeg con Pillow, 11 JPEG di partenza):** colore 4:2:0, 4:4:4, 4:2:2; bianco e nero; dimensioni dispari (251×187, 33×17, 77×41, anche 1×1); qualità da 15 a 95; **intervalli di ripartenza**: in tutti i casi **gli stessi pixel** del JPEG di partenza, il numero di scansioni di libjpeg (10 o 6), tre livelli con confini su pezzo e qualità crescente, gli stessi livelli di `tools/immagine_livelli.py`, dimensione entro il 5% di quella di libjpeg (progressivo ottimizzato: 9011 contro 8987 byte). Ingressi non validi (vuoto, testo, troncato, già progressivo) danno un errore chiaro. La pagina del telefono è provata con la scheda finta: l'immagine arriva come JPEG progressivo (SOF2) con tre livelli nel `BEGIN`.

**Limiti noti:** accetta solo JPEG a 8 bit con una o tre componenti e una sola scansione (quello che scrive la canvas del browser); non gestisce JPEG aritmetici o già progressivi (errore). Provato in Node con Pillow; **nel browser vero con la canvas di Chrome** è provato con la scheda finta, non con altri browser.

## Non fatto
1. **Scelta dei livelli.** Tre livelli con la sequenza standard di libjpeg: si può provare uno script a più livelli (per esempio un primo livello solo DC, una miniatura 1/8) quando ci saranno misure vere del tempo di radio.
2. **Misure:** PSNR su immagini vere (fotografie), non solo sintetiche; il peso reale dei livelli dipende dall'immagine.
3. **Altri browser e telefoni:** la pagina è provata con Chrome; Safari su iPhone non ha il Web Bluetooth (serve l'applicazione).
