# Immagine a livelli: JPEG progressivo (26/11/2026)

**Decisione dell'autore (26/11/2026):** il formato dell'immagine è il **JPEG progressivo**, preparato sul telefono o sul PC; la scheda trasporta byte e non decodifica. Questa pagina descrive la parte **da PC**, scritta e provata sul PC. **Non provato su schede né su telefoni.** La parte **da telefono** non c'è ancora (vedi in fondo).

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

## Non fatto
1. **La parte da telefono.** La canvas del browser scrive solo JPEG normali (baseline). Per i livelli sul telefono servono: (a) un codificatore JPEG progressivo in WebAssembly (per esempio MozJPEG) caricato dalla pagina; oppure (b) la **trasformazione senza perdite** del JPEG normale in progressivo (come `jpegtran -progressive`), da scrivere in JavaScript. La pagina del telefono ([ble-telefono.md](ble-telefono.md)) per ora manda un JPEG a un solo livello.
2. **Scelta dei livelli.** Tre livelli con la sequenza standard di libjpeg: si può provare uno script a più livelli (per esempio un primo livello solo DC, una miniatura 1/8) quando ci saranno misure vere del tempo di radio.
3. **Misure:** PSNR su immagini vere (fotografie), non solo sintetiche; il peso reale dei livelli dipende dall'immagine.
